FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

RUN pip install --no-cache-dir .

EXPOSE 8011

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8011"]
