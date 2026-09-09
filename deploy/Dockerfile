FROM python:3.12-slim AS dependencies
WORKDIR /app
ENV POETRY_VIRTUALENVS_IN_PROJECT=true PIP_NO_CACHE_DIR=1
RUN pip install poetry==2.1.3
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

FROM dependencies AS test
RUN poetry install --no-root --no-interaction --no-ansi
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini pytest.ini ./
COPY tests ./tests
CMD ["pytest", "-q"]

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 app
COPY --from=dependencies /app/.venv /app/.venv
COPY app ./app
COPY family_cli ./family_cli
COPY alembic ./alembic
COPY alembic.ini ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"]
CMD ["python", "-m", "family_cli.run", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
