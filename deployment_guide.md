# Deployment Guide for Aeza VPS

This guide outlines the steps to deploy the `bsky-sentiment` project on an Aeza VPS (or any Linux VPS) using Docker.

## Prerequisites

1.  **VPS**: A Linux VPS (Ubuntu 22.04 LTS recommended).
2.  **Docker**: Installed on the VPS.
3.  **Docker Compose**: Installed on the VPS.
4.  **Cerebras API Key**: You need a valid API key from Cerebras.

## 1. Initial VPS Setup

SSH into your VPS:
```bash
ssh root@<your-vps-ip>
```

Install Docker and Docker Compose (if not already installed):
```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Verify installation
docker --version
docker compose version
```

## 2. Project Setup

### Option A: Git Clone (Recommended)
If your project is in a Git repository:
```bash
git clone <your-repo-url> bskysent
cd bskysent
```

### Option B: Manual Upload
Upload your project files to the VPS using SCP or SFTP to `/root/bskysent`.

## 3. Configuration

Create the `.env` file in the `bsky-sentiment/ingestion` directory (or root, depending on where you want to keep it, but Docker expects it mapped or variables passed).

The `docker-compose.yml` expects environment variables. You can create a `.env` file in the **project root** (where `docker-compose.yml` is) for Docker Compose to pick up automatically.

Create `.env` in project root:
```bash
nano .env
```

Paste the following (adjust values as needed):

```ini
# Database
DB_USER=postgres
DB_PASSWORD=secure_password
DB_NAME=bsky_sentiment

# Bluesky Credentials (for ingestion)
BSKY_USERNAME=your.handle.bsky.social
BSKY_PASSWORD=your-app-password

# AI API Keys
OPENAI_API_KEY=sk-... (if used)
CEREBRAS_API_KEY=csk-... (REQUIRED for headlines)
```

## 4. Deployment

Build and start the services:

```bash
docker compose up -d --build
```

This command will:
1.  Build the unified Docker image.
2.  Start the Postgres database (`db`).
3.  Start the `ingestion` service (collects posts).
4.  Start the `processing` service (analyzes posts, generates headlines via Cerebras).
5.  Start the `dashboard` service (web UI).

## 5. Verification

Check the status of containers:
```bash
docker compose ps
```

View logs to ensure everything is running:
```bash
# Check all logs
docker compose logs -f

# Check processing logs (to verify Cerebras connection)
docker compose logs -f processing
```

## 6. Accessing the Dashboard

Open your browser and navigate to:
```
http://<your-vps-ip>:8000
```

You should see the Real-Time Sentiment Dashboard.

## Troubleshooting

-   **Database Connection Failed**: Ensure the `db` service is healthy before other services start. Docker Compose handles this with `depends_on`, but initial startup might take a moment.
-   **Cerebras Errors**: Check `docker compose logs processing` for "Cerebras Client initialized" or error messages. Ensure `CEREBRAS_API_KEY` is correct in `.env`.
-   **Ingestion Errors**: Check `docker compose logs ingestion` to verify Bluesky login.
