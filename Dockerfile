# Imagen de producción de la API MetriK (Cloud Run)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY ml/modelos ./ml/modelos

RUN useradd --create-home --uid 1000 metrik
USER metrik

EXPOSE 8080

# Cloud Run inyecta PORT; --proxy-headers para respetar https detrás del balanceador
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
