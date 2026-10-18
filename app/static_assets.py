"""Serve browser assets independently of Windows file association MIME types."""
from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class FrontendStaticFiles(StaticFiles):
    """Keep frontend types stable and revalidate cached assets after updates."""

    CONTENT_TYPES = {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".ttf": "font/ttf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".m4a": "audio/mp4",
    }
    CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if 200 <= response.status_code < 300 or response.status_code == 304:
            media_type = self.CONTENT_TYPES.get(Path(path).suffix.lower())
            if media_type:
                response.headers["content-type"] = media_type
            response.headers["cache-control"] = self.CACHE_CONTROL
        return response
