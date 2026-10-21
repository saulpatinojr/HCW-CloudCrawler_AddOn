"""The pane's static files. Paths are normalised and must stay under the configured directory."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from cloud_crawler_lab.errors import ApiError

MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


def safe_file(base: Path, relative: str) -> Path | None:
    root = base.resolve()
    try:
        candidate = (root / relative).resolve()
    except OSError:
        return None
    if candidate == root or root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


pane = APIRouter()


@pane.get("/{path:path}", include_in_schema=False)
async def static_file(request: Request, path: str) -> Response:
    if path.startswith("api/") or path == "api":
        raise ApiError(404, "not_found", "Not found.")
    relative = path or "index.html"
    file = safe_file(request.app.state.settings.static_dir, relative)
    if file is None:
        raise ApiError(404, "not_found", "Not found.")
    return FileResponse(file, media_type=MEDIA_TYPES.get(file.suffix, "application/octet-stream"))
