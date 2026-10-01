.PHONY: help infra-up infra-down api-install api-dev api-test api-lint api-migrate api-migrate-down api-migrate-new web-install web-dev web-typecheck docker-build docker-worker-build deploy-smoke

help:
	@echo "Tender Compliance Engine"
	@echo "  make infra-up       Start Postgres, Redis and MinIO"
	@echo "  make infra-down     Stop local infrastructure"
	@echo "  make api-install    Install API package + dev dependencies"
	@echo "  make api-dev        Run FastAPI with reload"
	@echo "  make api-test       Run backend tests"
	@echo "  make api-lint       Run Ruff"
	@echo "  make api-migrate    Apply Alembic migrations (alembic upgrade head)"
	@echo "  make api-migrate-down  Rollback one migration (alembic downgrade -1)"
	@echo "  make api-migrate-new  Create a new migration (message=...)"
	@echo "  make web-install    Install frontend dependencies"
	@echo "  make web-dev        Run Next.js development server"
	@echo "  make web-typecheck  Run TypeScript type checking"
	@echo "  make docker-build   Build API Docker image"
	@echo "  make docker-worker-build  Build worker Docker image"
	@echo "  make deploy-smoke   Run deployment smoke tests"

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

api-migrate:
	cd apps/api && alembic upgrade head

api-migrate-down:
	cd apps/api && alembic downgrade -1

api-migrate-new:
	cd apps/api && alembic revision -m "$(message)"

web-install:
	cd apps/web && npm install

web-dev:
	cd apps/web && npm run dev

web-typecheck:
	cd apps/web && npm run typecheck

docker-build:
	docker build -f apps/api/Dockerfile -t tender-compliance-api:dev apps/api

docker-worker-build:
	docker build -f apps/api/Dockerfile.worker -t tender-compliance-worker:dev apps/api

deploy-smoke:
	@echo "Running deployment smoke tests..."
	@curl -sf http://localhost:8000/health || (echo "Health check FAILED" && exit 1)
	@curl -sf -o /dev/null -w "%{http_code}" http://localhost:8000/projects | grep -q 401 || (echo "Auth check FAILED" && exit 1)
	@curl -sf http://localhost:8000/metrics | python -c "import sys,json; d=json.load(sys.stdin); assert 'gauges' in d" || (echo "Metrics check FAILED" && exit 1)
	@echo "All smoke tests passed."
