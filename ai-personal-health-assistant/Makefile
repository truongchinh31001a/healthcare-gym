.PHONY: install dev-web dev-mobile typecheck up down

install:
	npm ci

dev-web:
	npm run dev:web

dev-mobile:
	npm run dev:mobile

typecheck:
	npm run typecheck

up:
	docker compose up --build

down:
	docker compose down

.PHONY: install-api test-api migrate smoke
install-api:
	python -m pip install -e packages/health-core -e 'apps/api[dev]'
test-api:
	cd apps/api && python -m pytest -q
migrate:
	cd apps/api && python -m alembic upgrade head
smoke:
	python scripts/smoke_module01.py --report docs/phase-5/http-smoke.json
