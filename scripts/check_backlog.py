import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def check_backlog():
    with engine.connect() as conn:
        print(f"Current System Time: {datetime.now(timezone.utc)}")
        
        # 1. Total Raw Posts
        total_raw = conn.execute(text("SELECT COUNT(*) FROM raw_posts")).scalar()
        
        # 2. Processed Count (using is_processed flag if reliable, or joining processed_posts)
        # Let's check is_processed flag first as it's in the schema
        processed_count = conn.execute(text("SELECT COUNT(*) FROM raw_posts WHERE is_processed = TRUE")).scalar()
        
        # 3. Oldest Unprocessed Post (The "Head" of the backlog)
        oldest_unprocessed = conn.execute(text("""
            SELECT created_at 
            FROM raw_posts 
            WHERE is_processed = FALSE 
            ORDER BY created_at ASC 
            LIMIT 1
        """)).scalar()

        # 4. Newest Processed Post (Where we are currently working)
        newest_processed = conn.execute(text("""
            SELECT created_at 
            FROM raw_posts 
            WHERE is_processed = TRUE 
            ORDER BY created_at DESC 
            LIMIT 1
        """)).scalar()
        
        # 5. Newest Raw Post (The "Tail" of the backlog)
        newest_raw = conn.execute(text("""
            SELECT created_at 
            FROM raw_posts 
            ORDER BY created_at DESC 
            LIMIT 1
        """)).scalar()

        print("\n--- Backlog Status ---")
        print(f"Total Raw Posts:      {total_raw:,}")
        print(f"Processed Posts:      {processed_count:,} ({(processed_count/total_raw*100):.1f}%)")
        print(f"Remaining Backlog:    {total_raw - processed_count:,}")
        print("-" * 30)
        
        if oldest_unprocessed:
            print(f"Processing Data From: {oldest_unprocessed} (UTC)")
            lag = newest_raw - oldest_unprocessed
            print(f"Current Lag:          {lag}")
        else:
            print("No unprocessed posts found! (Caught up)")

        if newest_raw:
             print(f"Latest Ingested Data: {newest_raw} (UTC)")

if __name__ == "__main__":
    check_backlog()
