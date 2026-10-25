.PHONY: help pilot-start pilot-stop pilot-status web-install web-typecheck web-build web-test web-test-pipeline

help:
	@echo "Tender Review: single-app private MVP"
	@echo "  make pilot-start    Run the Next app on 127.0.0.1:3307"
	@echo "  make pilot-stop     Stop the local app"
	@echo "  make pilot-status   Check the local app"
	@echo "  make web-install    Install the Next app dependencies"
	@echo "  make web-typecheck  Type-check the app"
	@echo "  make web-test       Run extraction and provenance regression tests"
	@echo "  make web-build      Build the app"

pilot-start:
	@./scripts/pilot-start.sh

pilot-stop:
	@./scripts/pilot-stop.sh

pilot-status:
	@curl -fsS http://127.0.0.1:3307/ >/dev/null && echo "Tender Review is running at http://127.0.0.1:3307" || echo "Tender Review is not running."

web-install:
	@mkdir -p .local/npm-cache
	@npm_config_cache="$(CURDIR)/.local/npm-cache" npm ci --prefix apps/web --no-audit --no-fund --prefer-offline

web-typecheck:
	npm --prefix apps/web run typecheck

web-build:
	npm --prefix apps/web run build

web-test:
	npm --prefix apps/web test

web-test-pipeline:
	cd apps/web && npm run test:pipeline
