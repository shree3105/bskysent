FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (libpq needed for psycopg2)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Install specific dashboard dependencies
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy necessary code folders
# We mount these via volume in compose, but copying ensures the image runs standalone too
COPY dashboard /app/dashboard
COPY bsky-sentiment/ingestion/.env /app/bsky-sentiment/ingestion/.env

# Create the same folder structure expected by python imports if needed, 
# or just ensure PYTHONPATH is set correctly. 
# The server.py imports like: `from dotenv import load_dotenv` (standard)
# But it loads env from: `../bsky-sentiment/ingestion/.env`
# So we need to preserve that relative structure if we want `server.py` to run unmodified.

# Let's recreate the structure:
# /app/dashboard
# /app/bsky-sentiment/ingestion/.env

WORKDIR /app

# Expose port
EXPOSE 8000

# Command
CMD ["uvicorn", "dashboard.server:app", "--host", "0.0.0.0", "--port", "8000"]
