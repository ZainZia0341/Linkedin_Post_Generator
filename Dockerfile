FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV API_HOST=127.0.0.1
ENV API_PORT=8001
ENV STREAMLIT_PORT=7860
ENV DYNAMODB_PORT=8000
ENV DYNAMODB_ENDPOINT_URL=http://127.0.0.1:8000
ENV LINKEDIN_API_BASE_URL=http://127.0.0.1:8001
ENV LOCAL_DB_DIR=/data/local_db

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN mkdir -p /opt/dynamodb-local \
    && curl -fsSL https://s3.us-west-2.amazonaws.com/dynamodb-local/dynamodb_local_latest.tar.gz \
    | tar -xz -C /opt/dynamodb-local

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

RUN uv run playwright install --with-deps chromium

COPY . .

EXPOSE 7860

CMD ["bash", "scripts/start_hf_space.sh"]
