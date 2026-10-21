"""`python -m cloud_crawler_lab`: uvicorn on 0.0.0.0:$PORT, no access log, no proxy headers."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from cloud_crawler_lab.app import create_app
        from cloud_crawler_lab.config import Settings

        settings = Settings.from_env()
        app = create_app(settings)
    except Exception as exc:  # noqa: BLE001 - startup refusal is the point; the reason is printed once, scrubbed
        from cloud_crawler_lab.security.redaction import scrub

        sys.stderr.write(f'{{"event":"startup_refused","reason":"{scrub(str(exc))}"}}\n')
        return 3
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 - the container publishes on loopback; the host binds it
        port=settings.port,
        access_log=False,
        proxy_headers=False,
        server_header=False,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
