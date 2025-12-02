import os
import time
import logging
import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db_engine, init_db, RawPost, ProcessedPost, Topic, TopicScore, SessionLocal
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import ollama
from dotenv import load_dotenv
import re

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '../ingestion/.env'))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
SIMILARITY_THRESHOLD = 0.25 # Tuned to 0.25 (Stricter to prevent lumping)
LLAMA_MODEL = 'llama3'
SCORING_INTERVAL_MINUTES = 15

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
import joblib

class Processor:
    def __init__(self):
        self.engine = get_db_engine()
        SessionLocal.configure(bind=self.engine)
        init_db(self.engine)
        
        logger.info(f"Loading BERT model: {EMBEDDING_MODEL}...")
        logger.info(f"Connected to DB: {self.engine.url}")
        self.bert = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("BERT model loaded.")
        
        # Initialize Naive Bayes Noise Filter
        self.nb_model = None
        self.load_noise_filter()

    def load_noise_filter(self):
        """Loads pre-trained Naive Bayes classifier."""
        try:
            model_path = os.path.join(os.path.dirname(__file__), 'noise_filter.joblib')
            if os.path.exists(model_path):
                self.nb_model = joblib.load(model_path)
                logger.info(f"Loaded Naive Bayes Noise Filter from {model_path}")
            else:
                logger.warning("No pre-trained noise filter found. Training from DB...")
                self.train_noise_filter()
        except Exception as e:
            logger.error(f"Failed to load NB filter: {e}")

    def train_noise_filter(self):
        """Trains a Naive Bayes classifier on existing Noise vs Signal data."""
        session = SessionLocal()
        try:
            # 1. Get Noise Posts
            noise_topics = session.query(Topic.id).filter(Topic.label == "Noise").all()
            noise_ids = [t.id for t in noise_topics]
            
            if not noise_ids:
                logger.warning("No Noise topics found. Skipping NB training.")
                return

            noise_posts = session.query(RawPost.content).\
                join(ProcessedPost, RawPost.uri == ProcessedPost.uri).\
                filter(ProcessedPost.topic_id.in_(noise_ids)).limit(1000).all()
            
            # 2. Get Signal Posts (Resolved, Not Noise)
            signal_posts = session.query(RawPost.content).\
                join(ProcessedPost, RawPost.uri == ProcessedPost.uri).\
                join(Topic, ProcessedPost.topic_id == Topic.id).\
                filter(Topic.label != "Noise", ~Topic.label.like("PENDING:%")).limit(1000).all()
            
            if not noise_posts or not signal_posts:
                logger.warning("Insufficient data for NB training.")
                return

            X = [p.content for p in noise_posts] + [p.content for p in signal_posts]
            y = ["Noise"] * len(noise_posts) + ["Signal"] * len(signal_posts)
            
            self.nb_model = make_pipeline(CountVectorizer(), MultinomialNB())
            self.nb_model.fit(X, y)
            logger.info(f"Naive Bayes Noise Filter trained on {len(noise_posts)} Noise and {len(signal_posts)} Signal posts.")
            
        except Exception as e:
            logger.error(f"Failed to train NB filter: {e}")
        finally:
            session.close()

    def get_unprocessed_posts(self, limit=100):
        session = SessionLocal()
        try:
            posts = session.query(RawPost).filter(RawPost.is_processed == False).order_by(RawPost.created_at.asc()).limit(limit).all()
            return posts
        finally:
            session.close()

    def get_active_topics(self):
        session = SessionLocal()
        try:
            # Get topics updated in the last 2 hours (Archived after 2h)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            topics = session.query(Topic).filter(Topic.last_updated >= cutoff).all()
            return topics
        finally:
            session.close()

    def find_topic(self, post_embedding, active_topics, topic_embeddings, post_embedding_text):
        """Finds the best matching topic using pre-computed embeddings."""
        if not active_topics:
            return None

        # Calculate similarities against all topics at once
        similarities = cosine_similarity([post_embedding], topic_embeddings)[0]
        
        max_idx = np.argmax(similarities)
        score = similarities[max_idx]
        topic = active_topics[max_idx]
        
        # GENERIC LABELS LIST (Should match the one in resolve_pending_topics)
        GENERIC_LABELS = {
            "NOISE", "TECH NEWS", "FINANCIAL NEWS", "SPORTS NEWS", "TRADE TALKS", 
            "ECONOMY", "NEWS", "FINANCE", "OUTLOOK", "SOCCER NEWS", "AIRPORT NEWS",
            "PERSONAL", "COOKING DISASTER", "MEDIA CRITICISM", "TECH CRITICISM", "ECONOMY NEWS", "FOOTBALL NEWS"
        }
        is_generic = topic.label.upper() in GENERIC_LABELS

        # Debug log for high-ish scores
        if score > 0.25:
            logger.info(f"BERT Match Candidate: {topic.label} ({score:.2f}) [Generic={is_generic}]")
        
        # THRESHOLDS
        # If Generic: Be stricter. Need higher score or explicit entity match.
        # If Specific: Standard thresholds.
        
        HIGH_CONFIDENCE = 0.55 if is_generic else 0.45
        ENTITY_CHECK_MIN = 0.25
        ENTITY_CHECK_MAX = 0.55 if is_generic else 0.45

        # 1. High Confidence Match (Skip Entity Check)
        if score > HIGH_CONFIDENCE:
             return topic

        # 2. Borderline / Entity Check Window
        if ENTITY_CHECK_MIN <= score <= ENTITY_CHECK_MAX:
            # Label Match Bypass: If the topic label is explicitly in the text, match it.
            # (Unless it's generic, then we ignore this because "News" is in everything)
            if not is_generic and topic.label.lower() in post_embedding_text.lower():
                logger.info(f"Confirming match '{topic.label}' ({score:.2f}) due to label match.")
                return topic

            # Entity Check
            post_entities = self.extract_entities(self.clean_text(post_embedding_text))
            topic_entities = self.extract_entities(topic.label + " " + topic.keywords)
            
            common_entities = post_entities.intersection(topic_entities)
            
            if common_entities:
                logger.info(f"Confirming match '{topic.label}' ({score:.2f}) due to shared entities: {common_entities}")
                return topic
            else:
                logger.info(f"Rejecting match '{topic.label}' ({score:.2f}) due to lack of shared entities.")
                return None

        return None

    def create_new_topic(self, session, post_content, embedding, active_topics):
        """Creates a new PENDING topic. Labeling is deferred until enough posts accumulate."""
        
        # Clean content for keywords
        cleaned_content = self.clean_text(post_content)
        if not cleaned_content:
            cleaned_content = post_content # Fallback if cleaning removes everything (unlikely)

        # Create new topic
        topic_id = f"topic_{int(time.time())}_{np.random.randint(0, 1000)}"
        new_topic = Topic(
            id=topic_id,
            label=f"PENDING:{topic_id}",
            keywords=cleaned_content, # Use cleaned content
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc)
        )
        session.add(new_topic)
        session.flush() # Get ID
        logger.info(f"Created new PENDING topic: {topic_id}")
        return new_topic

    def resolve_pending_topics(self):
        """Checks pending topics and labels them if they have enough posts."""
        session = SessionLocal()
        try:
            # 1. Find all PENDING topics
            pending_topics = session.query(Topic).filter(Topic.label.like("PENDING:%")).all()
            if not pending_topics:
                return

            MIN_POSTS_TO_LABEL = 2 # Lowered to 2 for faster detection (User Request)
            
            for topic in pending_topics:
                # 2. Count posts
                post_count = session.query(func.count(ProcessedPost.uri)).filter(ProcessedPost.topic_id == topic.id).scalar()
                
                if post_count >= MIN_POSTS_TO_LABEL:
                    logger.info(f"Resolving Pending Topic {topic.id} (Count: {post_count})...")
                    
                    # 3. Get posts for context
                    posts = session.query(RawPost.content).\
                        join(ProcessedPost, RawPost.uri == ProcessedPost.uri).\
                        filter(ProcessedPost.topic_id == topic.id).\
                        limit(10).all()
                    
                    summary_text = "\n".join([p.content for p in posts])
                    
                    # 4. Call Llama
                    resolved_topics = session.query(Topic.label).filter(Topic.label.notlike("PENDING:%")).order_by(Topic.last_updated.desc()).limit(50).all()
                    
                    GENERIC_LABELS = {
                        "NOISE", "TECH NEWS", "FINANCIAL NEWS", "SPORTS NEWS", "TRADE TALKS", 
                        "ECONOMY", "NEWS", "FINANCE", "OUTLOOK", "SOCCER NEWS", "AIRPORT NEWS",
                        "PERSONAL", "COOKING DISASTER", "MEDIA CRITICISM", "TECH CRITICISM", 
                        "ECONOMY NEWS", "FOOTBALL NEWS", "STOCK MARKET", "MARKET UPDATE",
                        "US STOCK MARKET", "TV SHOW", "REACTION", "MEME", "JOKE",
                        "CENTRAL BANK COMMENTS", "STOCK MARKET UPDATE", "WHAT", "WHO", "WHY",
                        "POLITICS", "US POLITICS", "OPINION", "COMMENTARY"
                    }
                    
                    existing_labels_str = ", ".join([t.label for t in resolved_topics if t.label.upper() not in GENERIC_LABELS])

                    try:
                        response = ollama.chat(model=LLAMA_MODEL, messages=[
                            {'role': 'system', 'content': f"You are a topic classifier. Existing topics: [{existing_labels_str}].\n\nRules:\n1. If the tweets fit an existing topic, return EXACTLY that label.\n2. If it's a new event, create a specific 2-4 word label (e.g. 'Washington Shooting', 'Housing Market Drop', 'Nvidia Earnings', 'US-China Trade').\n3. DO NOT use generic labels like 'Economy', 'News', 'Finance', 'Stock Market', 'Market Update', 'TV Show', 'Central Bank Comments'.\n4. DO NOT simply copy the first few words of the tweet. Summarize the EVENT.\n5. ALWAYS include the specific Entity + Event (e.g. instead of 'Trade Talks', use 'US-China Trade').\n6. If it is personal/spam/irrelevant/reaction (e.g. 'lol', 'no', 'Jesus', 'meme'), return 'IRRELEVANT'."},
                            {'role': 'user', 'content': f"Tweets:\n{summary_text}\n\nLabel:"}
                        ])
                        raw_label = response['message']['content'].strip().replace('"', '').replace("'", "")
                        if ":" in raw_label: label = raw_label.split(":")[-1].strip()
                        else: label = raw_label
                        
                        logger.info(f"Llama resolved '{topic.id}' to: '{label}'")
                        
                        # Handle IRRELEVANT/GENERIC
                        clean_label_upper = label.upper()
                        
                        # Filter out single words (unless they are likely specific entities, but for now assume single word = bad/generic)
                        # Exception: "Bitcoin", "Nvidia" might be single words but usually we want "Bitcoin Rally" etc.
                        is_single_word = len(label.split()) < 2
                        
                        if "IRRELEVANT" in clean_label_upper or len(label) < 3 or clean_label_upper in GENERIC_LABELS or is_single_word:
                            label = "Noise"
                        else:
                            # LABEL NORMALIZATION: Title Case to prevent duplicates (e.g. "Champions League")
                            label = label.title()
                        
                        # Check for merge with existing (Case Insensitive)
                        existing_topic = session.query(Topic).filter(func.lower(Topic.label) == label.lower()).first()
                        if existing_topic and existing_topic.id != topic.id:
                            logger.info(f"Merging {topic.id} into existing {existing_topic.id} ({label})")
                            # Update posts to point to existing topic
                            session.query(ProcessedPost).filter(ProcessedPost.topic_id == topic.id).update({"topic_id": existing_topic.id})
                            session.delete(topic)
                        else:
                            topic.label = label
                            # PRESERVE CONTEXT: Prepend label, but keep existing keywords (centroid)
                            current_keywords = topic.keywords or ""
                            topic.keywords = (label + " " + current_keywords)[:1000] 
                        
                        session.commit()

                    except Exception as e:
                        logger.error(f"Llama failed to resolve topic {topic.id}: {e}")

        except Exception as e:
            logger.error(f"Resolve pending topics failed: {e}")
            session.rollback()
        finally:
            session.close()

    def extract_entities(self, text):
        """Extracts potential named entities (capitalized words) from text."""
        # Simple heuristic: Capitalized words (excluding start of sentence if possible, but simple regex here)
        candidates = set(re.findall(r'\b[A-Z][a-zA-Z0-9]+\b', text))
        STOPWORDS = {"The", "A", "An", "In", "On", "At", "To", "For", "Of", "With", "By", "From", "And", "But", "Or", "So", "Yet", "Nor", "It", "Is", "Are", "Was", "Were", "Be", "Been", "Has", "Have", "Had", "Do", "Does", "Did", "Can", "Could", "Will", "Would", "Shall", "Should", "May", "Might", "Must", "My", "Your", "His", "Her", "Its", "Our", "Their", "This", "That", "These", "Those", "Here", "There", "Where", "When", "Why", "How", "What", "Who", "Whom", "Whose", "Which", "We", "You", "They", "He", "She", "It", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "News", "Update", "Daily", "Weekly", "Report"}
        return {w for w in candidates if w not in STOPWORDS and len(w) > 2}

    def cleanup_stale_topics(self):
        """Removes PENDING topics that are older than 1 hour and haven't been resolved."""
        session = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            stale_topics = session.query(Topic).filter(
                Topic.label.like("PENDING:%"),
                Topic.created_at < cutoff
            ).all()
            
            if stale_topics:
                logger.info(f"Cleaning up {len(stale_topics)} stale PENDING topics...")
                for t in stale_topics:
                    session.delete(t)
                session.commit()
        except Exception as e:
            logger.error(f"Cleanup stale topics failed: {e}")
            session.rollback()
        finally:
            session.close()

    def merge_resolved_topics(self):
        """Periodically checks for resolved topics that are semantically identical and merges them."""
        session = SessionLocal()
        try:
            # 1. Get all RESOLVED topics (updated recently)
            # SYNC WITH ARCHIVE TIME: Only merge topics active in the last 2 hours
            cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            topics = session.query(Topic).filter(
                Topic.label.notlike("PENDING:%"),
                Topic.label != "Noise",
                Topic.last_updated >= cutoff
            ).all()
            
            if len(topics) < 2:
                return

            # 2. Generate Embeddings for Labels + Keywords
            topic_texts = [t.label + " " + (t.keywords or "") for t in topics]
            embeddings = self.bert.encode(topic_texts)
            
            # 3. Calculate Similarity Matrix
            similarity_matrix = cosine_similarity(embeddings)
            
            # 4. Find Candidates (> 0.75 similarity - HIGHER THRESHOLD)
            # We iterate upper triangle to avoid duplicates and self-matches
            merge_candidates = []
            for i in range(len(topics)):
                for j in range(i + 1, len(topics)):
                    score = similarity_matrix[i][j]
                    if score > 0.75:
                        # SMART FILTER: Check for shared entities
                        t1_entities = self.extract_entities(topics[i].label + " " + topics[i].keywords)
                        t2_entities = self.extract_entities(topics[j].label + " " + topics[j].keywords)
                        
                        # If both have entities, they MUST share at least one to be considered
                        if t1_entities and t2_entities:
                            if not t1_entities.intersection(t2_entities):
                                # High similarity but NO shared entities -> Likely distinct events (e.g. "Apple Earnings" vs "Tesla Earnings")
                                # Skip unless score is extremely high (> 0.90)
                                if score < 0.90:
                                    continue
                        
                        merge_candidates.append((topics[i], topics[j], score))
            
            if not merge_candidates:
                return

            # Sort by score (Highest first) to prioritize best matches
            merge_candidates.sort(key=lambda x: x[2], reverse=True)
            
            # Limit to top 10 to prevent "Merge Explosion"
            merge_candidates = merge_candidates[:10]

            logger.info(f"Found {len(merge_candidates)} high-prob merge candidates. Verifying with Llama...")

            for t1, t2, score in merge_candidates:
                # Double check they still exist (might have been merged in previous iteration)
                if session.query(Topic).filter(Topic.id == t1.id).first() is None: continue
                if session.query(Topic).filter(Topic.id == t2.id).first() is None: continue

                # Ask Llama
                try:
                    prompt = f"""
                    Are these two news topics referring to the EXACT SAME event?
                    Topic A: {t1.label} (Keywords: {t1.keywords[:200]}...)
                    Topic B: {t2.label} (Keywords: {t2.keywords[:200]}...)
                    
                    Reply strictly with YES or NO.
                    """
                    response = ollama.chat(model=LLAMA_MODEL, messages=[{'role': 'user', 'content': prompt}])
                    answer = response['message']['content'].strip().upper()
                    
                    if "YES" in answer:
                        logger.info(f"MERGING: '{t1.label}' and '{t2.label}' (Score: {score:.2f}) -> YES")
                        
                        # Merge t2 into t1 (Arbitrary direction, keep t1)
                        # 1. Move posts
                        session.query(ProcessedPost).filter(ProcessedPost.topic_id == t2.id).update({"topic_id": t1.id})
                        
                        # 2. Merge keywords (simple concat + truncate)
                        new_keywords = (t1.keywords + " " + t2.keywords)[:1000]
                        t1.keywords = new_keywords
                        t1.last_updated = datetime.now(timezone.utc)
                        
                        # 3. Delete t2
                        session.delete(t2)
                        session.commit()
                    else:
                        logger.info(f"Keeping separate: '{t1.label}' and '{t2.label}' (Score: {score:.2f}) -> NO")
                        
                except Exception as e:
                    logger.error(f"Merge check failed for {t1.label} vs {t2.label}: {e}")

        except Exception as e:
            logger.error(f"Merge resolved topics failed: {e}")
            session.rollback()
        finally:
            session.close()

    def process_batch(self):
        posts = self.get_unprocessed_posts()
        if not posts:
            return 0

        logger.info(f"Processing batch of {len(posts)} posts...")
        
        # Generate embeddings for POSTS
        contents = [p.content + (" " + p.quote_content if p.quote_content else "") for p in posts]
        post_embeddings = self.bert.encode(contents)
        
        active_topics = self.get_active_topics()
        
        # Generate embeddings for TOPICS (Once per batch)
        if active_topics:
            topic_strings = []
            for t in active_topics:
                if t.label.startswith("PENDING:"):
                    topic_strings.append(t.keywords) 
                else:
                    topic_strings.append(t.label + " " + t.keywords)
            
            topic_embeddings = self.bert.encode(topic_strings)
        else:
            topic_embeddings = []
        
        session = SessionLocal()
        try:
            for i, post in enumerate(posts):
                # 0. HARD NOISE FILTER (Pre-Bayes)
                # Filter out very short posts or specific noise words
                clean_content = post.content.strip().lower()
                noise_words = {"what", "lol", "no", "yes", "wow", "omg", "jesus", "damn", "shit", "fuck", "why", "stop", "womp womp"}
                
                is_hard_noise = False
                if len(clean_content) < 5: # Very short
                    is_hard_noise = True
                elif clean_content in noise_words: # Exact match noise word
                    is_hard_noise = True
                elif len(clean_content.split()) < 2 and clean_content not in ["oil up", "gold up", "btc up"]: # Single word (mostly noise)
                    is_hard_noise = True
                
                if is_hard_noise:
                    logger.info(f"Hard Filter: '{post.content}' -> Noise")
                    is_noise = True
                else:
                    # NAIVE BAYES FILTER
                    is_noise = False
                    if self.nb_model:
                        try:
                            # Index 0 is "Noise" usually, check classes_
                            noise_idx = list(self.nb_model.classes_).index("Noise")
                            prob_noise = self.nb_model.predict_proba([post.content])[0][noise_idx]
                            
                            if prob_noise > 0.80: # High confidence noise
                                is_noise = True
                                logger.info(f"Noise Filter: '{post.content[:30]}...' (Prob: {prob_noise:.2f})")
                        except Exception as e:
                            logger.warning(f"NB prediction failed: {e}")

                if is_noise:
                    noise_topic = session.query(Topic).filter(Topic.label == "Noise").order_by(Topic.last_updated.desc()).first()
                    if not noise_topic:
                        noise_topic = Topic(id=f"topic_noise_{int(time.time())}", label="Noise", keywords="Generic Noise", created_at=datetime.now(timezone.utc), last_updated=datetime.now(timezone.utc))
                        session.add(noise_topic)
                        session.flush()
                    topic = noise_topic
                else:
                    # NORMAL CLUSTERING (BERT)
                    topic = self.find_topic(post_embeddings[i], active_topics, topic_embeddings, post.content)
                    
                    if not topic:
                        topic = self.create_new_topic(session, post.content, post_embeddings[i], active_topics)
                        # Only append if it's actually new (not in active_topics)
                        if topic and topic not in active_topics:
                            active_topics.append(topic)
                            # Re-compute embeddings for the new topic and append
                            new_topic_embedding = self.bert.encode([topic.label + " " + topic.keywords])
                            if len(topic_embeddings) > 0:
                                topic_embeddings = np.vstack([topic_embeddings, new_topic_embedding])
                            else:
                                topic_embeddings = new_topic_embedding
                
                # Save ProcessedPost
                if topic:
                    # Fix for SQLAlchemy conflict: Ensure topic is attached to this session
                    topic = session.merge(topic)

                    processed = ProcessedPost(
                        uri=post.uri,
                        topic_id=topic.id
                    )
                    session.merge(processed) # Upsert
                    
                    # Mark RawPost as processed
                    db_post = session.query(RawPost).filter_by(uri=post.uri).first()
                    if db_post:
                        db_post.is_processed = True
                    
                    # Update Topic last_updated
                    topic.last_updated = datetime.now(timezone.utc)
                    
                    # CENTROID UPDATE: Rolling Window for ALL topics
                    current_content = topic.keywords or ""
                    
                    # Deduplicate: Don't add if already present
                    if post.content not in current_content:
                        # Clean text before appending
                        cleaned_post = self.clean_text(post.content)
                        if cleaned_post:
                            # Append new content
                            new_content = current_content + " " + cleaned_post
                            
                            # Sliding Window: Keep last ~1000 chars (Newest Context)
                            if len(new_content) > 1000:
                                new_content = new_content[-1000:] # Keep the NEWEST text
                                # Clean up partial word at the start
                                first_space = new_content.find(" ")
                                if first_space != -1:
                                    new_content = new_content[first_space+1:]
                            
                            topic.keywords = new_content
                            session.add(topic) # Ensure update is tracked

            logger.info("Committing batch transaction...")
            session.commit()
            logger.info("Batch processed successfully.")
            return len(posts)
        except Exception as e:
            import traceback
            logger.error(f"Batch processing failed: {e}")
            logger.error(traceback.format_exc())
            session.rollback()
            return 0
        finally:
            session.close()

    def run_scoring(self):
        """Runs periodic scoring for topics."""
        session = SessionLocal()
        try:
            # 1. Get last scored time from SystemState
            from database import SystemState
            state = session.query(SystemState).filter_by(key="last_scored_time").first()
            
            if not state:
                # Initialize with the time of the first raw post
                first_post = session.query(func.min(RawPost.created_at)).scalar()
                if not first_post:
                    return # No data at all
                # Round down to nearest 15 min
                start_time = first_post.replace(second=0, microsecond=0)
                start_time = start_time - timedelta(minutes=start_time.minute % SCORING_INTERVAL_MINUTES)
                
                state = SystemState(key="last_scored_time", value=start_time.isoformat())
                session.add(state)
                session.commit()
                last_scored_time = start_time
            else:
                last_scored_time = datetime.fromisoformat(state.value)

            # 2. Calculate next window
            next_bucket_start = last_scored_time + timedelta(minutes=SCORING_INTERVAL_MINUTES)
            next_bucket_end = next_bucket_start + timedelta(minutes=SCORING_INTERVAL_MINUTES)

            # Don't score the future (wait until window is fully passed)
            if next_bucket_end > datetime.now(timezone.utc):
                return

            logger.info(f"Scoring bucket: {next_bucket_start} to {next_bucket_end}")

            # 3. Get posts in this window
            posts_in_window = session.query(RawPost, ProcessedPost.topic_id).\
                join(ProcessedPost, RawPost.uri == ProcessedPost.uri).\
                filter(RawPost.created_at >= next_bucket_start, RawPost.created_at < next_bucket_end).\
                all()

            # 4. Score topics (if any posts)
            if posts_in_window:
                topic_posts = {}
                for post, topic_id in posts_in_window:
                    if topic_id not in topic_posts: topic_posts[topic_id] = []
                    topic_posts[topic_id].append(post.content)

                for topic_id, contents in topic_posts.items():
                    if len(contents) < 3: continue 
                    
                    summary_text = "\n".join(contents[:20])
                    try:
                        response = ollama.chat(model=LLAMA_MODEL, messages=[
                            {'role': 'system', 'content': f"You are a financial sentiment analyst. Analyze the following tweets about '{topic_id}'. Return a JSON object with: danger (0-10), hype (0-10), news_score (0-10, how much is this 'news' vs 'noise'), tickers (comma separated list of relevant tickers), and summary (1 sentence). JSON ONLY. No markdown."},
                            {'role': 'user', 'content': f"Tweets:\n{summary_text}"}
                        ])
                        
                        import json
                        import re
                        content = response['message']['content']
                        
                        # Robust JSON extraction
                        start_idx = content.find('{')
                        end_idx = content.rfind('}')
                        
                        # Auto-close if missing
                        if start_idx != -1 and end_idx == -1:
                            content += "}"
                            end_idx = len(content) - 1

                        if start_idx != -1 and end_idx != -1:
                            json_str = content[start_idx:end_idx+1]
                            json_str = json_str.replace("'", '"')
                            try:
                                data = json.loads(json_str)
                            except json.JSONDecodeError:
                                # Try to clean up common errors (like trailing commas)
                                try:
                                    json_str_clean = re.sub(r',\s*}', '}', json_str)
                                    data = json.loads(json_str_clean)
                                except:
                                    data = {} # Fallback to regex below
                        else:
                            data = {}

                        # Regex Fallback (if JSON parsing failed or no braces found)
                        if not data:
                            if start_idx == -1:
                                logger.warning(f"No JSON braces found in response. Attempting regex fallback.")
                            
                            data['danger'] = float(re.search(r'"danger":\s*([\d\.]+)', content).group(1)) if re.search(r'"danger":\s*([\d\.]+)', content) else 0
                            data['hype'] = float(re.search(r'"hype":\s*([\d\.]+)', content).group(1)) if re.search(r'"hype":\s*([\d\.]+)', content) else 0
                            data['news_score'] = float(re.search(r'"news_score":\s*([\d\.]+)', content).group(1)) if re.search(r'"news_score":\s*([\d\.]+)', content) else 0
                            data['tickers'] = re.search(r'"tickers":\s*"(.*?)"', content).group(1) if re.search(r'"tickers":\s*"(.*?)"', content) else ""
                            data['summary'] = re.search(r'"summary":\s*"(.*?)"', content).group(1) if re.search(r'"summary":\s*"(.*?)"', content) else ""
                            
                            if not data.get('summary'):
                                raise ValueError(f"Could not parse JSON from response: {content[:100]}...")
                        
                        score = TopicScore(
                            topic_id=topic_id,
                            timestamp=next_bucket_start,
                            danger_score=data.get('danger', 0),
                            hype_score=data.get('hype', 0),
                            news_score=data.get('news_score', 0),
                            tickers=data.get('tickers', ''),
                            post_count=len(contents),
                            summary=data.get('summary', '')
                        )
                        session.add(score)
                        logger.info(f"Scored Topic {topic_id}: D={score.danger_score} H={score.hype_score} News={score.news_score} Tickers={score.tickers}")
                    except Exception as e:
                        logger.error(f"Scoring failed for {topic_id}: {e}")

            # 5. Advance the clock
            state.value = next_bucket_start.isoformat()
            session.commit()
            logger.info(f"Advanced scoring clock to {next_bucket_start}")

        except Exception as e:
            logger.error(f"Scoring loop failed: {e}")
            session.rollback()
        finally:
            session.close()

    def clean_text(self, text):
        """Removes URLs, emojis, and special characters."""
        # Remove URLs
        text = re.sub(r'http\S+|www\.\S+', '', text)
        # Remove emojis and special symbols (keep alphanumeric, spaces, and basic punctuation)
        text = re.sub(r'[^\w\s.,!?\'-]', '', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def run(self):
        logger.info(f"Starting Processing Pipeline (Threshold: {SIMILARITY_THRESHOLD})...")
        
        last_merge_time = time.time()
        MERGE_INTERVAL_SECONDS = 900 # 15 minutes
        posts_processed_since_merge = 0
        POSTS_MERGE_TRIGGER = 500 # Merge every 500 posts during catch-up
        
        while True:
            processed_count = self.process_batch()
            
            if processed_count > 0:
                posts_processed_since_merge += processed_count
            
            # Resolve pending topics periodically
            self.resolve_pending_topics()
            
            # Check for Merge (Periodic OR Catch-up)
            time_since_merge = time.time() - last_merge_time
            should_merge = (time_since_merge > MERGE_INTERVAL_SECONDS) or (posts_processed_since_merge >= POSTS_MERGE_TRIGGER)

            if should_merge:
                trigger_reason = "Timer" if time_since_merge > MERGE_INTERVAL_SECONDS else "Post Count"
                logger.info(f"Running Topic Merge ({trigger_reason})...")
                self.merge_resolved_topics()
                last_merge_time = time.time()
                posts_processed_since_merge = 0
            
            if processed_count == 0:
                logger.info("No new posts. Sleeping...")
                time.sleep(10)
            
            # Check if it's time to run scoring
            self.run_scoring()
            
            # Cleanup stale topics (every loop is fine, it's fast)
            self.cleanup_stale_topics()

if __name__ == "__main__":
    processor = Processor()
    processor.run()
