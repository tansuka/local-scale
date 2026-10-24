from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.main import create_app


@pytest.fixture()
def dist_app(settings, tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>index</html>")
    (dist / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    return create_app(replace(settings, frontend_dist_path=dist, seed_demo_data=False))


def _raw_get(app, path: str) -> tuple[int, bytes]:
    """Send a request with the path exactly as given, like an HTTP server would.

    Test clients normalise "../" segments away before sending, which would hide
    the traversal this module checks for.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body


def test_serves_files_inside_dist(dist_app):
    assert _raw_get(dist_app, "/assets/app.js") == (200, b"console.log('app')")


def test_unknown_paths_fall_back_to_index(dist_app):
    assert _raw_get(dist_app, "/trends") == (200, b"<html>index</html>")


@pytest.mark.parametrize("path", ["/../secret.txt", "/assets/../../secret.txt"])
def test_parent_segments_cannot_escape_dist(dist_app, path):
    status, body = _raw_get(dist_app, path)

    assert b"TOP SECRET" not in body
    assert (status, body) == (200, b"<html>index</html>")


def test_absolute_paths_cannot_escape_dist(dist_app, tmp_path: Path):
    status, body = _raw_get(dist_app, "/" + str(tmp_path / "secret.txt"))

    assert b"TOP SECRET" not in body
    assert (status, body) == (200, b"<html>index</html>")
