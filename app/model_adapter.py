"""Узкая точка подключения локальной модели коллеги.

В /model/model_runtime.py должна быть функция predict(video_path, duration_sec).
Она возвращает список событий по контракту README.md.
"""

import json
import os
import sys


def main() -> None:
    request = json.load(sys.stdin)
    if request.get("schema_version") != 1:
        raise ValueError("Неподдерживаемая версия входного контракта")
    sys.path.insert(0, os.getenv("MODEL_DIR", "/model"))
    from model_runtime import predict  # type: ignore[import-not-found]

    events = predict(request["video_path"], request["duration_sec"])
    print(json.dumps({"schema_version": 1, "events": events}, ensure_ascii=False))


if __name__ == "__main__":
    main()
