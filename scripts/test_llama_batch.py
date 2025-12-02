import logging
import sys
import os
import time

# Add path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bsky-sentiment', 'processing'))

from models import LocalModels

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_llama_batch():
    models = LocalModels()
    
    print(f"\n{'='*20} TESTING PARALLEL LLAMA BATCH {'='*20}")
    
    post_text = "Apple stock hits all time high on new iPhone sales data."
    
    candidates = [
        "Apple Inc. shares reached a record high today driven by strong iPhone 15 demand.", # MATCH
        "Tesla stock surges as Elon Musk announces new factory.", # NO MATCH
        "Microsoft releases new Windows update.", # NO MATCH
        "Tech stocks are rallying today led by AAPL.", # MATCH (Maybe)
        "Banana prices are up due to shortage." # NO MATCH
    ]
    
    print(f"Post: {post_text}")
    print(f"Candidates: {len(candidates)}")
    
    start_time = time.time()
    results = models.verify_match_llama_batch(post_text, candidates)
    end_time = time.time()
    
    print(f"\nTime Taken: {end_time - start_time:.4f} seconds")
    
    for i, (cand, is_match) in enumerate(zip(candidates, results)):
        status = "MATCH" if is_match else "NO MATCH"
        print(f"[{i+1}] {status} | {cand}")

if __name__ == "__main__":
    test_llama_batch()
