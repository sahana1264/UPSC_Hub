# UPSC_Hub
A full-stack Progressive Web Application (PWA) built for UPSC aspirants, utilizing Machine Learning to automatically aggregate and classify news articles into specific General Studies (GS) papers. This application delivers an offline-ready, personalized, and efficient study experience.

## 🌟 Core Features

### 📚 **Smart News Classification**
- Automatically categorizes news into GS Papers (GS1-GS4) using ML models
- Uses Transformer models for accurate classification
- Fallback keyword-based classification system

### 📰 **Multi-Source News Aggregation**
- Fetches from The Hindu, Indian Express, Times of India
- Real-time RSS feed parsing
- Full article content extraction
- Automatic summarization using TextRank

### 📱 **Progressive Web App**
- Works offline with cached data
- Installable on mobile devices
- Service worker for background sync
- Responsive design for all screen sizes

### 🔖 **Personal Study Tools**
- Bookmark important articles
- Create and manage study notes
- Export bookmarks and notes as PDF
- Offline access to saved content

  ## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)
- 4GB+ RAM (for ML models)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/sahana1264/upsc_hub.git
   cd upsc_hub
   ```

2. **Install dependencies**
   ```bash
  pip install -r requirements.txt
   ```


4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the application**
   Open your browser and go to `http://localhost:5000`

   ## 🔧 Configuration

### RSS Feeds
The application fetches news from these sources (configurable in `src/app.py`):
- The Hindu: National news RSS
- Indian Express: India section RSS
- Times of India: Top stories RSS

### GS Paper Classification
- **GS1**: History, Culture, Geography, Society
- **GS2**: Polity, Governance, International Relations
- **GS3**: Economy, Technology, Environment, Security
- **GS4**: Ethics, Integrity, Aptitude

## 💡 Usage

### First Time Setup
1. **Register**: Create an account with username, email, and password
2. **Login**: Access your personalized dashboard
3. **Browse News**: View latest news or filter by GS Paper
4. **Bookmark**: Save important articles for later study
5. **Take Notes**: Add personal study notes to articles
6. **Export**: Download your data as PDF files

### Key Features
- **Latest News**: View all recent articles with ML classification
- **GS Paper Filter**: Browse news by specific GS Papers
- **Offline Mode**: Access bookmarks and notes without internet
- **Dark Mode**: Toggle between light and dark themes
- **Mobile Support**: Fully responsive design

## 🛠️ Technical Details

### Backend Technologies
- **Flask**: Web framework
- **SQLite**: Database with optimized indexes
- **Transformers**: Hugging Face models for classification
- **Sentence Transformers**: Text embeddings
- **FAISS**: Vector similarity search
- **BeautifulSoup**: Web scraping
- **Feedparser**: RSS feed parsing
- **ReportLab**: PDF generation
- **APScheduler**: Background task scheduling

### Frontend Technologies
- **Vanilla JavaScript**: No framework dependencies
- **IndexedDB**: Client-side storage
- **Service Worker**: PWA functionality
- **CSS Grid/Flexbox**: Responsive layouts

### Machine Learning Pipeline
1. **News Fetching**: RSS feeds → Full article extraction
2. **Text Processing**: Cleaning and tokenization
3. **Classification**: Transformer models → GS Paper assignment
4. **Summarization**: TextRank algorithm
5. **Storage**: SQLite with FAISS indexing

## 🔍 API Endpoints

### Authentication
- `POST /login` - User login
- `POST /signup` - User registration
- `GET /logout` - User logout

### News & Content
- `GET /` - Home dashboard
- `GET /latest_news` - Latest news with pagination
- `GET /search_results` - GS Paper filtered results

### User Data
- `POST /bookmark/<article_id>` - Toggle bookmark
- `GET /bookmarks` - View user bookmarks
- `GET /notes/<article_id>` - Manage article notes
- `GET /my_notes` - View all user notes

### Export
- `GET /export/bookmarks/pdf` - Export bookmarks as PDF
- `GET /export/notes/pdf` - Export notes as PDF

