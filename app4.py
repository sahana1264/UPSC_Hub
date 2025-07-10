

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import concurrent.futures
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sentence_transformers import SentenceTransformer
import feedparser
import sqlite3
import os
import torch
import json
from datetime import datetime
import faiss
import numpy as np
import nltk
import requests
from bs4 import BeautifulSoup
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer
import ssl
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import hashlib  # For better article_id generation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress noisy logs
nltk_logger = logging.getLogger('nltk')
nltk_logger.setLevel(logging.ERROR)

# Handle SSL certificate issues
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Initialize NLTK data
def initialize_nltk():
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)

initialize_nltk()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuration
GS_PAPERS = ["GS1", "GS2", "GS3", "GS4"]
RSS_FEEDS = {
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"
}

# FAISS Setup
d = 384
index = faiss.IndexFlatL2(d)
news_db = {}

# Database setup
def get_db():
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = sqlite3.connect('upsc_news.db')
        g.sqlite_db.row_factory = sqlite3.Row
        g.sqlite_db.execute("PRAGMA foreign_keys = ON")
    return g.sqlite_db

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()

def init_db():
    with app.app_context():
        db = get_db()
        version = db.execute("PRAGMA user_version").fetchone()[0]
        logger.info(f"Current database version: {version}")
        
        if version == 0:
            db.execute('''CREATE TABLE IF NOT EXISTS users
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          username TEXT UNIQUE NOT NULL,
                          email TEXT UNIQUE NOT NULL,
                          password TEXT NOT NULL)''')
            
            db.execute('''CREATE TABLE IF NOT EXISTS articles
                         (id TEXT PRIMARY KEY,
                          title TEXT NOT NULL,
                          content TEXT NOT NULL,
                          summary TEXT NOT NULL,
                          date TEXT NOT NULL,
                          gs_paper TEXT NOT NULL,
                          link TEXT NOT NULL,
                          newspaper TEXT NOT NULL,
                          last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            db.execute('''CREATE TABLE IF NOT EXISTS bookmarks
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_id INTEGER NOT NULL,
                          article_id TEXT NOT NULL,
                          title TEXT NOT NULL,
                          gs_paper TEXT NOT NULL,
                          summary TEXT NOT NULL,
                          link TEXT NOT NULL,
                          date_added TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                          FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE,
                          UNIQUE(user_id, article_id))''')
            
            db.execute('''CREATE TABLE IF NOT EXISTS notes
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_id INTEGER NOT NULL,
                          article_id TEXT NOT NULL,
                          title TEXT NOT NULL,
                          gs_paper TEXT NOT NULL,
                          content TEXT NOT NULL,
                          last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                          FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE)''')
            
            # Create indexes
            db.execute('CREATE INDEX IF NOT EXISTS idx_articles_gs_paper ON articles(gs_paper)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)')
            
            # Set schema version
            db.execute("PRAGMA user_version = 2")
            db.commit()
            logger.info("Database initialized with version 2 schema")

# Initialize models
def init_models():
    global tokenizer, model, embedder
    try:
        tokenizer = AutoTokenizer.from_pretrained("gs_classifier")
        model = AutoModelForSequenceClassification.from_pretrained("gs_classifier")
        embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        logger.info("Models loaded successfully")
    except Exception as e:
        logger.error(f"Error loading models: {e}")
        tokenizer, model, embedder = None, None, None

def fetch_full_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'iframe']):
            element.decompose()
            
        paragraphs = [p.get_text().strip() for p in soup.find_all('p')]
        return ' '.join(p for p in paragraphs if len(p.split()) > 10)
    except Exception as e:
        logger.error(f"Error fetching full text from {url}: {e}")
        return None

def fetch_rss_articles(feed_url, newspaper):
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        seen_titles = set()  # Track titles to avoid duplicates within the same feed

        for entry in feed.entries[:20]:  # Limit to 20 articles per feed
            title = entry.title.strip()
            if title in seen_titles:
                logger.debug(f"Skipping duplicate title in feed: {title}")
                continue
            seen_titles.add(title)

            full_text = fetch_full_text(entry.link)
            if not full_text or len(full_text.split()) < 50:
                continue
                
            pub_date = entry.get('published', datetime.now().isoformat())
            
            # Generate a unique ID using title, newspaper, and date
            article_id = hashlib.md5((title + newspaper + pub_date).encode()).hexdigest()
            
            articles.append({
                "id": article_id,
                "title": title,
                "link": entry.link,
                "text": full_text,
                "date": pub_date,
                "newspaper": newspaper
            })

        return articles
    except Exception as e:
        logger.error(f"Error parsing RSS feed {feed_url}: {e}")
        return []



def summarize_article(text):
    if not text or len(text.split()) < 50:
        return text

    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = TextRankSummarizer()
        summary = summarizer(parser.document, 4)
        return " ".join(str(sentence) for sentence in summary)
    except Exception as e:
        print(f"Summarization error: {e}")
        return text

def classify_article(text):
    if model is None or tokenizer is None:
        keywords = {
            "GS1": ["history", "culture", "heritage", "art", "geography", "society"],
            "GS2": ["governance", "constitution", "polity", "international", "relations", "policy"],
            "GS3": ["economy", "technology", "environment", "security", "disaster", "development"],
            "GS4": ["ethics", "integrity", "aptitude", "moral", "values", "attitude"]
        }
        text_lower = text.lower()
        scores = {paper: sum(1 for keyword in kw_list if keyword in text_lower) for paper, kw_list in keywords.items()}
        return max(scores, key=scores.get)
    
    try:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = model(**inputs).logits
        return GS_PAPERS[torch.argmax(logits, dim=1).item()]
    except Exception as e:
        logger.error(f"Classification error: {e}")
        return "GS2"

def fetch_and_store_articles():
    results = []
    news_articles = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(fetch_rss_articles, feed_url, newspaper): newspaper for newspaper, feed_url in RSS_FEEDS.items()}
        for future in concurrent.futures.as_completed(futures):
            newspaper = futures[future]
            articles = future.result()
            news_articles.extend(articles)

    db = get_db()
    
    for article in news_articles:
        # Check if article already exists (using the new ID scheme)
        existing = db.execute('''SELECT id FROM articles WHERE id = ?''', (article["id"],)).fetchone()
        if existing:
            logger.debug(f"Skipping duplicate article: {article['title']}")
            continue
            
        gs_paper = classify_article(article["text"])
        summary = summarize_article(article["text"])

        article_data = {
            "id": article["id"],
            "title": article["title"],
            "content": article["text"],
            "summary": summary,
            "date": article["date"],
            "gs_paper": gs_paper,
            "link": article["link"],
            "newspaper": article["newspaper"]
        }

        results.append(article_data)

    # Insert all new articles in a single transaction
    if results:
        try:
            db.executemany('''
                INSERT INTO articles 
                (id, title, content, summary, date, gs_paper, link, newspaper)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', [
                (article['id'], article['title'], article['content'], 
                 article['summary'], article['date'], article['gs_paper'], 
                 article['link'], article['newspaper'])
                for article in results
            ])
            db.commit()
            logger.info(f"Inserted {len(results)} new articles")
        except sqlite3.Error as e:
            logger.error(f"Error inserting articles: {e}")
            db.rollback()

    add_to_faiss(results)
    return len(results)

def add_to_faiss(news_articles):
    global index, news_db

    if index.is_trained is False:
        index = faiss.IndexFlatIP(d)

    for i, article in enumerate(news_articles):
        if article["content"]:
            text_embedding = embedder.encode(article["content"], normalize_embeddings=True).reshape(1, -1)
            index.add(text_embedding)
            news_db[i] = article

def get_sample_news(gs_paper=None, page=1, per_page=10):
    db = get_db()
    
    query = '''SELECT DISTINCT id, title, content, summary, date, gs_paper, link, newspaper 
               FROM articles 
               WHERE datetime(last_updated) > datetime('now', '-3 days')'''
    params = []
    
    if gs_paper:
        query += ' AND gs_paper = ?'
        params.append(gs_paper)
    
    query += ' ORDER BY date DESC'
    
    count_query = query.replace('SELECT DISTINCT id, title, content, summary, date, gs_paper, link, newspaper', 'SELECT COUNT(DISTINCT id)')
    if gs_paper:
        total_articles = db.execute(count_query, params).fetchone()[0]
    else:
        total_articles = db.execute(count_query).fetchone()[0]
    
    query += ' LIMIT ? OFFSET ?'
    offset = (page - 1) * per_page
    params.extend([per_page, offset])
    
    if gs_paper:
        articles = db.execute(query, params).fetchall()
    else:
        articles = db.execute(query, (per_page, offset)).fetchall()
    
    total_pages = (total_articles + per_page - 1) // per_page
    
    return {
        'articles': [dict(article) for article in articles],
        'total_pages': total_pages,
        'current_page': page,
        'total_articles': total_articles
    }

# ... [Rest of the routes remain unchanged] ...

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    trending_topics = ["IndianHistory", "Constitution", "Economy", "Ethics", "Governance", "ForeignPolicy", "Environment"]
    username = session.get('username', 'Guest')
    
    return render_template("index.html", trending_topics=trending_topics, username=username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template("login.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('signup'))
        
        hashed_password = generate_password_hash(password)
        
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                      (username, email, hashed_password))
            db.commit()
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists', 'danger')
        
    return render_template("signup.html")

@app.route('/logout')
def user_logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/latest_news')
def show_latest_news():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    news_data = get_sample_news(page=page, per_page=per_page)
    results = news_data['articles']
    total_pages = news_data['total_pages']
    
    db = get_db()
    bookmarks = db.execute('SELECT article_id FROM bookmarks WHERE user_id = ?', 
                         (session['user_id'],)).fetchall()
    
    bookmarked_ids = [bookmark['article_id'] for bookmark in bookmarks]
    
    return render_template('latest_news.html', 
                          results=results, 
                          current_page=page, 
                          total_pages=total_pages,
                          bookmarked_ids=bookmarked_ids)

@app.route('/search_results')
def search_results():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    gs_paper = request.args.get('gs_paper')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    if not gs_paper:
        return render_template('search_results.html', error="No GS paper selected", results=None)
    
    news_data = get_sample_news(gs_paper=gs_paper, page=page, per_page=per_page)
    results = news_data['articles']
    total_pages = news_data['total_pages']
    
    db = get_db()
    bookmarks = db.execute('SELECT article_id FROM bookmarks WHERE user_id = ?', 
                         (session['user_id'],)).fetchall()
    
    bookmarked_ids = [bookmark['article_id'] for bookmark in bookmarks]
    
    return render_template('search_results.html', 
                          results=results, 
                          gs_paper=gs_paper, 
                          current_page=page, 
                          total_pages=total_pages,
                          bookmarked_ids=bookmarked_ids)


@app.route('/bookmark/<article_id>', methods=['POST'])
def toggle_bookmark(article_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    user_id = session['user_id']
    
    db = get_db()
    bookmark = db.execute('SELECT * FROM bookmarks WHERE user_id = ? AND article_id = ?', 
                        (user_id, article_id)).fetchone()
    
    if bookmark:
        db.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark['id'],))
        db.commit()
        return jsonify({'success': True, 'bookmarked': False})
    else:
        article = db.execute('SELECT * FROM articles WHERE id = ?', (article_id,)).fetchone()
        
        if not article:
            return jsonify({'success': False, 'error': 'Article not found'})
        
        db.execute(
            'INSERT INTO bookmarks (user_id, article_id, title, gs_paper, summary, link) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, article_id, article['title'], article['gs_paper'], article['summary'], article['link'])
        )
        db.commit()
        return jsonify({'success': True, 'bookmarked': True})
    
@app.route('/bookmarks')
def show_bookmarks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    bookmarks = db.execute('''
        SELECT b.id, b.article_id, b.title, b.gs_paper, b.summary, b.link, b.date_added 
        FROM bookmarks b
        WHERE b.user_id = ? 
        ORDER BY b.date_added DESC
    ''', (session['user_id'],)).fetchall()
    
    return render_template('bookmarks.html', bookmarks=bookmarks)

@app.route('/notes/<article_id>', methods=['GET', 'POST'])
def manage_notes(article_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    all_news = get_sample_news()
    article = next((a for a in all_news['articles'] if a['id'] == article_id), None)
    
    if not article:
        flash('Article not found', 'danger')
        return redirect(url_for('home'))
    
    db = get_db()
    
    if request.method == 'POST':
        content = request.form['content']
        
        note = db.execute('SELECT * FROM notes WHERE user_id = ? AND article_id = ?', 
                        (user_id, article_id)).fetchone()
        
        if note:
            db.execute('UPDATE notes SET content = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?', 
                     (content, note['id']))
        else:
            db.execute(
                'INSERT INTO notes (user_id, article_id, title, gs_paper, content) VALUES (?, ?, ?, ?, ?)',
                (user_id, article_id, article['title'], article['gs_paper'], content)
            )
        
        db.commit()
        flash('Notes saved successfully!', 'success')
    
    note = db.execute('SELECT * FROM notes WHERE user_id = ? AND article_id = ?', 
                    (user_id, article_id)).fetchone()
    
    return render_template('notes.html', article=article, note=note)

@app.route('/my_notes')
def show_notes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    notes = db.execute('SELECT * FROM notes WHERE user_id = ? ORDER BY last_updated DESC', 
                     (session['user_id'],)).fetchall()
    
    return render_template('my_notes.html', notes=notes)

@app.route('/notes/delete/<note_id>', methods=['POST'])
def delete_note(note_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    db = get_db()
    db.execute('DELETE FROM notes WHERE id = ? AND user_id = ?', 
             (note_id, session['user_id']))
    db.commit()
    
    return jsonify({'success': True})

@app.route('/api/bookmarks')
def api_bookmarks():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    db = get_db()
    bookmarks = db.execute('''
        SELECT b.id, b.article_id, b.title, b.gs_paper, b.summary, b.link, b.date_added 
        FROM bookmarks b
        WHERE b.user_id = ?
    ''', (session['user_id'],)).fetchall()
    
    bookmarks_list = []
    for bookmark in bookmarks:
        bookmarks_list.append({
            'id': bookmark['id'],
            'article_id': bookmark['article_id'],
            'title': bookmark['title'],
            'gs_paper': bookmark['gs_paper'],
            'summary': bookmark['summary'],
            'link': bookmark['link'],
            'date_added': bookmark['date_added']
        })
    
    return jsonify(bookmarks_list)

@app.route('/api/notes')
def api_notes():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    db = get_db()
    notes = db.execute('SELECT * FROM notes WHERE user_id = ?', 
                     (session['user_id'],)).fetchall()
    
    notes_list = []
    for note in notes:
        notes_list.append({
            'id': note['id'],
            'article_id': note['article_id'],
            'title': note['title'],
            'gs_paper': note['gs_paper'],
            'content': note['content'],
            'last_updated': note['last_updated']
        })
    
    return jsonify(notes_list)

@app.route('/export/bookmarks/pdf')
def export_bookmarks_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    bookmarks = db.execute('''
        SELECT b.id, b.article_id, b.title, b.gs_paper, b.summary, b.link, b.date_added 
        FROM bookmarks b
        WHERE b.user_id = ? 
        ORDER BY b.date_added DESC
    ''', (session['user_id'],)).fetchall()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph("My UPSC Bookmarked Articles", styles['Title']))
    story.append(Spacer(1, 12))
    
    for bookmark in bookmarks:
        story.append(Paragraph(f"<b>{bookmark['title']}</b>", styles['Heading2']))
        story.append(Paragraph(f"<b>GS Paper:</b> {bookmark['gs_paper']}", styles['Normal']))
        story.append(Paragraph(f"<b>Date Bookmarked:</b> {bookmark['date_added']}", styles['Normal']))
        story.append(Paragraph(bookmark['summary'], styles['Normal']))
        story.append(Paragraph(f"<b>Link:</b> {bookmark['link']}", styles['Normal']))
        story.append(Spacer(1, 12))
    
    doc.build(story)
    
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=upsc_bookmarks.pdf'
    return response

@app.route('/export/notes/pdf')
def export_notes_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    notes = db.execute('SELECT * FROM notes WHERE user_id = ? ORDER BY last_updated DESC', 
                     (session['user_id'],)).fetchall()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph("My UPSC Notes", styles['Title']))
    story.append(Spacer(1, 12))
    
    for note in notes:
        story.append(Paragraph(f"<b>{note['title']}</b>", styles['Heading2']))
        story.append(Paragraph(f"<b>GS Paper:</b> {note['gs_paper']}", styles['Normal']))
        story.append(Paragraph(f"<b>Last Updated:</b> {note['last_updated']}", styles['Normal']))
        story.append(Paragraph(note['content'], styles['Normal']))
        story.append(Spacer(1, 12))
    
    doc.build(story)
    
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=upsc_notes.pdf'
    return response

@app.route('/export/single-note/pdf', methods=['POST'])
def export_single_note_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    title = request.form['title']
    content = request.form['content']
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph(title, styles['Title']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(content, styles['Normal']))
    
    doc.build(story)
    
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={title.replace(" ", "_")}_notes.pdf'
    return response

@app.route('/offline')
def offline():
    return render_template('offline.html')

def scheduled_fetch():
    with app.app_context():
        try:
            count = fetch_and_store_articles()
            logger.info(f"Scheduled fetch completed. Added/updated {count} articles")
        except Exception as e:
            logger.error(f"Error in scheduled fetch: {e}")


def init_app():
    init_db()
    try:
        init_models()
        count = fetch_and_store_articles()
        logger.info(f"Initial fetch completed. Added {count} articles")
    except Exception as e:
        logger.error(f"Error initializing: {e}")

if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_fetch, 'interval', hours=1)
    scheduler.start()
    
    with app.app_context():
        init_app()
    
    try:
        app.run(debug=True)
    except KeyboardInterrupt:
        scheduler.shutdown()