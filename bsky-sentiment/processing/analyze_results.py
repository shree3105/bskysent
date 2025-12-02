import os
import sys
import pandas as pd
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Force UTF-8 for Windows Console
sys.stdout.reconfigure(encoding='utf-8')

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def analyze():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found.")
        return

    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        print("\n--- PHASE 2 PERFORMANCE REPORT ---\n")

        # 1. NOISE FILTER PERFORMANCE
        total_processed = conn.execute(text("SELECT COUNT(*) FROM raw_posts WHERE is_processed = TRUE")).scalar()
        total_clustered = conn.execute(text("SELECT COUNT(*) FROM processed_posts")).scalar()
        
        if total_processed == 0:
            print("No posts processed yet. Run the pipeline first!")
            return

        noise_count = total_processed - total_clustered
        noise_rate = (noise_count / total_processed) * 100
        
        print(f"📊 TRAFFIC ANALYSIS")
        print(f"   Total Processed:   {total_processed}")
        print(f"   Kept (Signal):     {total_clustered}")
        print(f"   Dropped (Noise):   {noise_count} ({noise_rate:.1f}%)")
        print("-" * 40)

        # 2. CLUSTER HEALTH
        total_clusters = conn.execute(text("SELECT COUNT(*) FROM clusters")).scalar()
        if total_clusters > 0:
            avg_size = total_clustered / total_clusters
            singletons = conn.execute(text("SELECT COUNT(*) FROM clusters WHERE post_count = 1")).scalar()
            singleton_rate = (singletons / total_clusters) * 100
            
            print(f"🧩 CLUSTER METRICS")
            print(f"   Total Clusters:    {total_clusters}")
            print(f"   Avg Cluster Size:  {avg_size:.1f} posts")
            print(f"   Singletons (1 post): {singletons} ({singleton_rate:.1f}%)")
            
            if singleton_rate > 80:
                print("   ⚠️  High Singleton Rate: Thresholds might be too strict (under-merging).")
            elif avg_size > 50:
                print("   ⚠️  Huge Clusters: Thresholds might be too loose (over-merging).")
            else:
                print("   ✅  Healthy Clustering.")
        print("-" * 40)

        # 3. TOP STORIES
        print(f"🏆 TOP ACTIVE STORIES")
        df = pd.read_sql(text("SELECT label, post_count, last_updated FROM clusters ORDER BY post_count DESC LIMIT 10"), conn)
        if not df.empty:
            print(df.to_string(index=False))
        else:
            print("   No clusters found.")
        print("\n" + "=" * 40 + "\n")

if __name__ == "__main__":
    analyze()
