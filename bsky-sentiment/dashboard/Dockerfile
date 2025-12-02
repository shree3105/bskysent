FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Code
# We need to copy the dashboard folder AND the ingestion folder (for .env loading if needed, though we passed env vars)
# Actually, server.py tries to load ../ingestion/.env. 
# But in Docker, we pass env vars via docker-compose, so loading .env is redundant but harmless if file missing.
# We just need the dashboard code.
COPY dashboard /app/dashboard

# Set python path to allow imports if needed (though dashboard is self contained mostly)
ENV PYTHONPATH=/app

CMD ["uvicorn", "dashboard.server:app", "--host", "0.0.0.0", "--port", "8000"]
