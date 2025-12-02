import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def check_raw():
    with engine.connect() as conn:
        print("\n--- Raw Cluster Data (Top 10) ---")
        result = conn.execute(text("""
            SELECT id, label, post_count, latest_post_time, last_updated 
            FROM clusters 
            ORDER BY post_count DESC 
            LIMIT 10
        """))
        for row in result:
            print(row)

if __name__ == "__main__":
    check_raw()
