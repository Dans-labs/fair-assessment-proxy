FROM python:3.12.8-bookworm

ENV PYTHONPATH=/app/src

WORKDIR /app

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the application into the container.
COPY src ./src
COPY config/config.toml ./config/config.toml
COPY pyproject.toml .
COPY LICENSE .
COPY README.md .
COPY uv.lock .

RUN mkdir -p /app/cache

RUN pip install uvicorn
RUN uv sync --locked
CMD ["sh", "-c", "uv run uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]

