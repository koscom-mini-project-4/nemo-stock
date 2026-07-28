# 1. Build Stage
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt-get/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY . .
RUN pip install --no-cache-dir -e ".[dev]"


# 2. Runner Stage
FROM python:3.12-slim AS runner

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# app/main.py 경로에 맞춰 app.main:app 으로 지정
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
