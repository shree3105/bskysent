import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_db():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not found.")
        return

    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        
        logger.info("Resetting Phase 2 Data...")

        # 1. Clear Clusters and Links
        logger.info("Truncating clusters and processed_posts...")
        conn.execute(text("TRUNCATE TABLE clusters, processed_posts CASCADE;"))
        
        # 2. Reset Raw Posts
        logger.info("Resetting raw_posts flags...")
        conn.execute(text("UPDATE raw_posts SET is_processed = FALSE;"))

        logger.info("Reset Complete. You can now re-run pipeline.py.")

if __name__ == "__main__":
    reset_db()
