FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir pipenv==2025.0.4
COPY Pipfile Pipfile.lock ./
RUN pipenv install --system --deploy --ignore-pipfile
RUN pip install --no-cache-dir "boto3>=1.35,<2" "confluent-kafka>=2.12,<3" "cryptography>=46,<47" "psycopg[binary,pool]>=3.2,<4"

COPY app ./app
COPY config ./config
COPY pipeline_defs ./pipeline_defs

RUN addgroup --system mochi && adduser --system --ingroup mochi mochi \
    && mkdir -p /data/objects /data/outputs \
    && chown -R mochi:mochi /app /data

USER mochi
EXPOSE 8000

CMD ["uvicorn", "app.web_api:app", "--host", "0.0.0.0", "--port", "8000"]
