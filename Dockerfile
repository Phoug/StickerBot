# syntax=docker/dockerfile:1

# Сборка Python-зависимостей
FROM dhi.io/python:3.14-debian13-dev AS builder

WORKDIR /app

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip install --no-cache-dir -r requirements.txt


# Runtime с FFmpeg
FROM python:3.14-slim-trixie AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder --chown=65532:65532 /venv /venv
COPY --chown=65532:65532 . .

ENV PATH="/venv/bin:$PATH"

USER 65532:65532

EXPOSE 8000

CMD [ "/venv/bin/python3", "-m", "uvicorn", "main:app", "--host=0.0.0.0", "--port=8000" ]