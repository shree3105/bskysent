import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def check_data():
    with engine.connect() as conn:
        print("\n--- Cluster Data Sample ---")
        result = conn.execute(text("""
            SELECT id, label, summary 
            FROM clusters 
            WHERE is_active = TRUE 
            LIMIT 5
        """))
        for row in result:
            print(f"ID: {row[0]}")
            print(f"Label: {row[1]}")
            print(f"Summary: {row[2]}")
            print("-" * 20)

if __name__ == "__main__":
    check_data()
