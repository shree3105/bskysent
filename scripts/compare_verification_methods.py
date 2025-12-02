import sys
import os
import logging
from sqlalchemy import text
from dotenv import load_dotenv
from groq import Groq

# Add processing dir to path so we can import pipeline/models
sys.path.append(os.path.join(os.getcwd(), 'bsky-sentiment', 'processing'))

from pipeline import Pipeline, engine

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("ComparisonTest")

# Load Env
load_dotenv(os.path.join(os.getcwd(), 'bsky-sentiment/ingestion/.env'))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.1-8b-instant"

def run_new_batch_logic(post_text, candidates):
    # candidates is list of tuples from DB
    # id, label, summary, entities, post_count, last_updated, distance, latest_post_time
    
    c_text = ""
    c_map = {}
    for c in candidates:
        c_id = c[0]
        c_summary = c[2]
        c_text += f"ID: {c_id} | Summary: {c_summary}\n"
        c_map[c_id] = c
        
    prompt = f"""
    You are a news clustering assistant. 
    Determine if the NEW POST belongs to any of the existing CLUSTERS.
    It must describe the EXACT same specific event.

    NEW POST: "{post_text}"

    CLUSTERS:
    {c_text}

    INSTRUCTIONS:
    - If the post matches a cluster, return ONLY the ID of that cluster.
    - If it matches NONE, return "None".
    - Do not explain.
    """
    
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            temperature=0,
            max_tokens=10,
        )
        result = chat_completion.choices[0].message.content.strip()
        
        # Simple cleanup
        for line in result.split('\n'):
            clean = line.strip().replace('"', '').replace("'", "")
            if clean in c_map:
                return clean
        
        if "None" in result or "NONE" in result:
            return None
            
        return result # Return raw if unsure
    except Exception as e:
        logger.error(f"Batch Error: {e}")
        return None

import time

def main():
    logger.info("Initializing Pipeline (Read-Only)...")
    pipeline = Pipeline()
    
    # Fetch 1 recent processed post for Smoke Test
    logger.info("Fetching 1 recent post from DB...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT rp.uri, rp.content, rp.quote_content, pp.topic_id 
            FROM raw_posts rp
            JOIN processed_posts pp ON rp.uri = pp.uri
            WHERE rp.is_processed = TRUE
            ORDER BY rp.created_at DESC
            LIMIT 1
        """)).fetchall()

    if not rows:
        logger.info("No processed posts found in DB.")
        return

    logger.info(f"Testing on {len(rows)} posts (Estimated time: ~3 mins)...")
    
    agreements = 0
    disagreements = 0
    errors = 0
    
    for i, row in enumerate(rows):
        # Sleep to respect rate limits
        # 15 posts in 3 mins = 5 posts/min.
        # 60s / 5 = 12s. Let's do 10s to be slightly aggressive but safe-ish.
        if i > 0:
            time.sleep(10)

        uri, content, quote, actual_topic_id = row
        full_text = (content or "") + (" " + quote if quote else "")
        full_text = full_text.strip()
        
        # 1. Get Candidates (Simulate Pipeline Step 2)
        embedding = pipeline.models.get_embedding(full_text)
        candidates = pipeline.find_nearest_clusters(embedding, limit=5)
        
        if not candidates:
            continue
            
        # 2. Run OLD Method (Parallel Yes/No)
        candidate_summaries = [c[2] for c in candidates]
        old_results = pipeline.models.verify_match_llama_batch(full_text, candidate_summaries)
        
        old_match_id = None
        for idx, is_match in enumerate(old_results):
            if is_match:
                old_match_id = candidates[idx][0]
                break 
                
        # 3. Run NEW Method (Batch)
        new_match_id = run_new_batch_logic(full_text, candidates)
        
        # 4. Compare
        if old_match_id == new_match_id:
            agreements += 1
            print(".", end="", flush=True)
        else:
            disagreements += 1
            print("X", end="", flush=True)
            logger.info(f"\n[DISAGREEMENT] Post: {full_text[:50]}...")
            logger.info(f"  Old: {old_match_id} | New: {new_match_id}")

    print("\n\n=== RESULTS ===")
    print(f"Total Posts Tested: {agreements + disagreements}")
    print(f"Agreements: {agreements}")
    print(f"Disagreements: {disagreements}")
    if (agreements + disagreements) > 0:
        print(f"Agreement Rate: {agreements / (agreements + disagreements) * 100:.2f}%")

if __name__ == "__main__":
    main()
