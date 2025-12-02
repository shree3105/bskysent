import asyncio
import os
import json
import logging
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Dashboard")

# Load Env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../bsky-sentiment/ingestion/.env'))
logger.info(f"Loading .env from: {env_path}")
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("CRITICAL: DATABASE_URL not found in .env!")
else:
    logger.info("DATABASE_URL loaded successfully.")

# DB Setup
try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        logger.info("DB Connection Successful!")
except Exception as e:
    logger.error(f"DB Connection Failed: {e}")

async def get_top_clusters():
                        for pt_time, pt_count in points.items():
                            if abs((t - pt_time).total_seconds()) < 30: # Within 30s window
                                val = pt_count
                                break
                        filled_data.append(val)
                        
                elif interval_type == '24h':
                    # Last 24 hours
                    start_time = now - timedelta(hours=24)
                    start_time = start_time.replace(minute=0, second=0, microsecond=0)
                    for i in range(25):
                        t = start_time + timedelta(hours=i)
                        val = 0
                        for pt_time, pt_count in points.items():
                            if abs((t - pt_time).total_seconds()) < 1800: # Within 30m window
                                val = pt_count
                                break
                        filled_data.append(val)
                        
                elif interval_type == '7d':
                    # Last 7 days
                    start_time = now - timedelta(days=7)
                    start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                    for i in range(8):
                        t = start_time + timedelta(days=i)
                        val = 0
                        for pt_time, pt_count in points.items():
                            if abs((t - pt_time).total_seconds()) < 43200: # Within 12h window
                                val = pt_count
                                break
                        filled_data.append(val)
                        
                return filled_data

            def format_rows(rows, interval_type):
                data = []
                for row in rows:
                    sparkline_raw = row[6] if row[6] else []
                    sparkline_filled = fill_gaps(sparkline_raw, interval_type)
                    
                    label = row[1]
                    # Frontend Fallback for "New Topic"
                    if label == "New Topic" and row[5] and len(row[5]) > 0:
                        # Get most recent post content
                        latest_post = row[5][0]
                        # Handle both string (old format) and object (new format)
                        content = latest_post['content'] if isinstance(latest_post, dict) else latest_post
                        # Truncate to keep it clean
                        label = f"New: {content[:60]}..." if len(content) > 60 else f"New: {content}"

                    data.append({
                        "id": row[0],
                        "label": label,
                        "count": row[2],
                        "updated": row[3].strftime("%Y-%m-%d %H:%M") if row[3] else "",
                        "summary": row[4] if row[4] else "No summary available.",
                        "recent_posts": row[5] if row[5] else [],
                        "sparkline": sparkline_filled,
                        "rating": row[7] if len(row) > 7 and row[7] else None # Row 7 is the new rating object
                    })
                return data

            return {
                "latest_updates": format_rows(result_latest.fetchall(), '1h'),
                "last_hour": format_rows(result_1h.fetchall(), '1h'),
                "last_24h": format_rows(result_24h.fetchall(), '24h'),
                "last_7d": format_rows(result_7d.fetchall(), '7d'),
                "system_status": system_status
            }
    except Exception as e:
        logger.error(f"Error fetching clusters: {e}")
        return {"last_hour": [], "last_24h": [], "last_7d": []}

app = FastAPI()

# Store connected clients
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

@app.get("/")
async def get():
    # Serve the HTML file directly
    with open(os.path.join(os.path.dirname(__file__), "templates/index.html"), "r") as f:
        return HTMLResponse(content=f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial data immediately
        data = await get_top_clusters()
        await websocket.send_text(json.dumps(data))
        
        while True:
            # Keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def broadcast_updates():
    """Background task to push updates."""
    last_data = None
    while True:
        current_data = await get_top_clusters()
        
        # Only broadcast if data changed
        if current_data != last_data:
            await manager.broadcast(json.dumps(current_data))
            last_data = current_data
            
        await asyncio.sleep(0.5) # Update every 500ms

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_updates())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
