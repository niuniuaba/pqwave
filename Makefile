# Override with `make PYTHON=./venv/bin/python test` when using a venv.
PYTHON ?= python

.PHONY: help install dev-install test test-isolated lint format format-check clean build publish run

help:
	@echo "Available commands:"
	@echo "  make install     - Install production dependencies"
	@echo "  make dev-install - Install development dependencies"
	@echo "  make test        - Run the test suite (pytest, one process)"
	@echo "  make test-isolated - Run every test file in its own subprocess"
	@echo "  make lint        - Run flake8 + mypy"
	@echo "  make format      - Format code with black"
	@echo "  make format-check - Check formatting without rewriting files"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make build      - Build package"
	@echo "  make publish    - Publish to PyPI (requires twine)"
	@echo "  make run        - Run pqwave"
	@echo "  make help       - Show this help"

install:
	$(PYTHON) -m pip install -e .

dev-install:
	$(PYTHON) -m pip install -e ".[dev]"

# `tests/` holds the .raw/.qraw fixtures, not the test code; the suite lives in
# pqwave/tests/, which pyproject's testpaths now points at.
test:
	pytest

# Each test file in its own process: this is how the suite was run before, and it
# still matters for the Qt-teardown and TCP-binding cases.
test-isolated:
	$(PYTHON) pqwave.py --test

# mypy must NOT be handed pqwave.py and pqwave/ together: the root pqwave.py
# wrapper and the pqwave/ package both claim the module name "pqwave", and mypy
# aborts with 'Duplicate module named "pqwave"' before checking anything. The
# wrapper is a two-line shim; the package is what needs type-checking.
lint:
	flake8 pqwave/
	mypy pqwave/ --ignore-missing-imports

format:
	black pqwave/

format-check:
	black --check --diff pqwave/

clean:
	rm -rf build/ dist/ *.egg-info/ __pycache__/ .pytest_cache/ .mypy_cache/

build: clean
	$(PYTHON) -m build

publish: build
	twine upload dist/*

run:
	$(PYTHON) pqwave.py