"""The lab edition is technically unable to reach Azure. Checked at import of app.py; fail closed.

The AddOn collects evidence (uploads, or results the website hands in) but never fetches it: no cloud SDK, no
identity endpoint, no token (ADR 0001). This guard makes that a property of the process, not of the configuration.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import os
import sys
from collections.abc import Mapping

EDITION = "lab"
AZURE_CONNECTIVITY = "disabled-by-design"
# The skeleton's capabilities. The engine's (evidence, drift, reviews, bundles) are added when cloud-crawler-core is
# adopted; capabilities are only ever added, never renamed.
CAPABILITIES = (
    "health",
    "pane",
)
FORBIDDEN_MODULES = ("azure", "msal", "boto3")
IDENTITY_ENV_VARS = (
    "IDENTITY_ENDPOINT",
    "MSI_ENDPOINT",
    "AZURE_CLIENT_SECRET",
    "AZURE_FEDERATED_TOKEN_FILE",
    "AZURE_CLIENT_ID",
    "AZURE_TENANT_ID",
)


class EditionBoundaryError(RuntimeError):
    """Raised when the lab edition would be able to construct a cloud credential."""


class _RefuseCloudSdk(importlib.abc.MetaPathFinder):
    """A meta-path finder that answers any import of a cloud SDK with ImportError, even if one were installed later."""

    def find_spec(self, fullname: str, path=None, target=None):  # type: ignore[override]
        root = fullname.split(".", 1)[0]
        if root in FORBIDDEN_MODULES:
            raise ImportError(f"{root} is not available in the lab edition (edition boundary)")
        return None


def install_import_guard() -> None:
    if not any(isinstance(f, _RefuseCloudSdk) for f in sys.meta_path):
        sys.meta_path.insert(0, _RefuseCloudSdk())


def assert_lab_cannot_reach_azure(env: Mapping[str, str] | None = None) -> None:
    """Refuse to start when a cloud SDK is importable or an identity endpoint / credential variable is present."""
    env = os.environ if env is None else env
    present = [name for name in IDENTITY_ENV_VARS if env.get(name, "").strip()]
    if present:
        raise EditionBoundaryError(f"refusing to start: identity environment present ({', '.join(present)})")
    guard_installed = any(isinstance(f, _RefuseCloudSdk) for f in sys.meta_path)
    for module in FORBIDDEN_MODULES:
        try:
            spec = importlib.util.find_spec(module)
        except ImportError:
            spec = None if guard_installed else "guarded"  # type: ignore[assignment]
        if spec is not None and spec != "guarded":
            raise EditionBoundaryError(f"refusing to start: {module} is importable in the lab edition")
    install_import_guard()
