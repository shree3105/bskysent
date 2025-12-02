import os
from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, func
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
