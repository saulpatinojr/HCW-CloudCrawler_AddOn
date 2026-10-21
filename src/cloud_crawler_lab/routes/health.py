"""GET /api/health: the flat standard envelope, answered without any upstream dependency."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from cloud_crawler_lab import ADDON_ID, __version__
from cloud_crawler_lab.edition import AZURE_CONNECTIVITY, CAPABILITIES, EDITION

router = APIRouter()


def health_body(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "ok": True,
        "id": ADDON_ID,
        "version": __version__,
        "edition": EDITION,
        "capabilities": list(CAPABILITIES),
        "asOf": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "siteOrigins": list(settings.site_origins),
        "turnstile": {"required": settings.turnstile_enforced, "siteKey": settings.turnstile_site_key},
        "azureConnectivity": AZURE_CONNECTIVITY,
        "limits": {
            "maxUploadBytes": settings.max_upload_bytes,
            "maxRows": settings.max_rows,
            "ttlMinutes": settings.ttl_minutes,
        },
    }


@router.get("/api/health")
async def health(request: Request) -> dict:
    return health_body(request)
