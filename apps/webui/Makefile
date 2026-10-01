build:
	docker build -t webui .

up:
	make build
	@echo "Starting webui container..."
	docker run --rm -it -d --name webui -p 127.0.0.1:8501:8501 -v $(shell pwd):/app -v /var/run/docker.sock:/var/run/docker.sock -v ../:/apps webui

.PHONY: up build