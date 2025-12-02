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
    """Fetch top clusters split by time window"""
    try:
        with engine.connect() as conn:
            # 1. Last Hour (True Trending Velocity)
            result_1h = conn.execute(text("""
                SELECT c.id, c.label, COUNT(rp.uri) as post_count, MAX(rp.created_at) as display_time, c.summary,
                       (SELECT json_agg(t) FROM (
                           SELECT rp2.content, rp2.uri, rp2.author_did
                           FROM processed_posts pp2 
                           JOIN raw_posts rp2 ON pp2.uri = rp2.uri 
                           WHERE pp2.topic_id = c.id 
                           ORDER BY rp2.created_at DESC 
                           LIMIT 3
                       ) t) as recent_posts,
                       (
                           SELECT json_agg(EXTRACT(EPOCH FROM created_at)) 
                           FROM raw_posts rp3 
                           JOIN processed_posts pp3 ON rp3.uri = pp3.uri 
                           WHERE pp3.topic_id = c.id AND rp3.created_at >= NOW() - INTERVAL '1 hour'
                       ) as sparkline,
                       (SELECT row_to_json(r) FROM (SELECT rating_score, sentiment, reasoning FROM topic_ratings WHERE cluster_id = c.id ORDER BY rated_at DESC LIMIT 1) r) as rating
                FROM clusters c
                JOIN processed_posts pp ON c.id = pp.topic_id
                JOIN raw_posts rp ON pp.uri = rp.uri
                WHERE c.is_active = TRUE 
                  AND rp.created_at >= NOW() - INTERVAL '1 hour'
                GROUP BY c.id, c.label, c.summary
                ORDER BY post_count DESC
                LIMIT 10
            """))

            # 2. Latest Updates (Live Feed) - Just the very latest active topics
            result_latest = conn.execute(text("""
                SELECT c.id, c.label, COUNT(rp.uri) as post_count, MAX(rp.created_at) as display_time, c.summary,
                       (SELECT json_agg(t) FROM (
                           SELECT rp2.content, rp2.uri, rp2.author_did
                           FROM processed_posts pp2 
                           JOIN raw_posts rp2 ON pp2.uri = rp2.uri 
                           WHERE pp2.topic_id = c.id 
                           ORDER BY rp2.created_at DESC 
                           LIMIT 3
                       ) t) as recent_posts,
                       NULL as sparkline,
                       (SELECT row_to_json(r) FROM (SELECT rating_score, sentiment, reasoning FROM topic_ratings WHERE cluster_id = c.id ORDER BY rated_at DESC LIMIT 1) r) as rating
                FROM clusters c
                JOIN processed_posts pp ON c.id = pp.topic_id
                JOIN raw_posts rp ON pp.uri = rp.uri
                WHERE c.is_active = TRUE 
                  AND rp.created_at >= NOW() - INTERVAL '10 minutes'
                GROUP BY c.id, c.label, c.summary
                ORDER BY display_time DESC
                LIMIT 10
            """))

            # 3. Last 24 Hours
            result_24h = conn.execute(text("""
                SELECT c.id, c.label, COUNT(rp.uri) as post_count, MAX(rp.created_at) as display_time, c.summary,
                       (SELECT json_agg(t) FROM (
                           SELECT rp2.content, rp2.uri, rp2.author_did
                           FROM processed_posts pp2 
                           JOIN raw_posts rp2 ON pp2.uri = rp2.uri 
                           WHERE pp2.topic_id = c.id 
                           ORDER BY rp2.created_at DESC 
                           LIMIT 3
                       ) t) as recent_posts,
                       (
                           SELECT json_agg(EXTRACT(EPOCH FROM created_at)) 
                           FROM raw_posts rp3 
                           JOIN processed_posts pp3 ON rp3.uri = pp3.uri 
                           WHERE pp3.topic_id = c.id AND rp3.created_at >= NOW() - INTERVAL '24 hours'
                       ) as sparkline,
                       (SELECT row_to_json(r) FROM (SELECT rating_score, sentiment, reasoning FROM topic_ratings WHERE cluster_id = c.id ORDER BY rated_at DESC LIMIT 1) r) as rating
                FROM clusters c
                JOIN processed_posts pp ON c.id = pp.topic_id
                JOIN raw_posts rp ON pp.uri = rp.uri
                WHERE c.is_active = TRUE 
                  AND rp.created_at >= NOW() - INTERVAL '24 hours'
                GROUP BY c.id, c.label, c.summary
                ORDER BY post_count DESC
                LIMIT 10
            """))

            # 4. Last 7 Days
            result_7d = conn.execute(text("""
                SELECT c.id, c.label, COUNT(rp.uri) as post_count, MAX(rp.created_at) as display_time, c.summary,
                       (SELECT json_agg(t) FROM (
                           SELECT rp2.content, rp2.uri, rp2.author_did
                           FROM processed_posts pp2 
                           JOIN raw_posts rp2 ON pp2.uri = rp2.uri 
                           WHERE pp2.topic_id = c.id 
                           ORDER BY rp2.created_at DESC 
                           LIMIT 3
                       ) t) as recent_posts,
                       (
                           SELECT json_agg(EXTRACT(EPOCH FROM created_at)) 
                           FROM raw_posts rp3 
                           JOIN processed_posts pp3 ON rp3.uri = pp3.uri 
                           WHERE pp3.topic_id = c.id AND rp3.created_at >= NOW() - INTERVAL '7 days'
                       ) as sparkline,
                       (SELECT row_to_json(r) FROM (SELECT rating_score, sentiment, reasoning FROM topic_ratings WHERE cluster_id = c.id ORDER BY rated_at DESC LIMIT 1) r) as rating
                FROM clusters c
                JOIN processed_posts pp ON c.id = pp.topic_id
                JOIN raw_posts rp ON pp.uri = rp.uri
                WHERE c.is_active = TRUE 
                  AND rp.created_at >= NOW() - INTERVAL '7 days'
                GROUP BY c.id, c.label, c.summary
                ORDER BY post_count DESC
                LIMIT 10
            """))

            # 5. Sentiment History (River Chart Data)
            # Fetch history for the top 10 most frequently rated topics in the last 24h
            result_sentiment = conn.execute(text("""
                WITH FrequentTopics AS (
                    SELECT cluster_id 
                    FROM topic_ratings 
                    WHERE rated_at >= NOW() - INTERVAL '24 hours'
                    GROUP BY cluster_id 
                    ORDER BY COUNT(*) DESC 
                    LIMIT 10
                )
                SELECT tr.cluster_id, c.label, tr.rating_score, tr.rated_at, tr.sentiment
                FROM topic_ratings tr
                JOIN clusters c ON tr.cluster_id = c.id
                WHERE tr.cluster_id IN (SELECT cluster_id FROM FrequentTopics)
                  AND tr.rated_at >= NOW() - INTERVAL '24 hours'
                ORDER BY tr.rated_at ASC
            """))

            # Process Sentiment Data
            sentiment_data = {}
            for row in result_sentiment:
                cid = row[0]
                if cid not in sentiment_data:
                    sentiment_data[cid] = {"label": row[1], "data": []}
                sentiment_data[cid]["data"].append({"t": row[3].isoformat(), "y": row[2]})

            # System Status
            system_status = {"latest_processed_time": "Now"}

            from datetime import datetime, timedelta, timezone
            
            def fill_gaps(timestamps, interval_type):
                if not timestamps:
                    return []
                
                # Convert to datetime objects
                points = {}
                for ts in timestamps:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    # Bucketize
                    if interval_type == '1h':
                        key = dt.replace(second=0, microsecond=0)
                    elif interval_type == '24h':
                        key = dt.replace(minute=0, second=0, microsecond=0)
                    elif interval_type == '7d':
                        key = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    else:
                        key = dt
                    
                    points[key] = points.get(key, 0) + 1
                
                now = datetime.now(timezone.utc)
                filled_data = []
                
                if interval_type == '1h':
                    # Last 60 minutes
                    start_time = now - timedelta(hours=1)
                    start_time = start_time.replace(second=0, microsecond=0)
                    for i in range(61):
                        t = start_time + timedelta(minutes=i)
                        val = points.get(t, 0)
                        filled_data.append(val)
                        
                elif interval_type == '24h':
                    # Last 24 hours
                    start_time = now - timedelta(hours=24)
                    start_time = start_time.replace(minute=0, second=0, microsecond=0)
                    for i in range(25):
                        t = start_time + timedelta(hours=i)
                        val = points.get(t, 0)
                        filled_data.append(val)
                        
                elif interval_type == '7d':
                    # Last 7 days
                    start_time = now - timedelta(days=7)
                    start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                    for i in range(8):
                        t = start_time + timedelta(days=i)
                        val = points.get(t, 0)
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
                "sentiment_history": sentiment_data,
                "system_status": system_status
            }
    except Exception as e:
        logger.error(f"Error fetching clusters: {e}")
        return {"last_hour": [], "last_24h": [], "last_7d": [], "sentiment_history": {}}

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
