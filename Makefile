# Developer entry points. Humans and coding agents run the same commands.
PYTHON ?= python3
BIN ?= .venv/bin
TASK ?= Compute 30 * 24 * 3 * 0.12 and summarise our autoscaling policy

.PHONY: install format lint test check run trace clean

install:
	$(PYTHON) -m venv .venv
	$(BIN)/pip install -e ".[dev]"

format:
	$(BIN)/ruff format .

lint:
	$(BIN)/ruff check .

test:
	$(BIN)/pytest -q

check: lint test

run:
	$(BIN)/orchestrate "$(TASK)"

trace:
	mkdir -p .demo
	$(BIN)/orchestrate "$(TASK)" --json > .demo/trace.json
	@echo "wrote .demo/trace.json"

clean:
	rm -rf .pytest_cache .ruff_cache .demo build dist *.egg-info
