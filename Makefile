# Cloud Crawler lab edition. Every target is a plain uv invocation; nothing reaches a cloud.
.PHONY: setup lint test run image package clean

setup:
	uv python pin 3.14.6
	uv sync --all-packages

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest -q --cov=src --cov-report=term-missing

run:
	CC_ALLOW_NO_TURNSTILE=1 PORT=8080 uv run python -m cloud_crawler_lab

image:
	docker build -f infrastructure/docker/Dockerfile --build-arg EDITION=lab -t hcw-addon-cloud-crawler:dev .

package:
	git archive --format=zip --output=hcw-cloudcrawler-addon.zip HEAD

clean:
	rm -rf .venv .pytest_cache .ruff_cache .coverage coverage.xml htmlcov hcw-cloudcrawler-addon.zip
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
