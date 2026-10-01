# Mounted at an identical path in the container (not aliased to /apps) so that paths the
# Makefiles compute from $(CURDIR) (APP_DATA_DIR, CONFIGS_DIR, COMPOSE_FILE, ...) are valid
# when the host's docker daemon resolves bind mounts for `make up` runner containers.
REPO_ROOT := $(shell cd ../.. && pwd)

# webui and its `make up` runner containers talk to this proxy over TCP instead of mounting the
# raw docker.sock, so neither gets EXEC/SECRETS/SWARM/NODES/PLUGINS/SYSTEM/AUTH API access.
MGMT_NETWORK := webui-mgmt-network
SOCKET_PROXY_NAME := docker-socket-proxy
SOCKET_PROXY_IMAGE := tecnativa/docker-socket-proxy:latest

build:
	docker build -t webui .

network:
	@if ! docker network ls --format '{{.Name}}' | grep -wq "$(MGMT_NETWORK)"; then \
		echo "Creating network $(MGMT_NETWORK)"; \
		docker network create "$(MGMT_NETWORK)"; \
	else \
		echo "Network $(MGMT_NETWORK) already exists"; \
	fi

socket-proxy: network ## Start the docker-socket-proxy brokering API access for webui + make-up runners
	@if [ "$$(docker inspect -f '{{.State.Running}}' $(SOCKET_PROXY_NAME) 2>/dev/null)" != "true" ]; then \
		docker rm -f $(SOCKET_PROXY_NAME) >/dev/null 2>&1 || true; \
		echo "Starting $(SOCKET_PROXY_NAME)..."; \
		docker run -d --name $(SOCKET_PROXY_NAME) \
			--network $(MGMT_NETWORK) \
			-v /var/run/docker.sock:/var/run/docker.sock:ro \
			-e CONTAINERS=1 -e IMAGES=1 -e NETWORKS=1 -e VOLUMES=1 -e BUILD=1 -e INFO=1 -e POST=1 \
			$(SOCKET_PROXY_IMAGE); \
	else \
		echo "$(SOCKET_PROXY_NAME) already running"; \
	fi

up: socket-proxy
	make build
	@echo "Starting webui container..."
	docker run --rm -it -d --name webui -p 127.0.0.1:8501:8501 \
		--network $(MGMT_NETWORK) \
		-v $(shell pwd):/app \
		-v $(REPO_ROOT):$(REPO_ROOT) \
		-e REPO_ROOT=$(REPO_ROOT) \
		-e APPS_DIR=$(REPO_ROOT)/apps \
		-e WEBUI_MGMT_NETWORK=$(MGMT_NETWORK) \
		-e DOCKER_HOST=tcp://$(SOCKET_PROXY_NAME):2375 \
		webui

down: ## Stop webui and the docker-socket-proxy
	-docker rm -f webui $(SOCKET_PROXY_NAME) 2>/dev/null

.PHONY: up build network socket-proxy down