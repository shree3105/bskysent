import sys
import os
import logging
import time
from sqlalchemy import text
from dotenv import load_dotenv

# Add processing dir to path
sys.path.append(os.path.join(os.getcwd(), 'bsky-sentiment', 'processing'))

from pipeline import Pipeline, engine

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("BoundaryAnalysis")

def main():
    logger.info("Initializing Pipeline for Analysis...")
    pipeline = Pipeline()
    
    # Fetch recent processed posts to analyze
    logger.info("Fetching recent processed posts...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT rp.uri, rp.content, rp.quote_content 
            FROM raw_posts rp
            JOIN processed_posts pp ON rp.uri = pp.uri
            WHERE rp.is_processed = TRUE
            ORDER BY rp.created_at DESC
            LIMIT 20
        """)).fetchall()

    logger.info(f"Analyzing {len(rows)} posts...")
    
    results = []
    
    for i, row in enumerate(rows):
        uri, content, quote = row
        full_text = (content or "") + (" " + quote if quote else "")
        full_text = full_text.strip()
        
        if not full_text: continue

        # 1. Get Candidates
        embedding = pipeline.models.get_embedding(full_text)
        candidates = pipeline.find_nearest_clusters(embedding, limit=5)
        
        if not candidates:
            continue
            
        candidate_summaries = [c[2] for c in candidates]
        
        # 2. Run Cross-Encoder (The "Smart Filter")
        # pipeline.models.cross_encoder.predict returns scores
        pairs = [[full_text, summary] for summary in candidate_summaries]
        ce_scores = pipeline.models.cross_encoder.predict(pairs)
        
        # 3. Run Llama 70B (The "Truth")
        # We need to respect rate limits, so sleep a bit
        time.sleep(2) 
        llama_decisions = pipeline.models.verify_match_llama_batch(full_text, candidate_summaries)
        
        # 4. Log Data
        for idx, summary in enumerate(candidate_summaries):
            score = float(ce_scores[idx])
            llama_says_match = llama_decisions[idx]
            
            results.append({
                "score": score,
                "llama_match": llama_says_match,
                "text_snippet": full_text[:30],
                "summary_snippet": summary[:30]
            })
            
            match_str = "MATCH" if llama_says_match else "NO_MATCH"
            logger.info(f"Score: {score:.4f} | Llama: {match_str}")

    # Analysis
    logger.info("\n=== BOUNDARY ANALYSIS ===")
    
    # Find safe lower bound (Max score where Llama still says NO)
    # Actually, we want: Below what score does Llama ALWAYS say NO?
    # And: Above what score does Llama ALWAYS say YES?
    
    matches = [r['score'] for r in results if r['llama_match']]
    non_matches = [r['score'] for r in results if not r['llama_match']]
    
    if matches:
        min_match = min(matches)
        logger.info(f"Lowest Score that was a MATCH: {min_match:.4f}")
        
        # Print Low Score Matches
        logger.info("\n--- LOW SCORE MATCHES (Score < 0) ---")
        for r in results:
            if r['llama_match'] and r['score'] < 0:
                logger.info(f"Score: {r['score']:.2f} | Text: {r['text_snippet']}... | Summary: {r['summary_snippet']}...")

    else:
        logger.info("No matches found in sample.")
        
    if non_matches:
        max_non_match = max(non_matches)
        logger.info(f"Highest Score that was a NO_MATCH: {max_non_match:.4f}")
        
        # Print High Score Non-Matches
        logger.info("\n--- HIGH SCORE NON-MATCHES (Score > 5) ---")
        for r in results:
            if not r['llama_match'] and r['score'] > 5:
                logger.info(f"Score: {r['score']:.2f} | Text: {r['text_snippet']}... | Summary: {r['summary_snippet']}...")
    else:
        logger.info("No non-matches found in sample.")

if __name__ == "__main__":
    main()
