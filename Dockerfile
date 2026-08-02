FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system bot \
    && useradd --system --gid bot --home-dir /app bot

COPY pyproject.toml README.md ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY tests ./tests

RUN pip install --no-cache-dir ".[dev]" \
    && chown -R bot:bot /app

USER bot

CMD ["python", "-m", "app.main"]

