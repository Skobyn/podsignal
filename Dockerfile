FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the podsignal package (existing pipeline)
COPY podsignal/ /app/podsignal/
COPY pyproject.toml /app/pyproject.toml

# Copy the API
COPY api/ /app/api/

# Copy the built UI
COPY ui/dist/ /app/ui/dist/

# Copy config defaults
COPY config.yaml /app/config.yaml
COPY podcasts.yaml /app/podcasts.yaml

EXPOSE 8080

ENV PORT=8080
ENV PYTHONPATH=/app

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
