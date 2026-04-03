.PHONY: help install dev-install test lint format build-web build-agent build-bot build-all up down logs web bot agent clean shell dev-up dev-down dev-logs

# Default target
help:
	@echo "OSINT Relay - Makefile Commands"
	@echo "================================"
	@echo ""
	@echo "Local Development (Python):"
	@echo "  make install       - Install dependencies (production)"
	@echo "  make dev-install   - Install dependencies (development)"
	@echo "  make run           - Run CLI locally"
	@echo "  make run-offline   - Run CLI locally in offline mode"
	@echo "  make test          - Run tests"
	@echo "  make lint          - Run linting"
	@echo "  make format        - Format code"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make build-all     - Build all Docker images"
	@echo "  make build-web     - Build web server image"
	@echo "  make build-agent   - Build CLI agent image"
	@echo "  make build-bot     - Build bot image"
	@echo "  make up            - Start web and bot services (production)"
	@echo "  make up-web        - Start web service only (production)"
	@echo "  make up-bot        - Start bot service only (production)"
	@echo "  make down          - Stop all services"
	@echo "  make logs          - View logs from all services"
	@echo "  make logs-web      - View web service logs"
	@echo "  make logs-bot      - View bot service logs"
	@echo ""
	@echo "Docker Development:"
	@echo "  make dev-up        - Start dev services with code mounting"
	@echo "  make dev-down      - Stop dev services"
	@echo "  make dev-logs      - View dev service logs"
	@echo ""
	@echo "Docker CLI Commands:"
	@echo "  make agent         - Run CLI agent in Docker (interactive)"
	@echo "  make agent-offline - Run CLI agent in Docker (offline)"
	@echo "  make shell         - Open shell in web container"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean         - Clean Docker resources"
	@echo "  make prune         - Prune all Docker resources"

# Local Development
install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements-dev.txt
	pip install -r requirements-web.txt
	pip install -r requirements.txt

run:
	python -m socialosintagent.main

run-offline:
	python -m socialosintagent.main --offline

run-stdin:
	cat query.json | python -m socialosintagent.main --stdin

test:
	pytest tests/ -v

lint:
	python -m py_compile socialosintagent/*.py
	@echo "Syntax check passed"

format:
	@echo "No auto-formatter configured. Please format manually."

# Docker Build
build-all: build-web build-agent build-bot
	@echo "All Docker images built successfully"

build-web:
	docker build -t osint-web -f Dockerfile.web .

build-agent:
	docker build -t osint-agent -f Dockerfile.agent .

build-bot:
	docker build -t osint-bot -f Dockerfile.bot .

# Docker Compose
up:
	docker compose up -d web bot

up-web:
	docker compose up -d web

up-bot:
	docker compose up -d bot

down:
	docker compose down

logs:
	docker compose logs -f

logs-web:
	docker compose logs -f web

logs-bot:
	docker compose logs -f bot

# Docker CLI
agent:
	docker compose run --rm -it agent

agent-offline:
	docker compose run --rm -it agent --offline

agent-stdin:
	docker compose run --rm -T agent --stdin < query.json

shell:
	docker compose exec web bash

# Maintenance
clean:
	docker compose down -v
	docker system prune -f

prune:
	docker system prune -a -f --volumes

# Docker Development (with code mounting)
dev-up:
	docker compose -f docker-compose.dev.yml up -d

dev-down:
	docker compose -f docker-compose.dev.yml down

dev-logs:
	docker compose -f docker-compose.dev.yml logs -f
