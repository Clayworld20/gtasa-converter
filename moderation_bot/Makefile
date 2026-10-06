# Удобные команды для разработки и запуска.
# Пример: make install && cp .env.example .env && make run
PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

.PHONY: help venv install run test lint format cli demo clean

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

venv: ## Создать виртуальное окружение
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: venv ## Установить зависимости (включая dev)
	$(BIN)/pip install -r requirements-dev.txt

run: ## Запустить бота (нужен .env)
	$(BIN)/python -m bot

test: ## Прогнать тесты
	$(BIN)/python -m pytest

lint: ## Проверить код линтером
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: ## Отформатировать код
	$(BIN)/ruff check . --fix
	$(BIN)/ruff format .

cli: ## Показать настройки всех чатов (python manage.py list)
	$(BIN)/python manage.py list

demo: ## Показать, какие сообщения будут удалены (без Telegram)
	$(BIN)/python manage.py demo

clean: ## Удалить кэши
	rm -rf .pytest_cache .ruff_cache **/__pycache__
