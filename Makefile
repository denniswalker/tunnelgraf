.PHONY: help build install test test-verbose test-race test-integration coverage lint vet fmt fmt-check tidy clean dev run

BINARY := tunnelgraf
PKG    := ./cmd/tunnelgraf
BIN    := bin/$(BINARY)

help: ## This help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help

build: ## Build the binary into ./bin
	@mkdir -p bin
	go build -o $(BIN) $(PKG)

install: ## Install the binary into $GOBIN / $GOPATH/bin
	go install $(PKG)

test: ## Run unit tests
	go test ./...

test-verbose: ## Run unit tests with verbose output
	go test -v ./...

test-race: ## Run unit tests with race detector and coverage
	go test -race -cover ./...

test-integration: ## Run integration tests (requires Docker)
	go test -tags integration -v -count=1 -timeout 10m ./tests/integration/...

coverage: ## Run tests and write coverage.out
	go test -coverprofile=coverage.out ./...
	go tool cover -func=coverage.out

lint: ## Run golangci-lint (must be installed)
	golangci-lint run ./...

vet: ## Run go vet
	go vet ./...

fmt: ## Format Go sources
	gofmt -s -w .

fmt-check: ## Check formatting without modifying files
	@out=$$(gofmt -s -l .); \
	if [ -n "$$out" ]; then \
	  echo "files need formatting:"; echo "$$out"; exit 1; \
	fi

tidy: ## Tidy go.mod / go.sum
	go mod tidy

clean: ## Remove build artifacts
	rm -rf bin/ coverage.out

dev: ## Run against TUNNELGRAF_PROFILE with debug logging
	@if [ -z "$$TUNNELGRAF_PROFILE" ]; then \
	  echo "Error: TUNNELGRAF_PROFILE is not set"; exit 1; \
	fi
	LOG_LEVEL=DEBUG go run $(PKG) connect

run: ## Run the CLI (pass ARGS="..."), e.g. make run ARGS="show -p profile.yml"
	go run $(PKG) $(ARGS)
