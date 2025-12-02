import streamlit as st
import pandas as pd
import plotly.express as px
import os
import time
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

# Page Config
st.set_page_config(
    page_title="BlueSky Sentiment Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Database Connection
@st.cache_resource
def get_engine():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        st.error("DATABASE_URL not found in .env")
        st.stop()
    return create_engine(db_url)

engine = get_engine()

# Auto-Refresh Logic (2 seconds)
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

refresh_rate = 2 # seconds
time_now = time.time()
if time_now - st.session_state.last_refresh > refresh_rate:
    st.session_state.last_refresh = time_now
    st.rerun()

# --- DATA FETCHING ---
def get_active_topics():
    """Fetch topics updated in the last 24 hours with their latest scores."""
    query = text("""
        SELECT 
            t.id, 
            t.label, 
            t.keywords, 
            t.last_updated,
            ts.timestamp as score_time,
            COALESCE(ts.danger_score, 0) as danger_score,
            COALESCE(ts.hype_score, 0) as hype_score,
            COALESCE(ts.news_score, 0) as news_score,
            COALESCE(ts.post_count, 0) as volume,
            COALESCE(ts.summary, '') as summary,
            COALESCE(ts.tickers, '') as tickers
        FROM topics t
        JOIN (
            SELECT DISTINCT ON (topic_id) *
            FROM topic_scores
            ORDER BY topic_id, timestamp DESC
        ) ts ON t.id = ts.topic_id
        WHERE t.label != 'Noise' 
        AND ts.timestamp > NOW() - INTERVAL '30 minutes'
        ORDER BY ts.timestamp DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)

def get_topic_history():
    """Fetch historical volume for river graph."""
    query = text("""
        SELECT 
            t.label,
            ts.timestamp,
            ts.post_count as volume
        FROM topic_scores ts
        JOIN topics t ON ts.topic_id = t.id
        WHERE t.label != 'Noise'
        AND ts.timestamp > NOW() - INTERVAL '12 hours'
        ORDER BY ts.timestamp ASC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)

# --- DASHBOARD LAYOUT ---
st.title("BlueSky Sentiment Stream")

# Fetch Data
df_topics = get_active_topics()

if df_topics.empty:
    st.warning("No active topics scored in the last 30 minutes.")
else:
    # 1. SCATTER PLOT (Danger vs Hype)
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("News vs. Danger (Color=Hype)")
        
        # Clean up dataframe for tooltip
        df_topics['Last Updated'] = pd.to_datetime(df_topics['last_updated']).dt.strftime('%H:%M:%S')
        df_topics['Last Scored'] = pd.to_datetime(df_topics['score_time']).dt.strftime('%H:%M:%S')
        # Use Summary instead of Keywords if available, else truncate keywords
        df_topics['Description'] = df_topics.apply(lambda x: x['summary'] if x['summary'] else x['keywords'][:50]+"...", axis=1)
        
        fig_scatter = px.scatter(
            df_topics,
            x="news_score",
            y="danger_score",
            size="volume",
            color="hype_score",
            hover_name="label",
            hover_data={
                "news_score": ":.1f",
                "danger_score": ":.1f",
                "hype_score": ":.1f",
                "volume": True,
                "Description": True,
                "Last Scored": True,
                "label": False,
                "keywords": False,
                "last_updated": False,
                "score_time": False,
                "summary": False,
                "tickers": False
            },
            color_continuous_scale="Jet", # High contrast for Hype
            range_x=[0, 10],
            range_y=[0, 10],
            size_max=80, # Larger bubbles
            height=1400   # Taller chart (2x)
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col2:
        st.subheader("Top Active Topics")
        # Ensure sorted by volume descending
        top_topics = df_topics.sort_values("volume", ascending=False).head(20) # Show more topics
        for _, row in top_topics.iterrows():
            st.markdown(f"**{row['label']}**")
            if row['tickers']:
                st.caption(f"Tickers: {row['tickers']}")
            
            desc = row['summary'] if row['summary'] else row['keywords'][:100]+"..."
import streamlit as st
import pandas as pd
import plotly.express as px
import os
import time
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), 'bsky-sentiment/ingestion/.env'))

# Page Config
st.set_page_config(
    page_title="BlueSky Sentiment Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Database Connection
@st.cache_resource
def get_engine():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        st.error("DATABASE_URL not found in .env")
        st.stop()
    return create_engine(db_url)

engine = get_engine()

# Auto-Refresh Logic (2 seconds)
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

refresh_rate = 2 # seconds
time_now = time.time()
if time_now - st.session_state.last_refresh > refresh_rate:
    st.session_state.last_refresh = time_now
    st.rerun()

# --- DATA FETCHING ---
def get_active_topics():
    """Fetch topics updated in the last 24 hours with their latest scores."""
    query = text("""
        SELECT 
            t.id, 
            t.label, 
            t.keywords, 
            t.last_updated,
            ts.timestamp as score_time,
            COALESCE(ts.danger_score, 0) as danger_score,
            COALESCE(ts.hype_score, 0) as hype_score,
            COALESCE(ts.news_score, 0) as news_score,
            COALESCE(ts.post_count, 0) as volume,
            COALESCE(ts.summary, '') as summary,
            COALESCE(ts.tickers, '') as tickers
        FROM topics t
        JOIN (
            SELECT DISTINCT ON (topic_id) *
            FROM topic_scores
            ORDER BY topic_id, timestamp DESC
        ) ts ON t.id = ts.topic_id
        WHERE t.label != 'Noise' 
        AND ts.timestamp > NOW() - INTERVAL '30 minutes'
        ORDER BY ts.timestamp DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)

def get_topic_history():
    """Fetch historical volume for river graph."""
    query = text("""
        SELECT 
            t.label,
            ts.timestamp,
            ts.post_count as volume
        FROM topic_scores ts
        JOIN topics t ON ts.topic_id = t.id
        WHERE t.label != 'Noise'
        AND ts.timestamp > NOW() - INTERVAL '12 hours'
        ORDER BY ts.timestamp ASC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)

# --- DASHBOARD LAYOUT ---
st.title("BlueSky Sentiment Stream")

# Fetch Data
df_topics = get_active_topics()

if df_topics.empty:
    st.warning("No active topics scored in the last 30 minutes.")
else:
    # 1. SCATTER PLOT (Danger vs Hype)
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("News vs. Danger (Color=Hype)")
        
        # Clean up dataframe for tooltip
        df_topics['Last Updated'] = pd.to_datetime(df_topics['last_updated']).dt.strftime('%H:%M:%S')
        df_topics['Last Scored'] = pd.to_datetime(df_topics['score_time']).dt.strftime('%H:%M:%S')
        # Use Summary instead of Keywords if available, else truncate keywords
        df_topics['Description'] = df_topics.apply(lambda x: x['summary'] if x['summary'] else x['keywords'][:50]+"...", axis=1)
        
        fig_scatter = px.scatter(
            df_topics,
            x="news_score",
            y="danger_score",
            size="volume",
            color="hype_score",
            hover_name="label",
            hover_data={
                "news_score": ":.1f",
                "danger_score": ":.1f",
                "hype_score": ":.1f",
                "volume": True,
                "Description": True,
                "Last Scored": True,
                "label": False,
                "keywords": False,
                "last_updated": False,
                "score_time": False,
                "summary": False,
                "tickers": False
            },
            color_continuous_scale="Jet", # High contrast for Hype
            range_x=[0, 10],
            range_y=[0, 10],
            size_max=80, # Larger bubbles
            height=1400   # Taller chart (2x)
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col2:
        st.subheader("Top Active Topics")
        # Ensure sorted by volume descending
        top_topics = df_topics.sort_values("volume", ascending=False).head(20) # Show more topics
        for _, row in top_topics.iterrows():
            st.markdown(f"**{row['label']}**")
            if row['tickers']:
                st.caption(f"Tickers: {row['tickers']}")
            
            desc = row['summary'] if row['summary'] else row['keywords'][:100]+"..."
            st.caption(f"{desc}")
            
            st.caption(f"Vol: {row['volume']} | Danger: {row['danger_score']:.1f} | Hype: {row['hype_score']:.1f}")
            st.divider()

    # 2. RIVER GRAPH (Volume over Time)
    st.subheader("Topic Volume History (12h)")
    df_history = get_topic_history()
    
    if not df_history.empty:
        fig_river = px.area(
            df_history,
            x="timestamp",
            y="volume",
            color="label",
            line_group="label",
            hover_name="label",
            height=400
        )
        st.plotly_chart(fig_river, use_container_width=True)
    else:
        st.info("No historical volume data available yet.")

# Auto-refresh loop (using st.empty() trick is another way, but rerun is simpler for full page updates)
time.sleep(refresh_rate)
st.rerun()
