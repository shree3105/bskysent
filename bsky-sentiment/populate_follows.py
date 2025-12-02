import os
import logging
from dotenv import load_dotenv
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'ingestion'))

from bluesky_client import BlueskyIngester
from database import get_db_engine, init_db, SessionLocal

# Load .env from ingestion folder
load_dotenv(os.path.join(os.path.dirname(__file__), 'ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def populate_follows():
    logger.info("Initializing DB connection...")
    engine = get_db_engine()
    SessionLocal.configure(bind=engine)
    init_db(engine) # Ensure tables exist
    
    logger.info("Logging into Bluesky...")
    ingester = BlueskyIngester()
    ingester.login()
    
    logger.info("Fetching following list...")
    ingester.update_following_list()
    logger.info("Done!")

if __name__ == "__main__":
    populate_follows()
