import os
import time
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI
from dotenv import load_dotenv

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RatingService")

# Load Env (Try local path first, then default to container envs)
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "qwen/qwen3-32b" # User requested model

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not found! Service will fail to rate topics.")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def ensure_table_exists():
    """Create the topic_ratings table if it doesn't exist."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS topic_ratings (
                    id SERIAL PRIMARY KEY,
                    cluster_id TEXT NOT NULL,
                    rating_score INTEGER,
                    sentiment TEXT,
                    reasoning TEXT,
                    rated_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE CASCADE
                );
            """)
            conn.commit()
            logger.info("✅ Table `topic_ratings` checked/created.")
    except Exception as e:
        logger.error(f"Failed to create table: {e}")
    finally:
        conn.close()

def get_top_clusters():
    """Fetch top 5 active clusters from the last hour."""
    conn = get_db_connection()
    clusters = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Logic matches dashboard: Top 5 by post count in last hour
            cur.execute("""
                SELECT c.id, c.label, c.summary, COUNT(rp.uri) as post_count
                FROM clusters c
                JOIN processed_posts pp ON c.id = pp.topic_id
                JOIN raw_posts rp ON pp.uri = rp.uri
                WHERE c.is_active = TRUE 
                  AND rp.created_at >= NOW() - INTERVAL '1 hour'
                GROUP BY c.id, c.label, c.summary
                ORDER BY post_count DESC 
                LIMIT 5
            """)
            clusters = cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching clusters: {e}")
    finally:
        conn.close()
    return clusters

def rate_batch(clusters):
    """Send a batch request to Groq."""
    if not clusters:
        return []

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY
    )

    # Prepare Prompt
    cluster_text = ""
    for i, c in enumerate(clusters):
        cluster_text += f"ID: {c['id']}\nLabel: {c['label']}\nSummary: {c['summary']}\n---\n"

    prompt = f"""
    You are a Financial News Analyst. Rate the following 5 topics based on their "Market Impact".
    
    TOPICS:
    {cluster_text}

    INSTRUCTIONS:
    - Return a JSON object with keys as Cluster IDs.
    - Each value must have: "score" (0-100) representing Market Impact, "sentiment" (Bullish/Bearish/Neutral), "reasoning" (Max 10 words).
    - Score Criteria: 0-20 = Noise/Irrelevant, 21-50 = Minor Note, 51-79 = Moderate Impact, 80-100 = Major Market Mover.

    JSON OUTPUT FORMAT:
    {{
        "cluster_id_1": {{"score": 85, "sentiment": "Bullish", "reasoning": "Major acquisition news."}},
        ...
    }}
    """

    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                {"role": "user", "content": prompt}
            ],
            model=GROQ_MODEL,
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        content = completion.choices[0].message.content
        logger.info(f"Groq Response: {content}")
        return json.loads(content)
    except Exception as e:
        logger.error(f"Groq API Failed: {e}")
        return {}

def save_ratings(ratings):
    """Save ratings to DB."""
    if not ratings:
        return

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for cluster_id, data in ratings.items():
                cur.execute("""
                    INSERT INTO topic_ratings (cluster_id, rating_score, sentiment, reasoning)
                    VALUES (%s, %s, %s, %s)
                """, (cluster_id, data['score'], data['sentiment'], data['reasoning']))
            conn.commit()
            logger.info(f"✅ Saved {len(ratings)} ratings.")
    except Exception as e:
        logger.error(f"Error saving ratings: {e}")
    finally:
        conn.close()

def main():
    logger.info("🚀 Starting Topic Rating Service (Groq Qwen 32B)...")
    ensure_table_exists()
    
    while True:
        try:
            logger.info("Fetching Top 5 Clusters...")
            clusters = get_top_clusters()
            
            if not clusters:
                logger.info("No active clusters found. Sleeping...")
            else:
                logger.info(f"Found {len(clusters)} clusters. Rating...")
                ratings = rate_batch(clusters)
                save_ratings(ratings)
            
            logger.info("Sleeping for 5 minutes...")
            time.sleep(300) 
            
        except Exception as e:
            logger.error(f"Main Loop Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
