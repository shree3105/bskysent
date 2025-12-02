import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load Env
env_path = os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env')
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
print(f"DATABASE_URL: {DATABASE_URL}")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL is missing!")
    exit()

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("Connected to DB!")
        
        # Check Row Count
        result = conn.execute(text("SELECT COUNT(*) FROM clusters"))
        count = result.scalar()
        print(f"Total Clusters: {count}")
        
        # Check Active Count
        result = conn.execute(text("SELECT COUNT(*) FROM clusters WHERE is_active = TRUE"))
        active_count = result.scalar()
        print(f"Active Clusters: {active_count}")
        
        # Show Top 5
        result = conn.execute(text("SELECT id, label, post_count FROM clusters ORDER BY post_count DESC LIMIT 5"))
        print("\nTop 5 Clusters:")
        for row in result:
            print(row)
            
except Exception as e:
    print(f"DB Error: {e}")
