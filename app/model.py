import json
import math
import os
import subprocess
import time
from pathlib import Path

from .config import Settings


class ModelError(ValueError):
    pass


def load_rules(path: Path) -> dict:
    rules = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rules, dict) or not rules:
        raise ModelError("Каталог правил пуст или поврежден")
    return rules


def run_model(video_path: Path, duration: float, settings: Settings, rules: dict, deadline: float) -> list[dict]:
    if not settings.model_command:
        raise ModelError("Команда локальной модели не настроена")
    request = {"schema_version": 1, "video_path": str(video_path), "duration_sec": duration}
    timeout = min(settings.model_timeout_seconds, deadline - time.monotonic())
    if timeout <= 0:
        raise ModelError("Превышен общий лимит обработки видео")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(settings.model_command, input=json.dumps(request).encode("utf-8"),
                              capture_output=True, timeout=timeout, check=False, env=environment)
    except subprocess.TimeoutExpired as exc:
        raise ModelError("Локальная модель превысила лимит времени") from exc
    except OSError as exc:
        raise ModelError("Не удалось запустить локальную модель") from exc
    if proc.returncode != 0:
        raise ModelError("Локальная модель завершилась с ошибкой: " + proc.stderr[-300:].decode("utf-8", errors="replace").strip())
    if len(proc.stdout) > 1_000_000:
        raise ModelError("Ответ локальной модели слишком большой")
    try:
        response = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelError("Локальная модель вернула некорректный JSON") from exc
    if not isinstance(response, dict) or response.get("schema_version") != 1:
        raise ModelError("Неподдерживаемая версия ответа локальной модели")
    events = response.get("events")
    if not isinstance(events, list) or len(events) > 20:
        raise ModelError("Поле events должно быть массивом до 20 событий")
    validated = []
    for event in events:
        if not isinstance(event, dict):
            raise ModelError("Каждое событие должно быть объектом")
        event_type = event.get("event_type")
        if not isinstance(event_type, str) or event_type not in rules:
            raise ModelError(f"Неизвестный код события: {event_type!r}")
        timestamp = event.get("timestamp_sec")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or not 0 <= timestamp < duration:
            raise ModelError("Таймкод события вне диапазона видео")
        observation = event.get("observation")
        if not isinstance(observation, str) or not observation.strip() or len(observation) > 500:
            raise ModelError("Поле observation должно содержать краткое описание видимого действия")
        frames = event.get("evidence_timestamps_sec", [timestamp])
        if not isinstance(frames, list) or not 1 <= len(frames) <= 3:
            raise ModelError("Для события нужны 1–3 таймкода кадров")
        if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 <= t < duration for t in frames):
            raise ModelError("Таймкод кадра вне диапазона видео")
        confidence = event.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                                       or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ModelError("Некорректная уверенность модели")
        validated.append({"event_type": event_type, "timestamp_sec": float(timestamp),
                          "observation": observation.strip(), "frame_times": [float(t) for t in frames],
                          "confidence": confidence})
    return validated
