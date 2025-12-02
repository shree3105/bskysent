import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/processing'))
from database import get_db_engine, SessionLocal, Topic, ProcessedPost, RawPost
from sqlalchemy import func
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

def check_ratio():
    engine = get_db_engine()
    SessionLocal.configure(bind=engine)
    session = SessionLocal()
    try:
        # Get Noise Topic IDs
        noise_topics = session.query(Topic.id).filter(Topic.label == "Noise").all()
        noise_ids = [t.id for t in noise_topics]
        
        if not noise_ids:
            print("No 'Noise' topics found.")
            return

        # Count Noise Posts
        noise_count = session.query(func.count(ProcessedPost.uri)).filter(ProcessedPost.topic_id.in_(noise_ids)).scalar()
        
        # Count Signal Posts (Resolved but not Noise)
        signal_count = session.query(func.count(ProcessedPost.uri)).\
            join(Topic, ProcessedPost.topic_id == Topic.id).\
            filter(Topic.label != "Noise", ~Topic.label.like("PENDING:%")).scalar()
            
        print(f"Noise Posts: {noise_count}")
        print(f"Signal Posts: {signal_count}")
        
    finally:
        session.close()

if __name__ == "__main__":
    check_ratio()
