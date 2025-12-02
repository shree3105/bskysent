import time
import logging
import os
from dotenv import load_dotenv
from database import init_db, get_db_engine
from bluesky_client import BlueskyIngester

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing Bluesky Sentiment Ingestion Service...")
    
    # Initialize DB
    engine = get_db_engine()
    from database import SessionLocal
    SessionLocal.configure(bind=engine)
    init_db(engine)
    logger.info("Database initialized.")

    # Initialize Ingester
    ingester = BlueskyIngester()
    
    # Login
    ingester.login()
    
    # Initial fetch of following list
    ingester.update_following_list()
    
    # Start background thread to update following list periodically
    import threading
    def background_update():
        while True:
            time.sleep(600) # 10 minutes
            try:
                ingester.update_following_list()
            except Exception as e:
                logger.error(f"Background update failed: {e}")

    t = threading.Thread(target=background_update, daemon=True)
    t.start()
    logger.info("Started background thread for updating following list.")

    # Start Firehose (Blocking)
    try:
        ingester.start_firehose()
    except KeyboardInterrupt:
        logger.info("Stopping service...")
    except Exception as e:
        logger.error(f"Service crashed: {e}")
        # In a real deployment, the container orchestrator (Docker/K8s) would restart this.
        raise

if __name__ == "__main__":
    main()
