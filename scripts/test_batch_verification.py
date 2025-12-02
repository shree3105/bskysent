import os
import logging
from dotenv import load_dotenv
from groq import Groq

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestBatch")

# Load Env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

# Simulation Data
new_post = "Tesla stock is skyrocketing today after Musk revealed the new Optimus robot is ready for shipping."

candidates = [
    {"id": "cluster_1", "summary": "Apple releases new iPhone 16 with AI features."},
    {"id": "cluster_2", "summary": "SpaceX launches another Starship test flight from Texas."},
    {"id": "cluster_3", "summary": "Tesla shares jump 5% on news of Optimus robot production."},
    {"id": "cluster_4", "summary": "NVIDIA earnings report shows massive growth in AI chip demand."},
    {"id": "cluster_5", "summary": "Elon Musk tweets about Dogecoin going to the moon."}
]

# Construct the Batch Prompt
candidates_text = "\n".join([f"ID: {c['id']} | Summary: {c['summary']}" for c in candidates])

prompt = f"""
You are a news clustering assistant. 
Determine if the NEW POST belongs to any of the existing CLUSTERS.
It must describe the EXACT same specific event.

NEW POST: "{new_post}"

CLUSTERS:
{candidates_text}

INSTRUCTIONS:
- If the post matches a cluster, return ONLY the ID of that cluster.
- If it matches NONE, return "None".
- Do not explain.
"""

logger.info("Sending Batch Request...")

try:
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0,
        max_tokens=10,
    )
    result = chat_completion.choices[0].message.content.strip()
    logger.info(f"Result: {result}")
    
    if result == "cluster_3":
        logger.info("SUCCESS: Correctly identified cluster_3!")
    else:
        logger.error(f"FAILURE: Expected cluster_3, got {result}")

except Exception as e:
    logger.error(f"Error: {e}")
