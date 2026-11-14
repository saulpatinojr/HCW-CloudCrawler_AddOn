# Cloud Crawler lab edition. Every target is a plain uv invocation; nothing reaches a cloud.
.PHONY: setup lint test run image package clean

# .python-version names the line only (3.15). uv refuses to pin that line against requires-python >=3.15.2, because
# the line also covers 3.15.0 and 3.15.1, so the pin skips that check (--no-project); uv sync then picks a 3.15
# interpreter inside requires-python, and fails if none is available.
setup:
	uv python pin --no-project 3.15
	uv sync --all-packages

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run python scripts/check_release_version.py

test:
	uv run pytest -q --cov=src --cov-report=term-missing

run:
	CC_ALLOW_NO_TURNSTILE=1 PORT=8080 uv run python -m cloud_crawler_lab

image:
	docker build -f infrastructure/docker/Dockerfile --build-arg EDITION=lab -t img-cc-lab-addon:dev .

package:
	git archive --format=zip --output=hcw-cloudcrawler-addon.zip HEAD

clean:
	rm -rf .venv .pytest_cache .ruff_cache .coverage coverage.xml htmlcov hcw-cloudcrawler-addon.zip
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
