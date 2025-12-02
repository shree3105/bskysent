import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def test_queries():
    with engine.connect() as conn:
        print(f"Current Time: {datetime.now()}")
        
        # 1. Last Hour
        print("\n--- Testing Last Hour Query ---")
        result_1h = conn.execute(text("""
            SELECT id, label, post_count, COALESCE(latest_post_time, last_updated) as display_time
            FROM clusters 
            WHERE is_active = TRUE 
              AND GREATEST(COALESCE(latest_post_time, '-infinity'), last_updated) >= NOW() - INTERVAL '1 hour'
            ORDER BY post_count DESC 
            LIMIT 20
        """))
        rows_1h = result_1h.fetchall()
        print(f"Rows found: {len(rows_1h)}")
        for row in rows_1h:
            print(row)

        # 2. Last 24 Hours
        print("\n--- Testing Last 24 Hours Query ---")
        result_24h = conn.execute(text("""
            SELECT id, label, post_count, COALESCE(latest_post_time, last_updated) as display_time
            FROM clusters 
            WHERE is_active = TRUE 
              AND GREATEST(COALESCE(latest_post_time, '-infinity'), last_updated) >= NOW() - INTERVAL '24 hours'
            ORDER BY post_count DESC 
            LIMIT 20
        """))
        rows_24h = result_24h.fetchall()
        print(f"Rows found: {len(rows_24h)}")
        for row in rows_24h:
            print(row)

if __name__ == "__main__":
    test_queries()
