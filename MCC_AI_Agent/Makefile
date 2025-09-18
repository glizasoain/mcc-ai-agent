VENV_PY=.venv/bin/python
VENV_PIP=.venv/bin/pip
VENV_UVICORN=.venv/bin/uvicorn

.PHONY: dev run stop install-mysql test

dev:
	python3 -m venv .venv
	$(VENV_PY) -m pip install -r requirements.txt

run:
	$(VENV_UVICORN) app.main:app --reload --port 8090

stop:
	- lsof -ti tcp:8090 | xargs kill -9

install-mysql:
	$(VENV_PIP) install mysql-connector-python

test:
	$(VENV_PY) -m pytest -q
