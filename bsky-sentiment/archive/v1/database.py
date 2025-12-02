import os

from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, func, Integer, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class RawPost(Base):
    __tablename__ = 'raw_posts'

    uri = Column(Text, primary_key=True)
    cid = Column(Text)
    author_did = Column(Text, index=True)
    content = Column(Text)
    created_at = Column(DateTime(timezone=True))
    indexed_at = Column(DateTime(timezone=True), server_default=func.now())
    is_processed = Column(Boolean, default=False)
    quote_uri = Column(Text, nullable=True)
    quote_content = Column(Text, nullable=True)
    repost_uri = Column(Text, nullable=True)

class Topic(Base):
    __tablename__ = 'topics'
    
    id = Column(String, primary_key=True) # e.g., "topic_123"
    label = Column(Text) # e.g., "Inflation"
    keywords = Column(Text) # Comma-separated keywords
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), onupdate=func.now())

class TopicScore(Base):
    __tablename__ = 'topic_scores'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True)) # The bucket time (e.g., 10:00, 10:15)
    danger_score = Column(Float)
    hype_score = Column(Float) # 0-10, Excitement/Greed/FOMO
    news_score = Column(Float) # 0-10, how much is this "news" vs "opinion"
    tickers = Column(Text) # Comma-separated list of tickers e.g. "NVDA, BTC"
    post_count = Column(Integer)
    summary = Column(Text)

class ProcessedPost(Base):
    __tablename__ = 'processed_posts'
    
    uri = Column(Text, primary_key=True)
    topic_id = Column(String, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

class SystemState(Base):
    __tablename__ = 'system_state'
    key = Column(String, primary_key=True) # e.g., "last_scored_time"
    value = Column(Text)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class MonitoredAccount(Base):
    __tablename__ = 'monitored_accounts'

    did = Column(Text, primary_key=True)
    handle = Column(Text)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

def get_db_engine():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")
    return create_engine(database_url)

def init_db(engine):
    Base.metadata.create_all(engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False)
