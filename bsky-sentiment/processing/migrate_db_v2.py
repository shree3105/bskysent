import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_db():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not found.")
        return

    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        
        logger.info("Starting Database Migration for Phase 2...")

        # 1. Enable Vector Extension
        logger.info("Enabling pgvector extension...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

        # 2. Backup V1 Tables
        logger.info("Backing up V1 tables...")
        conn.execute(text("CREATE TABLE IF NOT EXISTS topics_v1_backup AS SELECT * FROM topics;"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS topic_scores_v1_backup AS SELECT * FROM topic_scores;"))
        
        # 3. Reset Processing State (Keep Raw Posts)
        logger.info("Resetting processing state...")
        conn.execute(text("TRUNCATE TABLE processed_posts, topic_scores CASCADE;"))
        # We don't truncate topics yet because of FK constraints, usually better to delete content
        conn.execute(text("DELETE FROM topics;")) 
        
        logger.info("Resetting RawPost.is_processed flags...")
        conn.execute(text("UPDATE raw_posts SET is_processed = FALSE;"))

        # 4. Create New Phase 2 Tables
        logger.info("Creating new 'clusters' table...")
        # Note: We use raw SQL for the vector column since SQLAlchemy needs specific types
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS clusters (
                id TEXT PRIMARY KEY,
                label TEXT,
                summary TEXT,
                embedding vector(384),
                entities JSONB,
                post_count INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_updated TIMESTAMPTZ DEFAULT NOW(),
                is_active BOOLEAN DEFAULT TRUE
            );
        """))
        
        # Update ProcessedPost to link to clusters (optional, or we reuse topic_id as cluster_id)
        # For Phase 2, let's stick to a clean new structure.
        # We might need to alter ProcessedPost if we want to enforce FKs to clusters instead of topics.
        # For now, let's assume we use the existing ProcessedPost but point topic_id to cluster.id
        
        logger.info("Migration Complete. Ready for Phase 2.")

if __name__ == "__main__":
    migrate_db()
