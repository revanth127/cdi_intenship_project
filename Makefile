PYTHON ?= $(shell which python3)
ifeq ($(wildcard backend/.venv/bin/python),backend/.venv/bin/python)
  PYTHON = backend/.venv/bin/python
  PYTEST = backend/.venv/bin/pytest
else
  PYTEST = pytest
endif

.PHONY: help benchmark demo-state test test-backend test-frontend up dev down reset

help:
	@echo "Available commands:"
	@echo "  make up             Start all services with Docker Compose"
	@echo "  make dev            Start services in development mode with reload and volume mount"
	@echo "  make down           Stop Docker Compose services"
	@echo "  make reset          Tear down services and delete database volume"
	@echo "  make demo-state     Apply Section 5 transactions to the clean seed"
	@echo "  make benchmark      Run Section 5 benchmark validation suite"
	@echo "  make test           Run all backend and frontend tests"
	@echo "  make test-backend   Run pytest test suite"
	@echo "  make test-frontend  Run vitest frontend suite"

benchmark:
	DATABASE_URL=$${DATABASE_URL:-postgresql+psycopg2://postgres:postgres@localhost:5434/order_to_audit} $(PYTHON) scripts/run_benchmark.py

demo-state:
	DATABASE_URL=$${DATABASE_URL:-postgresql+psycopg2://postgres:postgres@localhost:5434/order_to_audit} $(PYTHON) scripts/apply_benchmark_state.py

test: test-backend test-frontend

test-backend:
	$(PYTEST) backend/tests

test-frontend:
	npm --prefix frontend test -- --run

up:
	docker compose up --build

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

down:
	docker compose down

reset:
	docker compose down -v
