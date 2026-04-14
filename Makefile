PYTHON ?= python3
VENV   ?= .venv
BIN     = $(VENV)/bin
PORT   ?= 5500

.PHONY: help venv install assets run migrate clean reset-db freeze prod

help:
	@echo "Targets:"
	@echo "  make install   - create venv, install requirements, fetch vendor assets"
	@echo "  make assets    - fetch/refresh vendored JS/CSS/fonts into static/vendor"
	@echo "  make run       - run the Flask dev server on port $(PORT)"
	@echo "  make migrate   - run migrate_db.py against the SQLite DB"
	@echo "  make reset-db  - delete instance/scripter.db (DESTRUCTIVE)"
	@echo "  make prod      - run via waitress (requires SECRET_KEY env var)"
	@echo "  make clean     - remove __pycache__ and .pyc files"
	@echo "  make freeze    - pip freeze > requirements.lock.txt"

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

venv: $(VENV)/bin/activate

install: venv assets
	$(BIN)/pip install -r requirements.txt

assets:
	$(PYTHON) scripts/fetch_vendor.py

run: install
	FLASK_APP=app.py $(BIN)/python app.py

migrate: install
	$(BIN)/python migrate_db.py

reset-db:
	rm -f instance/scripter.db

freeze:
	$(BIN)/pip freeze > requirements.lock.txt

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

prod: install
	@if [ -z "$$SECRET_KEY" ]; then \
		echo "ERROR: SECRET_KEY env var not set — refusing to start in prod"; \
		exit 1; \
	fi
	$(BIN)/waitress-serve --listen=0.0.0.0:$(PORT) --threads=8 app:app
