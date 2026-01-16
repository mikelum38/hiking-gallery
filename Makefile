.PHONY: help install test lint security clean docker-build docker-run deploy

# Help
help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Installation
install: ## Installe les dépendances
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# Tests
test: ## Lance les tests unitaires avec couverture
	pytest --cov=app --cov-report=html --cov-report=term-missing -v

# Linting
lint: ## Vérifie la qualité du code
	flake8 app.py tests/ --count --select=E9,F63,F7,F82 --show-source --statistics
	black --check app.py tests/
	isort --check-only app.py tests/

# Sécurité
security: ## Lance les scans de sécurité
	safety check
	bandit -r app.py -f text

# Nettoyage
clean: ## Nettoie les fichiers temporaires
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf dist/
	rm -rf build/

# Docker
docker-build: ## Construit l'image Docker
	docker build -t hiking-gallery .

docker-run: ## Lance le conteneur Docker
	docker run -p 5000:5000 --env-file .env hiking-gallery

docker-push: ## Push l'image Docker sur le registry
	docker build -t ghcr.io/$(shell basename $(pwd)):latest .
	docker push ghcr.io/$(shell basename $(pwd)):latest

# Déploiement
deploy-staging: ## Déploie en staging
	vercel

deploy-prod: ## Déploie en production
	vercel --prod

# Développement
dev: ## Lance le serveur de développement
	python app.py

# CI complet
ci: ## Lance tout le pipeline CI
	make lint
	make test
	make security
	make docker-build

# Production ready
pre-deploy: ## Vérifications avant déploiement
	make ci
	@echo "✅ Pré-déploiement validé"

# Full workflow
all: clean install lint test security docker-build
	@echo "🚀 Pipeline complet terminé"
