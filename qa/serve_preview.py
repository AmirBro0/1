"""Локальный просмотр настоящего API без вывода секретов."""
import os
import sys
from pathlib import Path
import uvicorn

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
for line in (root / '.env').read_text(encoding='utf-8-sig').splitlines():
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        os.environ.setdefault(key, value)
uvicorn.run('app.api:app', host='127.0.0.1', port=8765, access_log=False)
