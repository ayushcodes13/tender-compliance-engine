.PHONY: help infra-up infra-down api-install api-dev api-test api-lint web-install web-dev web-typecheck

help:
	@echo "Tender Compliance Engine"
	@echo "  make infra-up       Start Postgres, Redis and MinIO"
	@echo "  make infra-down     Stop local infrastructure"
	@echo "  make api-install    Install API package + dev dependencies"
	@echo "  make api-dev        Run FastAPI with reload"
	@echo "  make api-test       Run backend tests"
	@echo "  make api-lint       Run Ruff"
	@echo "  make web-install    Install frontend dependencies"
	@echo "  make web-dev        Run Next.js development server"
	@echo "  make web-typecheck  Run TypeScript type checking"

infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

api-install:
	python -m pip install -e 'apps/api[dev]'

api-dev:
	cd apps/api && uvicorn tender_compliance_api.main:app --reload --host 0.0.0.0 --port 8000

api-test:
	cd apps/api && pytest

api-lint:
	cd apps/api && ruff check .

web-install:
	cd apps/web && npm install

web-dev:
	cd apps/web && npm run dev

web-typecheck:
	cd apps/web && npm run typecheck
