FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir \
    fastapi "uvicorn[standard]" pydantic pydantic-settings sqlalchemy alembic \
    "psycopg[binary]" httpx redis celery python-dotenv "apscheduler<4"
COPY . .
RUN pip install --no-cache-dir -e .
EXPOSE 8400
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8400"]
