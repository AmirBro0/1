import base64
import json
import math
import subprocess
import time
from pathlib import Path

from .config import Settings


class VideoError(ValueError):
    pass


def _remaining(deadline: float, cap: float) -> float:
    seconds = min(cap, deadline - time.monotonic())
    if seconds <= 0:
        raise VideoError("Превышен общий лимит обработки видео")
    return seconds


def probe_video(path: Path, settings: Settings, deadline: float) -> float:
    try:
        run = subprocess.run(
            [settings.ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
            "-of", "json", str(path)], capture_output=True, text=True,
            timeout=_remaining(deadline, 20), check=True
        )
        metadata = json.loads(run.stdout)
        duration = float(metadata["format"]["duration"])
    except (OSError, subprocess.SubprocessError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise VideoError("Файл не удалось прочитать как видео .mov") from exc
    if not any(stream.get("codec_type") == "video" for stream in metadata.get("streams", [])):
        raise VideoError("В файле нет видеопотока")
    if not math.isfinite(duration) or duration <= 0 or duration > settings.max_video_seconds:
        raise VideoError(f"Длительность видео должна быть от 0 до {settings.max_video_seconds:g} секунд")
    return duration


def jpeg_frame(path: Path, second: float, settings: Settings, deadline: float) -> str:
    try:
        run = subprocess.run(
            [settings.ffmpeg, "-nostdin", "-v", "error", "-ss", f"{second:.3f}", "-i", str(path),
             "-map", "0:v:0", "-frames:v", "1", "-vf", "scale='min(960,iw)':-2",
             "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
            capture_output=True, timeout=_remaining(deadline, 20), check=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VideoError(f"Не удалось извлечь кадр на {second:.2f} с") from exc
    if not run.stdout.startswith(b"\xff\xd8") or len(run.stdout) > 2_000_000:
        raise VideoError("Некорректный или слишком большой кадр-доказательство")
    return base64.b64encode(run.stdout).decode("ascii")
