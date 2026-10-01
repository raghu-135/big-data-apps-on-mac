# Helper image used by webui to run `make up` for a service via the mounted docker.sock.
# Needs the Docker CLI (with the compose plugin) plus make/bash/coreutils for Makefile.common & resolve-deps.sh.
FROM docker:27-cli
RUN apk add --no-cache make bash coreutils ncurses
