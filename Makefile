# Cross-platform Makefile.
# Works with GNU Make on Windows (cmd.exe) and on macOS/Linux (sh/bash).
# Python is a hard dep and is used to paper over shell differences.

ifeq ($(OS),Windows_NT)
  PYTHON ?= python
  VENV   ?= .venv
  BIN     = $(VENV)/Scripts
else
  PYTHON ?= python3
  VENV   ?= .venv
  BIN     = $(VENV)/bin
endif
PORT   ?= 5500

.PHONY: help venv install assets run migrate clean reset-db freeze prod

help:
	@echo Targets:
	@echo   make install   - create venv, install requirements, fetch vendor assets
	@echo   make assets    - fetch/refresh vendored JS/CSS/fonts into static/vendor
	@echo   make run       - run the Flask dev server on port $(PORT)
	@echo   make migrate   - run migrate_db.py against the SQLite DB
	@echo   make reset-db  - delete instance/scripter.db (DESTRUCTIVE)
	@echo   make prod      - run via waitress (requires SECRET_KEY env var)
	@echo   make clean     - remove __pycache__ and .pyc files
	@echo   make freeze    - pip freeze to requirements.lock.txt

# `python -m venv X` is idempotent — no-op if X is already a valid venv,
# so we don't need a file-dependency tracker (which differed per-OS anyway).
venv:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: venv assets
	$(BIN)/pip install -r requirements.txt

assets:
	$(PYTHON) scripts/fetch_vendor.py

run: install
	$(BIN)/python app.py

migrate: install
	$(BIN)/python migrate_db.py

reset-db:
	$(PYTHON) -c "import pathlib; p=pathlib.Path('instance/scripter.db'); p.unlink() if p.exists() else None; print('reset-db: ok')"

freeze:
	$(BIN)/pip freeze > requirements.lock.txt

clean:
	$(PYTHON) scripts/clean_pycache.py

prod: install
	$(PYTHON) scripts/require_env.py SECRET_KEY
	$(BIN)/waitress-serve --listen=0.0.0.0:$(PORT) --threads=8 app:app
