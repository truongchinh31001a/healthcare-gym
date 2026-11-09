FROM python:3.12-slim
WORKDIR /service
COPY packages/health-core /packages/health-core
RUN pip install --no-cache-dir /packages/health-core
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 health && mkdir /private-storage && chown health:health /private-storage
USER health
ENV STORAGE_DIR=/private-storage
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
