

// IndexedDB utility functions
const idbPromise = {
  // Database name and version
  dbName: 'upsc-news-hub',
  dbVersion: 2, // Incremented version to ensure schema updates
  
  // Open database connection
  openDB: function() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);
      
      // Create object stores on first load or version change
      request.onupgradeneeded = event => {
        const db = event.target.result;
        
        // Create bookmarks store with all needed fields
        if (!db.objectStoreNames.contains('bookmarks')) {
          const bookmarksStore = db.createObjectStore('bookmarks', { keyPath: 'id' });
          bookmarksStore.createIndex('user_id', 'user_id', { unique: false });
          bookmarksStore.createIndex('article_id', 'article_id', { unique: false });
          
          // Add summary field to bookmarks
          if (event.oldVersion < 2) {
            const transaction = event.target.transaction;
            const tempStore = transaction.objectStore('bookmarks');
            const req = tempStore.getAll();
            req.onsuccess = () => {
              req.result.forEach(bookmark => {
                if (!bookmark.hasOwnProperty('summary')) {
                  bookmark.summary = ''; // Initialize with empty summary
                  tempStore.put(bookmark);
                }
              });
            };
          }
        } else if (event.oldVersion < 2) {
          // For existing bookmarks store, ensure summary field exists
          const transaction = event.target.transaction;
          const bookmarksStore = transaction.objectStore('bookmarks');
          const req = bookmarksStore.getAll();
          req.onsuccess = () => {
            req.result.forEach(bookmark => {
              if (!bookmark.hasOwnProperty('summary')) {
                bookmark.summary = ''; // Initialize with empty summary
                bookmarksStore.put(bookmark);
              }
            });
          };
        }
        
        // Create notes store
        if (!db.objectStoreNames.contains('notes')) {
          const notesStore = db.createObjectStore('notes', { keyPath: 'id' });
          notesStore.createIndex('user_id', 'user_id', { unique: false });
          notesStore.createIndex('article_id', 'article_id', { unique: false });
        }
        
        // Create sync queue store for offline operations
        if (!db.objectStoreNames.contains('syncQueue')) {
          db.createObjectStore('syncQueue', { keyPath: 'id', autoIncrement: true });
        }
      };
      
      request.onsuccess = event => {
        resolve(event.target.result);
      };
      
      request.onerror = event => {
        reject('IndexedDB error: ' + event.target.errorCode);
      };
    });
  },
  
  // Get all items from a store
  getAll: function(storeName) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, 'readonly');
        const store = transaction.objectStore(storeName);
        const request = store.getAll();
        
        request.onsuccess = () => {
          resolve(request.result);
        };
        
        request.onerror = event => {
          reject('Error getting data: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Get bookmarks with summaries (specific method for bookmarks)
  getBookmarksWithSummaries: function(userId) {
    return this.getByIndex('bookmarks', 'user_id', userId).then(bookmarks => {
      return bookmarks.map(bookmark => ({
        ...bookmark,
        summary: bookmark.summary || 'No summary available' // Fallback
      }));
    });
  },
  
  // Get item by ID
  getById: function(storeName, id) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, 'readonly');
        const store = transaction.objectStore(storeName);
        const request = store.get(id);
        
        request.onsuccess = () => {
          resolve(request.result);
        };
        
        request.onerror = event => {
          reject('Error getting item: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Get items by index
  getByIndex: function(storeName, indexName, value) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, 'readonly');
        const store = transaction.objectStore(storeName);
        const index = store.index(indexName);
        const request = index.getAll(value);
        
        request.onsuccess = () => {
          resolve(request.result);
        };
        
        request.onerror = event => {
          reject('Error getting items by index: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Add bookmark with all required fields including summary
  addBookmark: function(bookmarkData) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction('bookmarks', 'readwrite');
        const store = transaction.objectStore('bookmarks');
        
        // Ensure all required fields are present
        const completeBookmark = {
          id: bookmarkData.id,
          user_id: bookmarkData.user_id,
          article_id: bookmarkData.article_id,
          title: bookmarkData.title,
          gs_paper: bookmarkData.gs_paper,
          summary: bookmarkData.summary || '', // Ensure summary exists
          link: bookmarkData.link,
          date_added: bookmarkData.date_added || new Date().toISOString()
        };
        
        const request = store.add(completeBookmark);
        
        request.onsuccess = () => {
          resolve(request.result);
        };
        
        request.onerror = event => {
          reject('Error adding bookmark: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Update bookmark including summary
  updateBookmark: function(bookmarkData) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction('bookmarks', 'readwrite');
        const store = transaction.objectStore('bookmarks');
        
        // Get existing bookmark first
        const getRequest = store.get(bookmarkData.id);
        
        getRequest.onsuccess = () => {
          const existing = getRequest.result || {};
          const updatedBookmark = {
            ...existing,
            ...bookmarkData,
            // Ensure summary is preserved if not provided
            summary: bookmarkData.hasOwnProperty('summary') ? bookmarkData.summary : existing.summary
          };
          
          const putRequest = store.put(updatedBookmark);
          
          putRequest.onsuccess = () => {
            resolve(putRequest.result);
          };
          
          putRequest.onerror = event => {
            reject('Error updating bookmark: ' + event.target.errorCode);
          };
        };
        
        getRequest.onerror = event => {
          reject('Error getting bookmark for update: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Add item to store (generic)
  add: function(storeName, item) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, 'readwrite');
        const store = transaction.objectStore(storeName);
        const request = store.add(item);
        
        request.onsuccess = () => {
          resolve(request.result);
        };
        
        request.onerror = event => {
          reject('Error adding item: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Update item in store (generic)
  update: function(storeName, item) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, 'readwrite');
        const store = transaction.objectStore(storeName);
        const request = store.put(item);
        
        request.onsuccess = () => {
          resolve(request.result);
        };
        
        request.onerror = event => {
          reject('Error updating item: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Delete item from store
  delete: function(storeName, id) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, 'readwrite');
        const store = transaction.objectStore(storeName);
        const request = store.delete(id);
        
        request.onsuccess = () => {
          resolve();
        };
        
        request.onerror = event => {
          reject('Error deleting item: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Add operation to sync queue for offline operations
  addToSyncQueue: function(operation) {
    return this.openDB().then(db => {
      return new Promise((resolve, reject) => {
        const transaction = db.transaction('syncQueue', 'readwrite');
        const store = transaction.objectStore('syncQueue');
        const request = store.add(operation);
        
        request.onsuccess = () => {
          resolve(request.result);
        };
        
        request.onerror = event => {
          reject('Error adding to sync queue: ' + event.target.errorCode);
        };
      });
    });
  },
  
  // Get all operations from sync queue
  getSyncQueue: function() {
    return this.getAll('syncQueue');
  },
  
  // Clear processed operations from sync queue
  clearFromSyncQueue: function(id) {
    return this.delete('syncQueue', id);
  },
  
  // Special method to sync bookmarks with server when online
  syncBookmarks: function(userId) {
    return this.getSyncQueue().then(queue => {
      const bookmarkOps = queue.filter(op => op.type === 'bookmark');
      const promises = [];
      
      bookmarkOps.forEach(op => {
        if (op.action === 'add') {
          promises.push(
            fetch(`/bookmark/${op.article_id}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
              if (data.success) {
                return this.clearFromSyncQueue(op.id);
              }
              throw new Error('Bookmark sync failed');
            })
          );
        } else if (op.action === 'remove') {
          promises.push(
            fetch(`/bookmark/${op.article_id}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
              if (data.success) {
                return this.clearFromSyncQueue(op.id);
              }
              throw new Error('Bookmark removal sync failed');
            })
          );
        }
      });
      
      return Promise.all(promises);
    });
  }
};