import logging
from sentence_transformers import SentenceTransformer
from gliner import GLiNER
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
import logging
from sentence_transformers import SentenceTransformer
from gliner import GLiNER
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
import os
from dotenv import load_dotenv

import requests
import concurrent.futures
import time
from openai import OpenAI  # Changed from Groq

logger = logging.getLogger(__name__)

# Load .env explicitly to ensure API keys are available
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup Cerebras
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = "llama-3.3-70b"

if not CEREBRAS_API_KEY:
    logger.warning("CEREBRAS_API_KEY not found in .env! Llama calls will fail.")

class LocalModels:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading models on {self.device}...")

        # Initialize Cerebras Client (via OpenAI SDK)
        if CEREBRAS_API_KEY:
            self.client = OpenAI(
                base_url="https://api.cerebras.ai/v1",
                api_key=CEREBRAS_API_KEY
            )
            logger.info(f"Cerebras Client initialized with model: {CEREBRAS_MODEL}")
        else:
            self.client = None

        # 1. SBERT (Vector Embeddings)
        logger.info("Loading SBERT (all-MiniLM-L6-v2)...")
        self.sbert = SentenceTransformer('all-MiniLM-L6-v2', device=self.device)

        # 2. GLiNER (Entity Extraction)
        logger.info("Loading GLiNER (gliner_small-v2.1)...")
        self.gliner = GLiNER.from_pretrained("urchade/gliner_small-v2.1").to(self.device)

        # 3. ModernBERT (Noise Filter)
        # Load locally trained model
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        MODEL_PATH = os.path.join(BASE_DIR, "../models/noise_filter_v1")
        
        if os.path.exists(MODEL_PATH):
            logger.info(f"Loading Noise Filter from {MODEL_PATH}...")
            self.noise_tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
            self.noise_model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH).to(self.device)
            self.noise_model.eval()
            self.use_trained_filter = True
        else:
            logger.warning(f"Trained model not found at {MODEL_PATH}. Falling back to Zero-Shot.")
            self.noise_classifier = pipeline("zero-shot-classification", model="cross-encoder/nli-deberta-v3-xsmall", device=0 if self.device == "cuda" else -1)
            self.use_trained_filter = False

        # 4. Cross-Encoder (Local Tie-Breaker)
        # Much more accurate than SBERT for pair comparison, and runs locally (No Rate Limits!)
        from sentence_transformers import CrossEncoder
        logger.info("Loading Cross-Encoder (ms-marco-MiniLM-L-6-v2)...")
        self.cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', device=self.device)

        # 5. Summarizer (Local Headlines) - REMOVED
        # We now use Groq (Llama 3) for headlines to save RAM.
        # self.summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6", device=0 if self.device == "cuda" else -1)

    def get_embedding(self, text):
        return self.sbert.encode(text).tolist()

    def extract_entities(self, text):
        # Extract Person, Organization, Location, etc.
        labels = ["person", "organization", "location", "product", "event"]
        entities = self.gliner.predict_entities(text, labels)
        return [{"text": e["text"], "label": e["label"]} for e in entities]

    def is_noise(self, text):
        # Returns True if Noise, False if Signal
        if not text or not text.strip():
            return True

        if self.use_trained_filter:
            # 0 = Noise, 1 = Financial News
            inputs = self.noise_tokenizer(text, return_tensors="pt", truncation=True, max_length=256, padding=True).to(self.device)
            with torch.no_grad():
                outputs = self.noise_model(**inputs)
            
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predicted_class = torch.argmax(probs, dim=-1).item()
            
            # If class is 0 (Noise), return True
            return predicted_class == 0
        else:
            # Fallback
            candidate_labels = ["financial news", "market update", "breaking news", "world events", "spam", "personal chatter", "crypto shilling"]
            result = self.noise_classifier(text, candidate_labels)
            
            top_label = result['labels'][0]
            score = result['scores'][0]
            
            if top_label in ["spam", "personal chatter", "crypto shilling"] and score > 0.65:
                return True
            return False

    def verify_match(self, text1, text2, threshold=0.5):
        # Uses Cross-Encoder to check if two texts are semantically similar
        # Returns True if similarity > threshold
        score = self.cross_encoder.predict([text1, text2])
        return score > threshold

    def verify_match_gatekeeper(self, text1, candidates):
        """
        Hybrid Gatekeeper using Cross-Encoder.
        Returns a list of results:
        - True: Safe Accept (High Confidence Match)
        - False: Safe Reject (High Confidence Non-Match)
        - None: Ambiguous (Needs Llama Verification)
        """
        # Thresholds from Verification (Conservative)
        UPPER_THRESHOLD = 9.0  # Auto-Accept
        LOWER_THRESHOLD = -8.0 # Auto-Reject
        
        pairs = [[text1, cand_summary] for cand_summary in candidates]
        scores = self.cross_encoder.predict(pairs)
        
        results = []
        for score in scores:
            if score > UPPER_THRESHOLD:
                results.append(True)
            elif score < LOWER_THRESHOLD:
                results.append(False)
            else:
                results.append(None) # Ambiguous
                
        return results, scores

    def verify_match_llama_batch(self, text1, candidates):
        """
        Optimized Batch Verification using Cerebras (Llama 3.1 70B).
        Sends ONE prompt with all candidates to save API calls.
        
        candidates: List of tuples (id, label, summary, ...) or just strings?
        The pipeline passes a list of summaries. 
        BUT, to return the correct index, we need to map them back.
        
        Refactored Signature:
        candidates: List of strings (summaries).
        Returns: List of Booleans [True, False, ...]
        """
        if not self.client:
            logger.error("Cerebras Client not initialized. Skipping Llama verification.")
            return [False] * len(candidates)

        # 1. Construct the Batch Prompt
        c_text = ""
        for i, summary in enumerate(candidates):
            c_text += f"ID: {i} | Summary: {summary}\n"
            
        # Truncate input to save tokens (Headlines usually in first 250 chars)
        text1_trunc = text1[:250]
            
        prompt = f"""
        TASK: De-Duplication. Match TWEET to CLUSTER ID.
        
        STRICT RULES:
        1. Entity/Location Mismatch = FATAL.
        2. Ignore Source/URL matches.
        3. Significant Updates (e.g. "Death toll rises") = MATCH.

        TWEET: 
        "{text1_trunc}"

        CLUSTERS:
        {c_text}

        OUTPUT FORMAT:
        REASONING: [Max 10 words]
        ID: [ID or None]
        """
        
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=CEREBRAS_MODEL,
                temperature=0,
                max_tokens=50, # Reduced further
            )
            result = chat_completion.choices[0].message.content.strip()
            logger.info(f"Batch Verification Result:\n{result}")
            
            # Parse Result (Looking for "ID: <number>" or "ID: None")
            bool_results = [False] * len(candidates)
            
            import re
            # Find ALL occurrences of "ID: <val>" to avoid matching mentions in reasoning (e.g. "Cluster ID: 0 says...")
            # We assume the FINAL "ID: ..." is the verdict.
            matches = re.findall(r'ID:\s*(None|\d+)', result, re.IGNORECASE)
            
            if matches:
                final_val = matches[-1]
                if final_val.lower() == "none":
                    pass # Explicit None, do nothing (bool_results remains all False)
                else:
                    idx = int(final_val)
                    if 0 <= idx < len(candidates):
                        bool_results[idx] = True
                        logger.info(f"Batch Match Parsed: Index {idx}")
            else:
                 logger.warning(f"Could not parse batch result: {result}")
            
            return bool_results

        except Exception as e:
            logger.error(f"Cerebras Batch Verification failed: {e}")
            return [False] * len(candidates)

    # def generate_headline(self, text):
    #     # Generates a short summary/headline
    #     try:
    #         # Max length 20 tokens (~15 words), min length 5
    #         summary = self.summarizer(text, max_length=20, min_length=5, do_sample=False)[0]['summary_text']
    #         return summary.strip()
    #     except Exception as e:
    #         logger.error(f"Summarization failed: {e}")
    #         return "Breaking News"

    def generate_headline_llama(self, posts_text):
        # Uses Cerebras (Llama 3.1 70B) to generate a Bloomberg-style headline
        if not self.client:
            logger.error("Cerebras Client not initialized. Skipping Llama headline.")
            return "Breaking News"

        prompt = f"""
        Write a SINGLE, Bloomberg-style breaking news headline (Max 10 words) for these tweets.
        Focus on specific entities and numbers. Use active voice.
        Output ONLY the headline. No intro/outro.

        Tweets:
        {posts_text}
        
        Headline:
        """
        
        try:
            start_time = time.time()
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=CEREBRAS_MODEL,
                temperature=0,
                max_tokens=50, 
            )
            duration = time.time() - start_time
            result = chat_completion.choices[0].message.content.strip().replace('"', '')
            
            # Safety Clean: Remove common AI prefixes and notes
            # 1. Take first non-empty line
            lines = [line.strip() for line in result.splitlines() if line.strip()]
            clean_response = lines[0] if lines else "Breaking News"

            # 2. Remove prefixes
            for prefix in ["Here is", "Here are", "Sure,", "Headline:", "Based on", "The headline is"]:
                if clean_response.lower().startswith(prefix.lower()):
                    if ":" in clean_response:
                        clean_response = clean_response.split(':', 1)[1].strip()
                    else:
                        # If no colon, just remove the prefix? Risk of removing part of headline.
                        # Usually "Here is the headline" is followed by the headline.
                        pass 
            
            # 3. Remove parenthetical notes at the end
            import re
            clean_response = re.sub(r'\s*\(Note:.*\).*$', '', clean_response, flags=re.IGNORECASE)
            clean_response = re.sub(r'\s*\(Note.*\).*$', '', clean_response, flags=re.IGNORECASE)
            
            logger.info(f"Cerebras Headline Generated in {duration:.2f}s: {clean_response}")
            return clean_response
        except Exception as e:
            logger.error(f"Cerebras Headline failed: {e}")
            return "Breaking News"
