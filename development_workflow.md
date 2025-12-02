# Development & Deployment Workflow

This guide explains how to develop locally and push updates to your Aeza VPS.

## 1. Local Development Cycle

Develop and test your changes on your local machine before deploying.

### Step 1: Make Changes
Edit your code (e.g., `processing/pipeline.py`, `dashboard/server.py`).

### Step 2: Run Locally
Use Docker Compose to run the full stack locally. This ensures it behaves exactly like production.

```bash
# Build and start all services
docker compose up --build
```

*   **Dashboard**: Access at `http://localhost:8000`.
*   **Logs**: Watch the terminal output for errors.
*   **Stop**: Press `Ctrl+C` to stop.

### Step 3: Verify
*   Check if the dashboard loads.
*   Check if the pipeline is processing posts (logs).
*   Check if Cerebras is generating headlines (logs).

---

## 2. Pushing Updates to VPS

We recommend using **Git** (GitHub, GitLab, etc.) to sync code.

### Step 1: Commit & Push (Local)
Once your local changes are working:

```bash
git add .
git commit -m "Description of changes"
git push origin main
```

### Step 2: Deploy on VPS
SSH into your VPS and pull the changes.

```bash
# 1. Connect to VPS
ssh root@<your-vps-ip>

# 2. Navigate to project folder
cd bskysent

# 3. Pull latest code
git pull origin main

# 4. Rebuild and Restart Containers
# This command rebuilds images with new code and restarts services with minimal downtime.
docker compose up -d --build --remove-orphans
```

### Step 3: Verify Deployment
Check logs to ensure the new version started correctly.

```bash
docker compose logs -f --tail=100
```

---

## Alternative: Manual Sync (No Git)
If you are not using Git, you can copy files directly using `scp`.

```bash
# Run this from your LOCAL machine
scp -r ./bsky-sentiment root@<your-vps-ip>:/root/bskysent/
scp -r ./dashboard root@<your-vps-ip>:/root/bskysent/
scp docker-compose.yml root@<your-vps-ip>:/root/bskysent/

# Then SSH in and restart
ssh root@<your-vps-ip> "cd bskysent && docker compose up -d --build"
```
