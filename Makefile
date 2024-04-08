.PHONY: help
help: ## This help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help

init: ## Create a venv and install dependencies
	pip3 install hatch
	hatch env create

test: ## Run tests
	hatch run test:run

ci: ## Run tests and generate junit report
	hatch run test:run --junitxml=report.xml

style_check: ## Run style checks
	hatch run style:check

style_fix: ## Run style checks and fix
	hatch run style:fmt

coverage: ## Run tests and generate coverage report
	hatch run test:run --cov-config .coveragerc --verbose --cov-report term --cov-report xml --cov=src/tunnelgraf src/tests

clean: ## Clean the project
	rm -rf dist/ .pytest_cache/
	find . -name __pycache__ -delete

dev: ## Run the app
	hatch run python3 src/tunnelgraf/ connect ./test.yml

build: ## Build the package
	hatch build

publish: ## Publish the package
	hatch publish
