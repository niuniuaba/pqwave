.PHONY: help install dev-install test lint format clean build publish run

help:
	@echo "Available commands:"
	@echo "  make install     - Install production dependencies"
	@echo "  make dev-install - Install development dependencies"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linters"
	@echo "  make format     - Format code"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make build      - Build package"
	@echo "  make publish    - Publish to PyPI (requires twine)"
	@echo "  make run        - Run pqwave"
	@echo "  make help       - Show this help"

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"

test:
	pytest tests/

lint:
	flake8 pqwave.py
	mypy pqwave.py --ignore-missing-imports

format:
	black pqwave.py

clean:
	rm -rf build/ dist/ *.egg-info/ __pycache__/ .pytest_cache/ .mypy_cache/

build: clean
	python -m build

publish: build
	twine upload dist/*

run:
	python pqwave.py