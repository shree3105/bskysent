import os
import time
import logging
import pandas as pd
import requests
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from tqdm import tqdm

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Setup DB
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3" 

# Use a Session for connection pooling (Keep-Alive)
session = requests.Session()

def get_all_posts():
    with engine.connect() as conn:
        # Fetch all posts
        query = text("SELECT uri, content, quote_content FROM raw_posts ORDER BY created_at DESC")
        return pd.read_sql(query, conn)

def classify_post_ollama(text_content):
    prompt = f"""
    Classify this social media post into exactly one category:
    1. "Financial News" (IMPORTANT: Breaking News, Geopolitics, Global Events, Headlines, Market Moves, Earnings, Crypto, Economic Data, Mergers & Acquisitions, Central Bank Policy, Commodities & Energy, Legal & Regulatory, Technology & Product Launches, Executive Changes, IPOs & Capital Markets, Analyst Ratings, Trade & Tariffs, Health & Biotech, Defense & Security, Natural Disasters, Supply Chain & Logistics, Politics, President)
    2. "Noise" (Personal opinion, random chatter, memes, spam, minor daily life updates)
    
    Post: "{text_content}"
    
    Return ONLY the category name ("Financial News" or "Noise"). Do not explain.
    """
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        # Use the global session
        response = session.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        result = response.json()['response'].strip()
        
        # Normalize output
        if "Financial News" in result:
            return "Financial News"
        return "Noise" # Default to Noise if unsure or "Noise" is in result
    except Exception as e:
        logger.error(f"Ollama Error: {e}")
        return "Error"

def main():
    logger.info("Fetching posts from DB...")
    df = get_all_posts()
    logger.info(f"Loaded {len(df)} posts.")
    
    # Prepare text
    df['full_text'] = df['content'].fillna('') + " " + df['quote_content'].fillna('')
    df['full_text'] = df['full_text'].str.strip()
    df = df[df['full_text'].str.len() > 10] # Skip tiny posts
    
    logger.info(f"Classifying {len(df)} valid posts using Ollama ({MODEL_NAME})...")
    
    labels = []
    
    # Process in parallel (Ollama handles queuing/batching well)
    from concurrent.futures import ThreadPoolExecutor
    
    # Increased workers to 10 to saturate GPU
    with ThreadPoolExecutor(max_workers=10) as executor:
        labels = list(tqdm(executor.map(classify_post_ollama, df['full_text']), total=len(df)))
        
    df['label'] = labels
    
    # Filter out errors
    df = df[df['label'] != "Error"]
    
    # Save
    output_path = "bsky-sentiment/processing/labeled_dataset.csv"
    df.to_csv(output_path, index=False)
    logger.info(f"Saved labeled dataset to {output_path}")
    
    # Show stats
    print(df['label'].value_counts())

if __name__ == "__main__":
    main()
