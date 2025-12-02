import os
import logging
from dotenv import load_dotenv
from groq import Groq

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestGroq")

# Load Env
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"

if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY not found!")
    exit(1)

logger.info(f"Testing Groq with model: {GROQ_MODEL}")

client = Groq(api_key=GROQ_API_KEY)

prompt = """
Write a short, breaking news headline for:
"Tesla stock just jumped 5% after Elon Musk announced a new robot."
"""

try:
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model=GROQ_MODEL,
        temperature=0,
        max_tokens=20,
    )
    result = chat_completion.choices[0].message.content.strip()
    logger.info(f"Success! Response: {result}")
except Exception as e:
    logger.error(f"Groq Test Failed: {e}")
