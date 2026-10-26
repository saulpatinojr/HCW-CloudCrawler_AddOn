"""GET /api/samples/{name}: the fictional sample files, by a fixed list of names (never a path from the request)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.routes.static import safe_file

router = APIRouter()

# Exactly the *.json files in samples/ (tests/unit/test_pane.py holds the two lists together).
SAMPLE_FILES = (
    "decision-starter.json",
    "decision-wave-one.json",
    "decision-zone-redundancy.json",
    "sample-resource-graph.json",
)


@router.get("/api/samples/{name}")
async def sample(request: Request, name: str) -> Response:
    if name not in SAMPLE_FILES:
        raise ApiError(404, "not_found", "Not found.")
    path = safe_file(request.app.state.settings.samples_dir, name)
    if path is None:
        raise ApiError(404, "not_found", "Not found.")
    return Response(
        path.read_bytes(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
