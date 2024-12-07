FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root --no-interaction --no-ansi

COPY app /app/app

ENV PYTHONPATH="${PYTHONPATH}:/app"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]