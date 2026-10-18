"""python -m app --port 8000: one local application, including its worker."""
import argparse
import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    environment = root / ".env"
    if environment.is_file():
        for line in environment.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip())
    os.environ.setdefault("MODEL_DIR", str(root / "model"))
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    options = parser.parse_args()
    import uvicorn
    uvicorn.run("app.api:app", host=options.host, port=options.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
