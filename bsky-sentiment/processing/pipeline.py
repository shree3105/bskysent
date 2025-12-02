import os
import time
import logging
import json
import numpy as np
import requests
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from models import LocalModels

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DB Setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Pipeline:
    def __init__(self):
        self.models = LocalModels()
        logger.info("Pipeline initialized.")

    def get_unprocessed_posts(self, limit=50):
        with engine.connect() as conn:
            result = conn.execute(text("SELECT uri, content, quote_content FROM raw_posts WHERE is_processed = FALSE ORDER BY created_at ASC LIMIT :limit"), {"limit": limit})
            return result.fetchall()
import os
import time
import logging
import json
import numpy as np
import requests
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from models import LocalModels

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DB Setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Setup Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
LLAMA_MODEL = "llama3"
# Use a Session for connection pooling
session = requests.Session()

class Pipeline:
    def __init__(self):
        self.models = LocalModels()
        logger.info("Pipeline initialized.")

    def get_unprocessed_posts(self, limit=50):
        with engine.connect() as conn:
            # Fetch created_at as well
            result = conn.execute(text("SELECT uri, content, quote_content, created_at FROM raw_posts WHERE is_processed = FALSE ORDER BY created_at ASC LIMIT :limit"), {"limit": limit})
            return result.fetchall()

    def mark_processed(self, uri):
        with engine.connect() as conn:
            conn.execute(text("UPDATE raw_posts SET is_processed = TRUE WHERE uri = :uri"), {"uri": uri})
            conn.commit()

    def find_nearest_clusters(self, embedding, limit=20):
        # pgvector search - Fetch Top 20 Candidates
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, label, summary, entities, post_count, last_updated, embedding <=> :embedding as distance, latest_post_time
                FROM clusters
                WHERE is_active = TRUE
                ORDER BY embedding <=> :embedding ASC
                LIMIT :limit
            """), {"embedding": str(embedding), "limit": limit})
            return result.fetchall()



    def create_cluster(self, uri, content, embedding, entities, created_at):
        cluster_id = f"cluster_{int(time.time())}_{np.random.randint(1000)}"
        summary = content # Initial summary is just the first post
        
        # Generate initial headline if possible, or just use content
        label = "New Topic" 
        
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO clusters (id, label, summary, embedding, entities, post_count, latest_post_time)
                VALUES (:id, :label, :summary, :embedding, :entities, 1, :created_at)
            """), {
                "id": cluster_id,
                "label": label,
                "summary": summary,
                "embedding": str(embedding),
                "entities": json.dumps(entities),
                "created_at": created_at
            })
            # Link Post to Cluster (Ignore duplicates)
            conn.execute(text("INSERT INTO processed_posts (uri, topic_id) VALUES (:uri, :cluster_id) ON CONFLICT (uri) DO NOTHING"), 
                         {"uri": uri, "cluster_id": cluster_id})
            conn.commit()
        logger.info(f"Created New Cluster: {cluster_id}")
        return cluster_id

    def update_cluster(self, uri, cluster_id, content, embedding, old_count, old_summary, created_at):
        # Simple moving average for embedding (optional, or just keep centroid)
        # For now, we just increment count. 
        # If count hits 5, 10, etc, we trigger re-summarization.
        
        new_count = old_count + 1
        
        with engine.connect() as conn:
            # Update latest_post_time only if the new post is newer
            conn.execute(text("""
                UPDATE clusters 
                SET post_count = :count, 
                    last_updated = NOW(),
                    latest_post_time = GREATEST(COALESCE(latest_post_time, '-infinity'), :created_at)
                WHERE id = :id
            """), {"count": new_count, "id": cluster_id, "created_at": created_at})
            # Link Post to Cluster (Ignore duplicates)
            conn.execute(text("INSERT INTO processed_posts (uri, topic_id) VALUES (:uri, :cluster_id) ON CONFLICT (uri) DO NOTHING"), 
                         {"uri": uri, "cluster_id": cluster_id})
            conn.commit()
            
        logger.info(f"Merged into Cluster: {cluster_id} (Count: {new_count})")
        
        # Trigger Headline Update
        if new_count % 3 == 0:
            # Fetch recent posts for this cluster (we need a way to link posts to clusters)
            # For now, we just use the old summary + new content as context
            context = old_summary + "\n" + content
            new_headline = self.models.generate_headline_llama(context)
            
            with engine.connect() as conn:
                conn.execute(text("UPDATE clusters SET label = :label WHERE id = :id"), 
                             {"label": new_headline, "id": cluster_id})
                conn.commit()
            logger.info(f"Updated Headline: {new_headline}")

    def run(self):
        logger.info("Starting Phase 2 Pipeline (Live Re-ranking)...")
        while True:
            posts = self.get_unprocessed_posts()
            if not posts:
                time.sleep(5)
                continue
            
            logger.info(f"Processing batch of {len(posts)} posts...")
            
            for post in posts:
                uri, content, quote, created_at = post
                full_text = (content or "") + (" " + quote if quote else "")
                full_text = full_text.strip()
                
                if not full_text:
                    logger.info(f"Skipping empty post: {uri}")
                    self.mark_processed(uri)
                    continue

                # Log truncated content for visibility
                logger.info(f"Processing: {full_text[:50]}...")

                # 1. NOISE FILTER
                if self.models.is_noise(full_text):
                    logger.info(f"Dropped Noise: {full_text[:30]}...")
                    self.mark_processed(uri)
                    continue
                
                # 2. VECTOR SEARCH (Fetch Candidates)
                embedding = self.models.get_embedding(full_text)
                candidates = self.find_nearest_clusters(embedding, limit=50)
                
                logger.info(f"Found {len(candidates)} candidates for: {uri}")

                # 3. LIVE RE-RANKING (Time Cone Logic)
                valid_candidates = []
                
                post_entities = self.models.extract_entities(full_text)
                post_orgs = {e['text'].lower() for e in post_entities if e['label'] in ['organization', 'person', 'location']}

                for cand in candidates:
                    c_id, c_label, c_summary, c_ent_json, c_count, c_updated, c_dist, c_latest_time = cand
                    
                    # A. Temporal Decay
                    # Use latest_post_time for decay if available, else last_updated
                    ref_time = c_latest_time if c_latest_time else c_updated
                    
                    # Ensure ref_time is timezone aware/naive compatible with datetime.now(timezone.utc)
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)
                    
                    # Ensure created_at is timezone aware
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    time_diff = abs((created_at - ref_time).total_seconds()) / 3600.0
                    
                    # Gentler Decay (Half-life of 12 hours)
                    # Score drops to 0.5 after 12 hours, 0.33 after 24 hours.
                    decay_weight = 1.0 / (1.0 + (time_diff / 12.0))
                    
                    # B. Similarity
                    raw_sim = 1 - c_dist
                    adjusted_sim = raw_sim * decay_weight
                    
                    # Debug Log
                    # logger.info(f"Cand: {c_label} | Sim: {raw_sim:.2f} | Decay: {decay_weight:.2f} | Adj: {adjusted_sim:.2f}")

                    # C. Threshold Check (0.25 allows fresh news with sim ~0.3 to pass)
                    if adjusted_sim < 0.25:
                        continue
                        
                    # Add to potential candidates
                    valid_candidates.append({
                        "data": cand,
                        "score": adjusted_sim
                    })

                # Sort by Score (Descending)
                valid_candidates.sort(key=lambda x: x["score"], reverse=True)
                
                logger.info(f"Valid Candidates after Re-ranking: {len(valid_candidates)}")

                # E. Hybrid Gatekeeper Verification
                best_match = None
                best_score = -1
                
                # Take Top 5
                top_5_items = valid_candidates[:5]
                if top_5_items:
                    # Prepare batch
                    summaries = [item["data"][2] for item in top_5_items]
                    
                    logger.info(f"Verifying Top 5 Candidates...")

                    # 1. Run Gatekeeper (Local Cross-Encoder)
                    gk_decisions, gk_scores = self.models.verify_match_gatekeeper(full_text, summaries)
                    
                    final_decisions = []
                    
                    # 2. Process Gatekeeper Results
                    llama_candidates_indices = []
                    llama_candidates_summaries = []
                    
                    for i, decision in enumerate(gk_decisions):
                        cand_label = top_5_items[i]["data"][1]
                        score = gk_scores[i]
                        
                        if decision is True:
                            logger.info(f"  🛡️ SAFE ACCEPT: {cand_label} (Score: {score:.2f})")
                            final_decisions.append(True)
                        elif decision is False:
                            logger.info(f"  🛡️ SAFE REJECT: {cand_label} (Score: {score:.2f})")
                            final_decisions.append(False)
                        else:
                            logger.info(f"  🤔 AMBIGUOUS: {cand_label} (Score: {score:.2f}) -> Sending to Llama")
                            final_decisions.append(None) # Placeholder
                            llama_candidates_indices.append(i)
                            llama_candidates_summaries.append(summaries[i])
                    
                    # 3. Run Llama for Ambiguous Cases
                    if llama_candidates_summaries:
                        logger.info(f"  🦙 Calling Llama 70B for {len(llama_candidates_summaries)} items...")
                        llama_results = self.models.verify_match_llama_batch(full_text, llama_candidates_summaries)
                        
                        # Merge results back
                        for idx, is_match in zip(llama_candidates_indices, llama_results):
                            final_decisions[idx] = is_match
                            if is_match:
                                logger.info(f"    ✅ Llama ACCEPT: {top_5_items[idx]['data'][1]}")
                            else:
                                logger.info(f"    ❌ Llama REJECT: {top_5_items[idx]['data'][1]}")

                    # 4. Find Best Match
                    for i, is_match in enumerate(final_decisions):
                        if is_match:
                            best_match = top_5_items[i]["data"]
                            best_score = top_5_items[i]["score"]
                            break # First valid match is best match (sorted by score)
                
                # 4. ASSIGNMENT
                if best_match:
                    cluster_id, label, summary, cluster_entities_json, count, last_updated, distance, latest_post_time = best_match
                    logger.info(f"Matched Cluster: {label} (Score: {best_score:.2f})")
                    self.update_cluster(uri, cluster_id, full_text, embedding, count, summary, created_at)
                else:
                    # Create New
                    self.create_cluster(uri, full_text, embedding, post_entities, created_at)
                
                self.mark_processed(uri)
            
            # Only sleep if we processed a batch to avoid hammering CPU, but short enough to clear backlog
            # Cerebras Limit: 14,400/day (~10/min). Sleep 10s (Retry logic handles spikes).
            logger.info("Batch complete. Checking for more...")
            time.sleep(10)

if __name__ == "__main__":
    pipeline = Pipeline()
    pipeline.run()
