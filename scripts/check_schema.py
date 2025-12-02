import os
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def check_schema():
    inspector = inspect(engine)
    
    print("\n--- Schema: raw_posts ---")
    columns = inspector.get_columns('raw_posts')
    for column in columns:
        print(f"('{column['name']}', '{column['type']}')")

if __name__ == "__main__":
    check_schema()
