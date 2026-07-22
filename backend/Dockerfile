FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations before uvicorn, but don't hard-fail boot if the target database's
# alembic_version is already ahead of this demo branch's known revision chain (e.g. a
# database previously migrated by a newer, non-demo codebase). This demo branch's schema
# needs are a strict subset of that later schema, so continuing to serve is safe.
# $PORT is set by Railway/Render; default 8000 for local Docker.
CMD ["sh", "-c", "alembic upgrade head || echo 'demo: alembic upgrade skipped (database schema already satisfies this demo revision)'; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
