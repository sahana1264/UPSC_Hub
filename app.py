from flask import Flask, render_template, request, jsonify
import faiss
import numpy as np
import torch
import concurrent.futures  
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
from sentence_transformers import SentenceTransformer
import feedparser
import requests
from bs4 import BeautifulSoup
import logging  

# Initialize Flask App
app = Flask(__name__)

#  Define UPSC GS paper categories
GS_PAPERS = ["GS1", "GS2", "GS3", "GS4"]

# Load Transformer Models
tokenizer = AutoTokenizer.from_pretrained("gs_classifier")
model = AutoModelForSequenceClassification.from_pretrained("gs_classifier")
embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
summarizer = pipeline("summarization", model="t5-small")

# FAISS Setup
d = 384  
index = faiss.IndexFlatL2(d)
news_db = {}

# RSS Feeds
RSS_FEEDS = {
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"
}

logging.basicConfig(level=logging.INFO)


def fetch_rss_articles(feed_url):
    """Fetch top articles from an RSS feed (Optimized for Speed)."""
    feed = feedparser.parse(feed_url)
    articles = []
    
    for entry in feed.entries[:20]:  
        full_text = entry.summary  
        pub_date = entry.get("published", "Unknown Date")  

        articles.append({
            "title": entry.title,
            "link": entry.link,
            "summary": full_text[:200] + "...",
            "text": full_text,
            "date": pub_date  
        })

    return articles

def classify_article(text):
    """Classify article into GS1, GS2, GS3, or GS4."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
    with torch.no_grad():
        outputs = model(**inputs)
    logits = outputs.logits
    predicted_class = torch.argmax(logits, dim=1).item()
    return GS_PAPERS[predicted_class]  

def summarize_article(text):
    """Summarize article using T5-small model."""
    if len(text.split()) < 50:
        return text  
    summary = summarizer(text, max_length=50, min_length=30, do_sample=False)
    return summary[0]["summary_text"]

def add_to_faiss(news_articles):
    """Indexes articles into FAISS, ensuring correct embeddings and metadata storage."""
    global index, news_db

    if index.is_trained is False:
        print("FAISS Index is not trained. Initializing...")
        index = faiss.IndexFlatIP(384)  

    for i, article in enumerate(news_articles):
        if article["text"]:  
            text_embedding = embedder.encode(article["text"], normalize_embeddings=True).reshape(1, -1)
            index.add(text_embedding)

            news_db[i] = {
                "title": article["title"],
                "link": article["link"],
                "text": article["text"],
                "summary": article["summary"],
                "gs_paper": article["gs_paper"],
                "date": article.get("date", "Unknown")  
            }

def fetch_and_store_articles():
    """Fetches, processes, and stores news articles at startup."""
    results = []
    news_articles = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        fetched_articles = list(executor.map(fetch_rss_articles, RSS_FEEDS.values()))

    for newspaper, articles in zip(RSS_FEEDS.keys(), fetched_articles):
        for article in articles:
            gs_paper = classify_article(article["text"])  
            summary = summarize_article(article["text"])  

            article_data = {
                "newspaper": newspaper,
                "title": article["title"],
                "link": article["link"],
                "gs_paper": gs_paper,  
                "summary": summary,
                "text": article["text"],
                "date":article["date"]
            }

            results.append(article_data)
            news_articles.append(article_data)  

    add_to_faiss(news_articles)
    print(f" {len(news_articles)} articles stored at startup!")

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/latest_news', methods=['GET'])
def latest_news():
    results = list(news_db.values())  
    return render_template("latest_news.html", results=results)

@app.route('/search_result', methods=['GET'])
def search_news():
    gs_paper = request.args.get("gs_paper")  

    print(f"🔎 DEBUG: Total Articles in `news_db`: {len(news_db)}")
    
    for i, article in news_db.items():
        print(f"📰 {article['title']} | GS Paper: {article.get('gs_paper', 'Unknown')}")

    if not gs_paper or gs_paper not in GS_PAPERS:
        return render_template("search_results.html", results=[], gs_paper=gs_paper, error="Invalid GS Paper selection.")

    results = [article for article in news_db.values() if article.get("gs_paper", "").strip() == gs_paper.strip()]

    if not results:
        return render_template("search_results.html", results=[], gs_paper=gs_paper, error="No articles found for this GS Paper.")

    return render_template("search_results.html", results=results, gs_paper=gs_paper)

# ✅ Run Flask App
if __name__ == '__main__':
    fetch_and_store_articles()  # ✅ Fetch news at startup
    app.run(debug=True)
