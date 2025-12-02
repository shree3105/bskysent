import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), 'ingestion/.env'))

def check_count():
    db_url = os.getenv("DATABASE_URL")
    engine = create_engine(db_url)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT COUNT(*) FROM monitored_accounts;"))
        print(f"Count: {result.scalar()}")

if __name__ == "__main__":
    check_count()
