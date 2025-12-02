import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from ingestion folder
load_dotenv(os.path.join(os.path.dirname(__file__), 'ingestion/.env'))

def reset_database():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found.")
        return

    print(f"Connecting to {db_url.split('@')[1]}...") # Hide credentials
    engine = create_engine(db_url)

    with engine.connect() as connection:
        print("Dropping old tables...")
        # Drop tables with CASCADE to handle foreign keys
        connection.execute(text("DROP TABLE IF EXISTS raw_posts CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS topic_scores CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS processed_posts CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS topics CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS monitored_accounts CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS system_state CASCADE;"))
        connection.commit()
        print("Tables dropped.")

    print("Re-initializing tables using ingestion/database.py...")
    from ingestion.database import init_db as init_ingestion_db, get_db_engine
    
    # We need to make sure we use the same engine or create a new one
    # The init_db function takes an engine
    init_ingestion_db(engine)
    
    print("Re-initializing tables using processing/database.py...")
    # Note: processing/database.py might have extra tables (Topics, Scores)
    # We should import the models to ensure they are registered with Base
    from processing.database import Topic, TopicScore, ProcessedPost, SystemState, Base
    Base.metadata.create_all(engine)

    print("Database reset and schema updated successfully!")

if __name__ == "__main__":
    reset_database()
