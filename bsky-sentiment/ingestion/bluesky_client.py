import os
import asyncio
import logging
from atproto import Client, FirehoseSubscribeReposClient, parse_subscribe_repos_message, models, CAR
from atproto import firehose_models
MessageFrame = firehose_models.MessageFrame
from sqlalchemy.orm import Session
from database import RawPost, MonitoredAccount, SessionLocal, get_db_engine
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BlueskyIngester:
    def __init__(self):
        self.handle = os.getenv("BLUESKY_HANDLE")
        self.password = os.getenv("BLUESKY_PASSWORD")
        self.client = Client()
        self.monitored_dids = set()
        self.db_engine = get_db_engine()

    def login(self):
        try:
            self.client.login(self.handle, self.password)
            logger.info(f"Logged in as {self.handle}")
        except Exception as e:
            logger.error(f"Failed to login: {e}")
            raise

    def update_following_list(self):
        """Fetches accounts the user follows and updates the DB/memory."""
        logger.info("Updating following list...")
        session = SessionLocal()
        try:
            # Fetch profile to get own DID
            profile = self.client.get_profile(self.handle)
            own_did = profile.did

            cursor = None
            fetched_count = 0
            
            while True:
                response = self.client.get_follows(actor=own_did, cursor=cursor)
                for follow in response.follows:
                    self.monitored_dids.add(follow.did)
                    
                    # Update DB
                    account = session.query(MonitoredAccount).filter_by(did=follow.did).first()
                    if not account:
                        account = MonitoredAccount(did=follow.did, handle=follow.handle)
                        session.add(account)
                    else:
                        account.handle = follow.handle
                        account.last_updated = datetime.now(timezone.utc)
                    
                    fetched_count += 1

                if not response.cursor:
                    break
                cursor = response.cursor
            
            session.commit()
            logger.info(f"Updated following list. Total monitored: {len(self.monitored_dids)}")
            
        except Exception as e:
            logger.error(f"Error updating following list: {e}")
            session.rollback()
        finally:
            session.close()

    def process_commit(self, commit: models.ComAtprotoSyncSubscribeRepos.Commit, session: Session):
        if commit.repo not in self.monitored_dids:
            return

        # Parse CAR file
        car_file = CAR.from_bytes(commit.blocks)
        
        for op in commit.ops:
            if op.action == 'create' and (op.path.startswith('app.bsky.feed.post') or op.path.startswith('app.bsky.feed.repost')):
                record_raw = car_file.blocks.get(op.cid)
                if not record_raw:
                    continue
                    
                record = models.get_or_create(record_raw, strict=False)
                
                # Check if it's a Post record
                if isinstance(record, models.AppBskyFeedPost.Record):
                    # Construct URI
                    uri = f"at://{commit.repo}/{op.path}"
                    
                    # Check for Quote Post
                    quote_uri = None
                    quote_content = None
                    if hasattr(record, 'embed') and record.embed:
                        # Case 1: Pure Quote
                        if hasattr(record.embed, 'record') and hasattr(record.embed.record, 'uri'):
                            quote_uri = record.embed.record.uri
                        # Case 2: Quote with Media
                        elif hasattr(record.embed, 'record') and hasattr(record.embed.record, 'record') and hasattr(record.embed.record.record, 'uri'):
                             quote_uri = record.embed.record.record.uri
                    
                    if quote_uri:
                        quote_content = self.fetch_quote_content(quote_uri)

                    # Save to DB
                    existing = session.query(RawPost).filter_by(uri=uri).first()
                    if not existing:
                        new_post = RawPost(
                            uri=uri,
                            cid=str(op.cid),
                            author_did=commit.repo,
                            content=record.text,
                            created_at=datetime.fromisoformat(record.created_at.replace('Z', '+00:00')),
                            is_processed=False,
                            quote_uri=quote_uri,
                            quote_content=quote_content
                        )
                        session.add(new_post)
                        clean_text = record.text[:50].replace('\n', ' ')
                        logger.info(f"✅ SAVED POST | User: {commit.repo} | Content: {clean_text}...")

                # Check if it's a Repost record
                elif isinstance(record, models.AppBskyFeedRepost.Record):
                    # For Reposts, the 'subject' is the URI of the original post.
                    # We want to save the CONTENT of the original post, but attribute the action to the reposter.
                    repost_uri = record.subject.uri
                    original_content = self.fetch_quote_content(repost_uri) # Reuse fetch logic
                    
                    if original_content:
                        uri = f"at://{commit.repo}/{op.path}"
                        existing = session.query(RawPost).filter_by(uri=uri).first()
                        if not existing:
                            new_post = RawPost(
                                uri=uri,
                                cid=str(op.cid),
                                author_did=commit.repo,
                                content=original_content, # Save original content as the main content
                                created_at=datetime.fromisoformat(record.created_at.replace('Z', '+00:00')),
                                is_processed=False,
                                repost_uri=repost_uri
                            )
                            session.add(new_post)
                            clean_text = original_content[:50].replace('\n', ' ')
                            logger.info(f"🔄 SAVED REPOST | User: {commit.repo} | Content: {clean_text}...")

    def fetch_quote_content(self, uri):
        """Fetches the content of a quoted post."""
        try:
            # The atproto library's get_posts takes a list of URIs
            response = self.client.get_posts(uris=[uri])
            if response.posts:
                return response.posts[0].record.text
        except Exception as e:
            logger.warning(f"Failed to fetch quote content for {uri}: {e}")
        return None

    def start_firehose(self):
        """Connects to the firehose and listens for events."""
        logger.info("Starting Firehose client...")
        client = FirehoseSubscribeReposClient()

        def on_message_handler(message: MessageFrame):
            commit = parse_subscribe_repos_message(message)
            if not isinstance(commit, models.ComAtprotoSyncSubscribeRepos.Commit):
                return

            session = SessionLocal()
            try:
                self.process_commit(commit, session)
                session.commit()
            except Exception as e:
                logger.error(f"Error processing commit: {e}")
                session.rollback()
            finally:
                session.close()

        client.start(on_message_handler)

if __name__ == "__main__":
    ingester = BlueskyIngester()
    ingester.login()
    ingester.update_following_list()
    ingester.start_firehose()
