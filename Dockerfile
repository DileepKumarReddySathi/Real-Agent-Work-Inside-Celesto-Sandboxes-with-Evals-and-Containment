FROM python:3.11-slim

WORKDIR /app

# Install curl for container healthcheck and libpq dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code, reports, logs, and seeds
COPY src/ ./src/
COPY seeds/ ./seeds/
COPY reports/ ./reports/
COPY logs/ ./logs/

ENV PYTHONPATH=/app
ENV API_PORT=8080

EXPOSE 8080

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8080"]
