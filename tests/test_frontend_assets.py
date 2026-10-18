"""Regression coverage for Windows MIME associations and stale frontend caches."""
import mimetypes

import pytest
import starlette.responses
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static_assets import FrontendStaticFiles


@pytest.fixture
def assets(tmp_path, monkeypatch):
    static_dir = tmp_path / "public"
    static_dir.mkdir()
    for suffix in FrontendStaticFiles.CONTENT_TYPES:
        (static_dir / ("asset" + suffix)).write_bytes(b"public fixture")
    (tmp_path / "secret.txt").write_text("outside static root", encoding="utf-8")

    # FileResponse imports guess_type directly; poison both entry points to
    # reproduce arbitrary MIME associations loaded from the Windows registry.
    incorrect_guess = lambda *args, **kwargs: ("text/plain", None)
    monkeypatch.setattr(mimetypes, "guess_type", incorrect_guess)
    monkeypatch.setattr(starlette.responses, "guess_type", incorrect_guess)
    app = FastAPI()
    app.mount("/static", FrontendStaticFiles(directory=static_dir), name="static")
    app.mount("/_ui/{revision}", FrontendStaticFiles(directory=static_dir), name="frontend")
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("suffix,expected", list(FrontendStaticFiles.CONTENT_TYPES.items()))
def test_browser_asset_types_override_os_associations(assets, suffix, expected):
    response = assets.get("/static/asset" + suffix)
    assert response.status_code == 200
    assert response.headers["content-type"] == expected
    assert response.headers["cache-control"] == FrontendStaticFiles.CACHE_CONTROL
    assert response.content == b"public fixture"


def test_conditional_asset_revalidation_keeps_cache_policy(assets):
    initial = assets.get("/static/asset.js")
    cached = assets.get("/static/asset.js", headers={"If-None-Match": initial.headers["etag"]})
    assert cached.status_code == 304
    assert cached.headers["cache-control"] == FrontendStaticFiles.CACHE_CONTROL
    assert cached.headers["content-type"] == "application/javascript"
    assert cached.content == b""
    head = assets.head("/static/asset.ttf")
    assert head.status_code == 200
    assert head.headers["content-type"] == "font/ttf"
    assert head.content == b""


def test_release_directory_serves_nested_resources_with_correct_types(assets):
    for revision in ("old-release", "new-release"):
        response = assets.get(f"/_ui/{revision}/asset.js")
        assert response.status_code == 200
        assert response.content == b"public fixture"
        assert response.headers["content-type"] == "application/javascript"
        assert response.headers["cache-control"] == FrontendStaticFiles.CACHE_CONTROL
        assert assets.get(f"/_ui/{revision}/asset.ttf").headers["content-type"] == "font/ttf"


@pytest.mark.parametrize("path", ["/static/missing.js", "/static/%2e%2e/secret.txt",
                                  "/_ui/release/missing.js", "/_ui/release/%2e%2e/secret.txt"])
def test_missing_files_and_traversal_remain_404(assets, path):
    response = assets.get(path)
    assert response.status_code == 404
    assert "cache-control" not in response.headers
    assert "outside static root" not in response.text
