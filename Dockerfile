# syntax=docker/dockerfile:1
FROM dhi.io/python:3.14-debian13-dev AS builder
WORKDIR /app
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
COPY app/requirements.txt /tmp/bot-requirements.txt
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/bot-requirements.txt -r /tmp/backend-requirements.txt

FROM dhi.io/python:3.14-debian13-dev AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder --chown=65532:65532 /venv /venv
COPY --chown=65532:65532 app ./app
COPY --chown=65532:65532 backend ./backend
COPY --chown=65532:65532 run_bot.py .
RUN mkdir -p /app/data && chown 65532:65532 /app/data
ENV PATH="/venv/bin:$PATH" DATA_DIR="/app/data"
USER 65532:65532
EXPOSE 8000
CMD ["/venv/bin/python3", "-m", "uvicorn", "backend.main:app", "--host=0.0.0.0", "--port=8000"]
