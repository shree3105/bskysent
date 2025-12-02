import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_sentiment():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not found.")
        return

    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        
        logger.info("Adding sentiment columns to clusters table...")
        
        try:
            conn.execute(text("ALTER TABLE clusters ADD COLUMN IF NOT EXISTS sentiment_score FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE clusters ADD COLUMN IF NOT EXISTS sentiment_label TEXT DEFAULT 'Neutral';"))
            logger.info("Columns added successfully.")
        except Exception as e:
            logger.error(f"Error adding columns: {e}")

if __name__ == "__main__":
    migrate_sentiment()
