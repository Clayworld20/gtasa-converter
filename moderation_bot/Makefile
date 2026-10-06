# Удобные команды для разработки и запуска.
# Пример: make install && cp .env.example .env && make run
PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

.PHONY: help venv install setup run selftest doctor test lint format cli demo clean

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

venv: ## Создать виртуальное окружение
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: venv ## Установить зависимости (включая dev)
	$(BIN)/pip install -r requirements-dev.txt

setup: install ## Первичная настройка: зависимости + .env + диагностика
	@test -f .env || (cp .env.example .env && echo "📝 Создан .env — вставьте в него BOT_TOKEN")
	-$(BIN)/python manage.py selftest --offline

selftest: ## Проверить готовность бота к запуску (добавьте ONLINE=1 для связи с Telegram)
	$(BIN)/python manage.py selftest $(if $(ONLINE),, --offline)

doctor: ## Проверить права бота в группе: make doctor CHAT=-1001234567890
	$(BIN)/python manage.py doctor --chat $(CHAT)

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
