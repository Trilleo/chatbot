# syntax=docker/dockerfile:1

# The bot image (NoneBot). Built by .github/workflows/ci.yml and deploy.yml; NapCat's
# image is napcat/Dockerfile.
#
# Base images are pinned: every new base layer has to be uploaded to Huawei SWR in
# mainland China, which is slow (~70 KB/s from GitHub), so they change only on
# purpose. Dependabot proposes updates monthly; keep .python-version in step.

FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

# 1. Install the locked dependencies into /app/.venv.
FROM python:3.13.16-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Manifests first, so dependency installs stay cached until they change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY bot.py ./
COPY src ./src
COPY migrations ./migrations
# NoneBot's list of known keys (see the note at the top of .env.example) and the
# container's own settings.
COPY .env.example ./.env
COPY .env.docker ./
RUN python -m compileall -q src bot.py

# 2. The runtime image: the venv and the code, no build tools.
FROM python:3.13.16-slim-trixie AS bot
ARG GIT_SHA=dev
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=docker \
    HOST=0.0.0.0 \
    PORT=8080 \
    STATUS_VERSION=$GIT_SHA
RUN useradd --uid 1000 --home-dir /app --no-create-home --shell /usr/sbin/nologin bot \
    && install -d -o bot -g bot /data
WORKDIR /app
COPY --from=build /app /app
# The server's compose file ships inside the image, so deploys always use the one
# that matches the release (deploy/server/chatbot-deploy copies it out).
COPY docker-compose.yml /deploy/docker-compose.yml
# The NapCat image to run with this release: a hash of napcat/, so NapCat (and the QQ
# login) restarts only when napcat/ changes, not on every deploy.
ARG NAPCAT_TAG=local
RUN printf '%s\n' "$NAPCAT_TAG" > /deploy/napcat-tag
LABEL org.opencontainers.image.source="https://github.com/Trilleo/chatbot"
USER bot
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"]
# Applies database migrations, then runs the bot (bot.py).
CMD ["python", "bot.py"]
