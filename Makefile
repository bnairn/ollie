.PHONY: help install dev run docker-build docker-run docker-shell clean test

help:
	@echo "OLLIE - Offline Local Language Intelligence"
	@echo ""
	@echo "Commands:"
	@echo "  make install      Install dependencies"
	@echo "  make dev          Install with dev dependencies"
	@echo "  make run          Run OLLIE in text mode"
	@echo "  make docker-build Build Docker image"
	@echo "  make docker-run   Run in Docker (interactive)"
	@echo "  make docker-shell Shell into Docker container"
	@echo "  make test         Run tests"
	@echo "  make clean        Clean up build artifacts"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

run:
	python -m ollie.cli

docker-build:
	docker compose build

docker-run:
	docker compose run --rm ollie

docker-shell:
	docker compose run --rm ollie /bin/bash

test:
	pytest tests/ -v

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
