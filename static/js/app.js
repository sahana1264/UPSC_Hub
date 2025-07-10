

// app.js - Updated to handle summaries in offline mode
document.addEventListener('DOMContentLoaded', function() {
  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/service-worker.js')
      .then(registration => {
        console.log('Service Worker registered with scope:', registration.scope);
        // Cache articles with summaries when online
        if (navigator.onLine) {
          cacheArticlesWithSummaries();
        }
      })
      .catch(error => {
        console.error('Service Worker registration failed:', error);
      });
  }
  
  // Setup offline detection
  setupOfflineDetection();
  
  // Initialize dark mode from localStorage
  initDarkMode();
  
  // Sync data when online
  window.addEventListener('online', syncData);
});

// Cache articles with their summaries
function cacheArticlesWithSummaries() {
  fetch('/api/articles')
    .then(response => response.json())
    .then(articles => {
      if (window.idbPromise) {
        // Store articles in IndexedDB for offline access
        articles.forEach(article => {
          idbPromise.add('articles', {
            id: article.id,
            title: article.title,
            content: article.content,
            summary: article.summary,
            gs_paper: article.gs_paper,
            link: article.link,
            date: article.date
          });
        });
      }
    })
    .catch(error => console.error('Error caching articles:', error));
}

// Setup offline detection and indicator
function setupOfflineDetection() {
  const offlineIndicator = document.createElement('div');
  offlineIndicator.className = 'offline-indicator';
  offlineIndicator.textContent = '🔌 You are offline';
  document.body.appendChild(offlineIndicator);
  
  function updateOnlineStatus() {
    if (navigator.onLine) {
      offlineIndicator.style.display = 'none';
      syncData();
      // Refresh cached articles when coming back online
      cacheArticlesWithSummaries();
    } else {
      offlineIndicator.style.display = 'block';
    }
  }
  
  window.addEventListener('online', updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);
  
  // Initial check
  updateOnlineStatus();
}

// Initialize dark mode from localStorage
function initDarkMode() {
  const toggleButton = document.getElementById('darkModeToggle');
  if (!toggleButton) return;
  
  if (localStorage.getItem('darkMode') === 'true') {
    document.body.classList.add('dark-mode');
    toggleButton.textContent = '☀️ Light Mode';
  }
  
  toggleButton.addEventListener('click', function() {
    document.body.classList.toggle('dark-mode');
    toggleButton.textContent = document.body.classList.contains('dark-mode') ? '☀️ Light Mode' : '🌙 Dark Mode';
    localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
  });
}

// Sync data when online
function syncData() {
  if (!navigator.onLine || !window.idbPromise) return;
  
  // Get pending operations from sync queue
  idbPromise.getSyncQueue()
    .then(operations => {
      if (operations.length === 0) return;
      
      // Process each operation
      operations.forEach(operation => {
        if (operation.type === 'bookmark') {
          // Sync bookmark with summary
          fetch(`/bookmark/${operation.articleId}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              summary: operation.summary // Include summary in the request
            })
          })
          .then(response => response.json())
          .then(data => {
            if (data.success) {
              // Remove from sync queue
              idbPromise.clearFromSyncQueue(operation.id);
            }
          });
        } else if (operation.type === 'note') {
          // Sync note
          fetch(`/notes/${operation.articleId}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              content: operation.content
            })
          })
          .then(response => {
            if (response.ok) {
              // Remove from sync queue
              idbPromise.clearFromSyncQueue(operation.id);
            }
          });
        } else if (operation.type === 'deleteNote') {
          // Sync note deletion
          fetch(`/notes/delete/${operation.noteId}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            }
          })
          .then(response => response.json())
          .then(data => {
            if (data.success) {
              // Remove from sync queue
              idbPromise.clearFromSyncQueue(operation.id);
            }
          });
        } else if (operation.type === 'removeBookmark') {
          // Sync bookmark removal
          fetch(`/bookmark/${operation.bookmarkId}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            }
          })
          .then(response => response.json())
          .then(data => {
            if (data.success) {
              // Remove from sync queue
              idbPromise.clearFromSyncQueue(operation.id);
            }
          });
        }
      });
    });
}