# Infrastructure

| Path | What |
|---|---|
| `docker/Dockerfile` | The lab image (`docker.io/hybridcloudworks/img-cc-lab-addon`): two stages on one digest-pinned base, hash-pinned dependencies, no pip at runtime, uid 10001, `HEALTHCHECK`, `CMD python -m cloud_crawler_lab`. `ARG EDITION=lab` is asserted in both stages. |
| `docker/versions.env` | `BASE_IMAGE`, `BASE_DIGEST`, `BASE_PYTHON_VERSION`; CI fails when any `FROM` differs from `BASE_IMAGE@BASE_DIGEST` (the `lint` job in `ci.yml`, and `tests/unit/test_base_image_pin.py` in the regular test run), and the `image` job in `ci.yml` fails when the built image's `python --version` differs from `BASE_PYTHON_VERSION`. It follows the website's pin automatically: once a day `.github/workflows/base-update.yml` compares it with the website's `lab-image/versions.env` and, when they differ, opens the pull request that moves it and every `FROM` together (`scripts/follow_website_base.py`); a person only reviews and merges that pull request. `security.yml`'s `base-follows-website` job stays as the second check, on `main` and weekly. |
| `../docker-compose.yml` | Local development only, hardened like the lab host's `docker_container` (read-only root, tmpfs `/tmp`, `cap_drop ALL`, `no-new-privileges`, 512m, 256 pids, one CPU). |

There is no Terraform here and there must not be (AddOn Integration Standard, section 3): the lab host belongs to the
website repository (`lab-host/ansible`, role `addons`), and the Azure appliance belongs to `HCW-CloudCrawler_App`.

The lab application is copied into `/usr/local/lib/python3.14/site-packages` as a source tree rather than built as a
wheel, so no build backend enters the image. The build stage exports `uv.lock` with `uv export --frozen --format
requirements-txt --no-dev --no-emit-project` (hashes on by default), using the uv CI uses by digest. That export is the
only input `pip install --require-hashes --no-deps` reads, and uv stays in the build stage. There is no committed
export: `uv.lock` is the one lock, which Dependabot (`uv` ecosystem) updates with `pyproject.toml`. When the engine
is adopted from the App it enters through `uv.lock` as a hash-verified release wheel (ADR 0001).

Image build, Trivy and the `import azure` image check run in CI (`ci.yml`, `publish-images.yml`); the authoring
container had no Docker daemon (see `VALIDATION.md`).
