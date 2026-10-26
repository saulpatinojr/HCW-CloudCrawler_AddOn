import pytest

from cloud_crawler_lab.config import Settings


def test_defaults_from_empty_env():
    s = Settings.from_env({})
    assert s.port == 8080 and s.frame_ancestors == "'none'" and s.ttl_minutes == 120 and s.max_items == 200
    assert s.rate_limit_posts == 10 and s.rate_limit_window_minutes == 10 and s.max_concurrent == 2
    assert not s.trust_proxy and not s.allow_no_turnstile and s.turnstile_secret is None
    assert s.turnstile_enforced and not s.turnstile_required, (
        "fail closed: no secret and no override means uploads answer 503"
    )
    assert s.static_dir.name == "web" and s.max_upload_bytes == 5 * 1024 * 1024 and s.max_rows == 5_000


def test_full_env():
    s = Settings.from_env(
        {
            "PORT": "9000",
            "CC_ALLOWED_ORIGINS": "https://a.example, https://b.example/ https://a.example",
            "CC_FRAME_ANCESTORS": "https://hybridcloudworks.com https://www.hybridcloudworks.com",
            "CC_SITE_ORIGINS": "https://hybridcloudworks.com",
            "TURNSTILE_SECRET": " s3 ",
            "CC_TURNSTILE_SITE_KEY": "k",
            "CC_ALLOW_NO_TURNSTILE": "true",
            "CC_TTL_MINUTES": "5",
            "CC_MAX_ITEMS": "3",
            "CC_RATE_LIMIT_POSTS": "2",
            "CC_RATE_LIMIT_WINDOW_MINUTES": "1",
            "CC_MAX_CONCURRENT": "1",
            "CC_TRUST_PROXY": "1",
            "CC_LOG_SILENT": "yes",
            "CC_STATIC_DIR": "/tmp/web",
        }
    )
    assert s.port == 9000 and s.allowed_origins == ("https://a.example", "https://b.example")
    assert s.site_origins == ("https://hybridcloudworks.com",) and s.turnstile_secret == "s3" and s.turnstile_required
    assert s.turnstile_enforced and s.trust_proxy and s.log_silent and s.static_dir.as_posix() == "/tmp/web"
    assert "s3" not in repr(s), "the secret never appears in repr"


def test_override_only_applies_without_secret():
    s = Settings.from_env({"CC_ALLOW_NO_TURNSTILE": "1"})
    assert not s.turnstile_enforced and not s.turnstile_required


@pytest.mark.parametrize(
    "env",
    [
        {"PORT": "abc"},
        {"PORT": "0"},
        {"CC_TTL_MINUTES": "-1"},
        {"CC_TTL_MINUTES": "9" * 400},
        {"CC_RATE_LIMIT_POSTS": "1000000001"},
        {"CC_MAX_CONCURRENT": "1.5"},
        {"CC_ALLOWED_ORIGINS": "example.com"},
        {"CC_FRAME_ANCESTORS": "'self'; script-src *"},
    ],
)
def test_invalid_values_raise(env):
    with pytest.raises(ValueError):
        Settings.from_env(env)


def test_the_upload_settings_have_defaults_and_can_be_set():
    s = Settings.from_env({})
    assert s.samples_dir.name == "samples" and s.max_store_mb == 64
    s = Settings.from_env({"CC_SAMPLES_DIR": "/app/samples", "CC_MAX_STORE_MB": "8"})
    assert s.samples_dir.as_posix() == "/app/samples" and s.max_store_mb == 8


@pytest.mark.parametrize("env", [{"CC_MAX_STORE_MB": "0"}, {"CC_MAX_STORE_MB": "-4"}, {"CC_MAX_STORE_MB": "lots"}])
def test_the_store_budget_must_be_a_positive_integer(env):
    with pytest.raises(ValueError):
        Settings.from_env(env)
