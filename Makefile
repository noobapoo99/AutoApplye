.PHONY: install dev test lint migrate demo clean logs help

help:
	@echo ""
	@echo "  AutoApply — Makefile targets"
	@echo "  ─────────────────────────────────────────────"
	@echo "  make install   Install Python + Node deps"
	@echo "  make dev       Start all services (Docker)"
	@echo "  make test      Run backend test suite"
	@echo "  make lint      Lint backend with ruff"
	@echo "  make migrate   Run DB migrations (Alembic)"
	@echo "  make demo      Dry-run pipeline simulation"
	@echo "  make logs      Tail Docker logs"
	@echo "  make clean     Remove containers + volumes"
	@echo ""

install:
	cd backend && pip install -r requirements.txt
	cd backend && playwright install chromium
	cd frontend && npm install

dev:
	docker-compose up --build

test:
	cd backend && python -m pytest tests/ -v --asyncio-mode=auto

lint:
	cd backend && python -m ruff check . --fix

migrate:
	cd backend && alembic upgrade head

demo:
	python scripts/demo_pipeline.py --dry-run

logs:
	docker-compose logs -f

clean:
	docker-compose down -v --remove-orphans
