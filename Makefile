.PHONY: build run dev logs install-dev test lint format

build:
	docker-compose build

run:
	docker-compose up -d

dev:
	uvicorn app.main:app --reload --port 8006

logs:
	docker-compose logs -f

install-dev:
	pip install -r requirements-dev.txt

# Database tests need TEST_DATABASE_URL (a role that may create schemas); without it
# they are skipped. Tests create and drop their own schema; registry data is never touched.
test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .
