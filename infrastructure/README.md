# Infrastructure

| Path | What |
|---|---|
| `docker/Dockerfile` | The lab image (`docker.io/hybridcloudworks/hcw-cloudcrawler`): two stages on one digest-pinned base, hash-pinned dependencies, no pip at runtime, uid 10001, `HEALTHCHECK`, `CMD python -m cloud_crawler_lab`. `ARG EDITION=lab` is asserted in both stages. |
| `docker/versions.env` | `BASE_IMAGE`, `BASE_DIGEST`, `BASE_PYTHON_VERSION`; CI fails when any `FROM` differs from `BASE_IMAGE@BASE_DIGEST`. |
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
