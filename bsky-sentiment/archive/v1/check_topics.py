import sys
import os
from dotenv import load_dotenv

# Add processing dir to path
sys.path.append(os.path.join(os.getcwd(), 'bsky-sentiment', 'processing'))

# Load env
load_dotenv('bsky-sentiment/ingestion/.env')

from database import get_db_engine, SessionLocal, Topic, ProcessedPost, func

def check():
    engine = get_db_engine()
    print(f"Connected to: {engine.url}")
    SessionLocal.configure(bind=engine)
    session = SessionLocal()
    
    try:
        # Debug Counts
        raw_count = session.query(func.count(Topic.id)).select_from(Topic).scalar() # Mistake in import, let's fix below
        # Actually let's just use raw sql or proper imports.
        # I need to import RawPost in the script first.
        
        # Check for resolved topics
        resolved = session.query(Topic.id, Topic.label, Topic.keywords).filter(Topic.label.notlike('PENDING:%')).all()
        print(f"Resolved Topics Count: {len(resolved)}")
        for t in resolved:
            print(f" - {t.label} (ID: {t.id})")
            
        # Check for pending topics with high counts
        print("\nPending Topics with > 1 posts:")
        pending_counts = session.query(Topic.id, func.count(ProcessedPost.uri))\
            .join(ProcessedPost, Topic.id == ProcessedPost.topic_id)\
            .filter(Topic.label.like('PENDING:%'))\
            .group_by(Topic.id)\
            .having(func.count(ProcessedPost.uri) > 1)\
            .all()
            
        for tid, count in pending_counts:
            print(f" - {tid}: {count} posts")

        # DEBUG SECTION
        from database import RawPost
        total_raw = session.query(func.count(RawPost.uri)).scalar()
        processed_raw = session.query(func.count(RawPost.uri)).filter(RawPost.is_processed == True).scalar()
        total_processed_posts = session.query(func.count(ProcessedPost.uri)).scalar()
        
        print(f"\nDEBUG STATS:")
        print(f"Total Raw Posts: {total_raw}")
        print(f"Processed Raw Posts: {processed_raw}")
        print(f"Total Entries in ProcessedPost Table: {total_processed_posts}")
        
        if total_processed_posts > 0:
            print("Sample ProcessedPost:")
            sample = session.query(ProcessedPost).first()
            print(f" - URI: {sample.uri}, TopicID: {sample.topic_id}")
            
    finally:
        session.close()

if __name__ == "__main__":
    check()
