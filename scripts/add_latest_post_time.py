import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not found.")
        return

    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        logger.info("Adding latest_post_time column to clusters table...")
        
        try:
            conn.execute(text("ALTER TABLE clusters ADD COLUMN IF NOT EXISTS latest_post_time TIMESTAMPTZ DEFAULT NOW();"))
            logger.info("Column added successfully.")
            
            # Backfill with last_updated for existing records
            logger.info("Backfilling existing records...")
            conn.execute(text("UPDATE clusters SET latest_post_time = last_updated WHERE latest_post_time IS NULL;"))
            logger.info("Backfill complete.")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
