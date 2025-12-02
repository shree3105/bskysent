import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from ingestion folder
load_dotenv(os.path.join(os.path.dirname(__file__), 'ingestion/.env'))

def reset_processing():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found.")
        return

    print(f"Connecting to {db_url.split('@')[1]}...")
    engine = create_engine(db_url)

    with engine.connect() as connection:
        print("Cleaning processing tables...")
        # Clear processing results
        connection.execute(text("TRUNCATE TABLE topic_scores CASCADE;"))
        connection.execute(text("TRUNCATE TABLE processed_posts CASCADE;"))
        connection.execute(text("TRUNCATE TABLE topics CASCADE;"))
        connection.execute(text("DELETE FROM system_state WHERE key = 'last_scored_time';"))
        
        print("Resetting raw_posts status...")
        # Reset raw_posts to be processed again
        connection.execute(text("UPDATE raw_posts SET is_processed = false;"))
        
        # Check monitored accounts
        result = connection.execute(text("SELECT COUNT(*) FROM monitored_accounts;"))
        count = result.scalar()
        print(f"Monitored Accounts Count: {count}")
        
        connection.commit()
        print("Processing data cleared and raw_posts reset.")

if __name__ == "__main__":
    reset_processing()
