"""No credential-shaped strings in the tree; .env.example has no values; samples use only the fictional subscription."""

import re
import subprocess
from pathlib import Path

from ..conftest import ROOT

PATTERNS = [
    (re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}"), "storage account key"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}"), "JWT"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "API key"),
    (
        re.compile(r"(client_secret|clientSecret|CLIENT_SECRET)\s*[:=]\s*[\"'][A-Za-z0-9~._-]{20,}[\"']"),
        "client secret literal",
    ),
    (re.compile(r"0x4AAAAAAA[A-Za-z0-9_-]{10,}"), "verification site key"),
    (re.compile(r"TURNSTILE_SECRET[ \t]*=[ \t]*[A-Za-z0-9_][^\s#]{7,}"), "verification secret"),
]
FICTIONAL_SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"
PLACEHOLDER = re.compile(r"^00000000-0000-0000-0000-0000000000[0-9a-fA-F]{2}$")
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SKIP_SUFFIXES = {".png", ".jpg", ".zip", ".ico", ".lock", ".woff", ".woff2"}


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files = [ROOT / line for line in out.splitlines() if line]
    return [
        f
        for f in files
        if f.is_file() and f.suffix not in SKIP_SUFFIXES and ".venv" not in f.parts and "node_modules" not in f.parts
    ]


def test_no_credential_shaped_strings():
    hits = []
    for path in _tracked_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for rx, what in PATTERNS:
            if rx.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {what}")
    assert hits == []


def test_no_real_identifiers_anywhere():
    """Every GUID in the tree is a placeholder of the form 00000000-0000-0000-0000-0000000000NN."""
    hits = []
    for path in _tracked_files():
        for guid in GUID.findall(path.read_text(encoding="utf-8", errors="ignore")):
            if not PLACEHOLDER.match(guid):
                hits.append(f"{path.relative_to(ROOT)}: {guid}")
    assert hits == []


def test_env_example_defines_no_secret_values():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "TURNSTILE_SECRET=" in env
    for line in env.splitlines():
        if line.startswith("TURNSTILE_SECRET"):
            assert line.strip() == "TURNSTILE_SECRET=", line
    assert not re.search(r"SECRET\s*=[ \t]*\S", env)
    for key in (
        "PORT",
        "CC_ALLOWED_ORIGINS",
        "CC_FRAME_ANCESTORS",
        "CC_SITE_ORIGINS",
        "CC_TURNSTILE_SITE_KEY",
        "CC_ALLOW_NO_TURNSTILE",
        "CC_TTL_MINUTES",
        "CC_MAX_ITEMS",
        "CC_RATE_LIMIT_POSTS",
        "CC_RATE_LIMIT_WINDOW_MINUTES",
        "CC_MAX_CONCURRENT",
        "CC_TRUST_PROXY",
        "CC_LOG_SILENT",
        "CC_STATIC_DIR",
    ):
        assert re.search(rf"^{key}=", env, re.MULTILINE), key


def test_gitignore_excludes_secrets_and_runtime_data():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for must in (".env", "*.tfstate", "*.tfvars", "data/", ".venv/", "*.pem"):
        assert must in gi, must


def test_samples_are_fictional():
    for path in (ROOT / "samples").glob("*"):
        text = path.read_text(encoding="utf-8")
        guids = set(GUID.findall(text))
        assert guids <= {FICTIONAL_SUBSCRIPTION}, f"{path.name}: {guids - {FICTIONAL_SUBSCRIPTION}}"


def test_no_vendor_names_in_visitor_facing_text():
    """The pane says 'human verification' and 'expires after two hours'; it names no host, edge or vendor."""
    for path in (ROOT / "web").glob("*.html"):
        text = path.read_text(encoding="utf-8").lower()
        for vendor in ("cloudflare", "turnstile", "hetzner", "coder", "docker hub", "caddy"):
            assert vendor not in text, f"{path.name} names {vendor}"
        assert "human verification" in text and "expires after two hours" in text
