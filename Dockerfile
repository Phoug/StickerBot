# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=dhi.io/python:3.14-debian13-dev
ARG NODE_IMAGE=node:22-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da
FROM ${NODE_IMAGE} AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS builder
WORKDIR /app
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
COPY app/requirements.txt /tmp/bot-requirements.txt
COPY requirements.lock /tmp/requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.lock

# Optional lightweight target; the default image retains both entrypoints.
FROM ${PYTHON_IMAGE} AS bot-builder
WORKDIR /app
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
COPY app/requirements.txt /tmp/bot-requirements.txt
COPY requirements.lock /tmp/requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -c /tmp/requirements.lock -r /tmp/bot-requirements.txt

FROM ${PYTHON_IMAGE} AS bot
WORKDIR /app
COPY --from=bot-builder --chown=65532:65532 /venv /venv
COPY --chown=65532:65532 app/bot ./app/bot
COPY --chown=65532:65532 common ./common
COPY --chown=65532:65532 run_bot.py .
ARG APP_VERSION=dev
ENV PATH="/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE="1" PYTHONUNBUFFERED="1" PYTHON_DOTENV_DISABLED="1" APP_VERSION=${APP_VERSION}
USER 65532:65532
CMD ["python3", "run_bot.py"]

FROM ${PYTHON_IMAGE} AS runtime
# DHI dev images can omit init helpers required by Debian package postinsts.
# Reinstall also restores helpers when dpkg already records the package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --reinstall init-system-helpers \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder --chown=65532:65532 /venv /venv
COPY --chown=65532:65532 app/bot ./app/bot
COPY --from=frontend --chown=65532:65532 /app/webapp ./app/webapp
COPY --chown=65532:65532 backend ./backend
COPY --chown=65532:65532 common ./common
COPY --chown=65532:65532 run_bot.py .
RUN mkdir -p /app/data /app/backups && chown 65532:65532 /app/data /app/backups
ARG APP_VERSION=dev
ENV PATH="/venv/bin:$PATH" DATA_DIR="/app/data" PYTHONDONTWRITEBYTECODE="1" PYTHONUNBUFFERED="1" PYTHON_DOTENV_DISABLED="1" APP_VERSION=${APP_VERSION}
USER 65532:65532
EXPOSE 8000
CMD ["/venv/bin/python3", "-m", "uvicorn", "backend.main:app", "--host=0.0.0.0", "--port=8000"]
