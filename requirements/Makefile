
.PHONY: dev lint test build run-api run-agents seed demo

dev:
	pip install -r requirements.txt

lint:
	ruff check . && mypy --ignore-missing-imports .

test:
	pytest -q

build:
	docker build -t mcc-api:dev services/api || true
	docker build -t mcc-agents:dev services/agents || true

run-api:
	uvicorn services.api.main:app --reload --port 8080

run-agents:
	python services/agents/run_workers.py

seed:
	python scripts/db_seed.py

demo:
	python scripts/run_demo.py

export:
	python scripts/export_mysql_mcc_data.py

seedcsv:
	python scripts/seed_from_csv.py
