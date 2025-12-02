import os
import logging
import joblib
import ollama
import csv
import pandas as pd
from sqlalchemy.orm import Session
from database import get_db_engine, init_db, RawPost, SessionLocal
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

LLAMA_MODEL = 'llama3'
CSV_FILE = os.path.join(os.path.dirname(__file__), 'labeled_data.csv')
MODEL_FILE = os.path.join(os.path.dirname(__file__), 'noise_filter.joblib')

def classify_all_posts():
    """Fetches all posts, classifies them via LLM, and saves to CSV."""
    engine = get_db_engine()
    SessionLocal.configure(bind=engine)
    session = SessionLocal()
    
    try:
        # 1. Load existing progress
        existing_uris = set()
        if os.path.exists(CSV_FILE):
            try:
                df = pd.read_csv(CSV_FILE)
                existing_uris = set(df['uri'].tolist())
                logger.info(f"Resuming... Found {len(existing_uris)} already classified posts.")
            except Exception:
                logger.warning("CSV file exists but is empty or corrupt. Starting fresh.")

        # 2. Fetch all posts
        logger.info("Fetching all posts from database...")
        all_posts = session.query(RawPost).all()
        
        posts_to_process = [p for p in all_posts if p.uri not in existing_uris]
        logger.info(f"Found {len(all_posts)} total posts. {len(posts_to_process)} remaining to classify.")
        
        if not posts_to_process:
            logger.info("All posts already classified!")
            return

        # 3. Open CSV for appending
        file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
        
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['uri', 'content', 'label'])
            
            for i, post in enumerate(posts_to_process):
                text = post.content
                
                try:
                    # STRICT Prompt for Noise vs Signal
                    response = ollama.chat(model=LLAMA_MODEL, messages=[
                        {'role': 'system', 'content': "You are a financial news filter. Classify the tweet as 'SIGNAL' (market-moving news, economic data, corporate events, geopolitical news) or 'NOISE' (opinion, memes, personal life, vague commentary, single words, reactions like 'lol'). Reply ONLY with 'SIGNAL' or 'NOISE'."},
                        {'role': 'user', 'content': f"Tweet: {text}\n\nClassification:"}
                    ])
                    label = response['message']['content'].strip().upper()
                    
                    if "SIGNAL" in label:
                        final_label = "Signal"
                    else:
                        final_label = "Noise"
                    
                    writer.writerow([post.uri, text, final_label])
                    f.flush() # Ensure write to disk
                    
                    if i % 10 == 0:
                        logger.info(f"[{i}/{len(posts_to_process)}] {final_label}: {text[:50]}...")
                        
                except Exception as e:
                    logger.error(f"LLM failed for post {post.uri}: {e}")
                    continue

    except Exception as e:
        logger.error(f"Classification failed: {e}")
    finally:
        session.close()

def train_from_csv():
    """Trains Naive Bayes model from the generated CSV."""
    try:
        if not os.path.exists(CSV_FILE):
            logger.error(f"No CSV found at {CSV_FILE}. Run classification first.")
            return

        logger.info(f"Loading data from {CSV_FILE}...")
        df = pd.read_csv(CSV_FILE)
        
        if df.empty:
            logger.error("CSV is empty.")
            return

        X = df['content'].fillna("").tolist()
        y = df['label'].tolist()
        
        logger.info(f"Training Naive Bayes Model on {len(X)} samples...")
        logger.info(f"Class distribution: {df['label'].value_counts().to_dict()}")

        model = make_pipeline(CountVectorizer(), MultinomialNB())
        model.fit(X, y)
        
        joblib.dump(model, MODEL_FILE)
        logger.info(f"Model saved to {MODEL_FILE}")
        
        # Validation
        test_phrases = [
            "Fed hikes rates by 50bps", 
            "Just ate a sandwich", 
            "Lol", 
            "Nvidia revenue jumps 200%", 
            "I hate mondays",
            "US Inflation rises to 3.2%"
        ]
        logger.info("--- Validation Tests ---")
        preds = model.predict(test_phrases)
        for text, pred in zip(test_phrases, preds):
            logger.info(f"'{text}' -> {pred}")

    except Exception as e:
        logger.error(f"Training failed: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train_from_csv()
    else:
        classify_all_posts()
        train_from_csv()
