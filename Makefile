export PYTHONPATH := $(PWD)/src:$(PYTHONPATH)
PORT ?= 8080
HOST_PORT ?= 8080
ORG_NAME := eosc-data-commons
IMAGE_NAME := $(ORG_NAME)/tool-registry
VERSION = $(shell grep '^version' pyproject.toml | head -1 | cut -d '"' -f2)
PLATFORMS := linux/amd64,linux/arm64

.PHONY: run sync force-sync install git-tag git-push-tag docker-login docker-check-login docker-build docker-push docker-release print-version bump
run: sync
	uvicorn src.main:app --host 0.0.0.0 --port $(PORT) --reload

install:
	mkdir -p cache
	uv sync --frozen --no-cache

.PHONY: re-install install
re-install: clean
	mkdir -p cache
	uv sync

.PHONY: clean
clean:
	rm -rf ./.venv
	rm uv.lock 2> /dev/null || true
	rm -rf ./cache

token:
	uv run src/get_admin_token.py

sync:
	uv sync 

force-sync:
	rm uv.lock
	uv sync --force-reinstall

print-version:
	@echo "Version: $(VERSION)"

bump:
	uv version --bump patch
	uv lock
	V=$$(grep '^version' pyproject.toml | head -1 | cut -d '"' -f2); \
	git commit -am "Bump version to v$$V"
	git push

git-tag:
	@echo "Tagging version v$(VERSION)"
	@git diff --quiet || (echo "ERROR: Working tree not clean"; exit 1)
	@git tag -a v$(VERSION) -m "Release v$(VERSION)"

git-push-tag:
	@git push origin v$(VERSION)

docker-login:
	@if [ -z "$$GITHUB_TOKEN" ]; then \
		echo "ERROR: GITHUB_TOKEN not set"; \
		exit 1; \
	fi
	@if [ -z "$$GITHUB_USER" ]; then \
		echo "ERROR: GITHUB_USER not set"; \
		exit 1; \
	fi
	@echo "Logging in to GHCR as $(GITHUB_USER)"
	@echo $$GITHUB_TOKEN | docker login ghcr.io -u $(GITHUB_USER) --password-stdin

docker-check-login:
	@if docker system info >/dev/null 2>&1; then \
		if grep -q '"ghcr.io"' $$HOME/.docker/config.json 2>/dev/null; then \
			echo "Logged in to ghcr.io"; \
		else \
			echo "Not logged in to ghcr.io"; \
			exit 1; \
		fi \
	else \
		echo "Docker daemon not running"; \
		exit 1; \
	fi

# docker-build:
# 	@echo "Building $(IMAGE_NAME):$(VERSION)"
# 	uv lock
# 	docker build --platform linux/amd64 -t ghcr.io/$(IMAGE_NAME):$(VERSION) .
# 	docker tag ghcr.io/$(IMAGE_NAME):$(VERSION) ghcr.io/$(IMAGE_NAME):latest

docker-build:
	@echo "Building $(IMAGE_NAME):$(VERSION)"
	uv lock
	docker buildx build \
		--platform $(PLATFORMS) \
		-t ghcr.io/$(IMAGE_NAME):$(VERSION) \
		-t ghcr.io/$(IMAGE_NAME):latest \
		--push \
		.

docker-build-dev:
	@echo "Building $(IMAGE_NAME):$(VERSION)-dev"
	docker build --platform linux/amd64 -t ghcr.io/$(IMAGE_NAME):$(VERSION)-dev .

docker-push: docker-build
	@echo "Pushing $(IMAGE_NAME):$(VERSION)"
	docker push ghcr.io/$(IMAGE_NAME):$(VERSION)
	docker push ghcr.io/$(IMAGE_NAME):latest

docker-release: docker-build
	@echo "Released $(IMAGE_NAME):$(VERSION)"

docker-run:
	docker run -e PORT=$(PORT) -p $(HOST_PORT):$(PORT)  -v ./config:/app/config ghcr.io/$(IMAGE_NAME):latest

release: print-version docker-login docker-check-login git-tag git-push-tag docker-release
	@echo "Released version $(VERSION) to GitHub"
