FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Copy requirements from ingestion folder
COPY ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code (ingestion, processing, models)
COPY . .

# Run the application
CMD ["python", "main.py"]
