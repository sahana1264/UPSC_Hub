const CACHE_NAME = 'upsc-news-hub-v1';
const DYNAMIC_CACHE = 'upsc-news-dynamic-v1';

// Assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/favicon.ico',
  '/static/offline.html',
  '/static/js/app.js',
  '/static/js/idb.js',
  '/static/manifest.json'
];

// Install event - cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(cacheName => {
          return cacheName !== CACHE_NAME && cacheName !== DYNAMIC_CACHE;
        }).map(cacheName => {
          console.log('Deleting old cache', cacheName);
          return caches.delete(cacheName);
        })
      );
    })
  );
});

// Fetch event - serve from cache or network
self.addEventListener('fetch', event => {
  // Skip non-GET requests and browser extensions
  if (event.request.method !== 'GET' || 
      !event.request.url.startsWith('http')) {
    return;
  }

  // API requests - handle differently for offline sync
  if (event.request.url.includes('/api/')) {
    return handleApiRequest(event);
  }

  // Regular assets and pages
  event.respondWith(
    caches.match(event.request)
      .then(cachedResponse => {
        // Return cached response if found
        if (cachedResponse) {
          return cachedResponse;
        }

        // Otherwise fetch from network
        return fetch(event.request)
          .then(response => {
            // Clone the response
            const responseToCache = response.clone();
            
            // Open dynamic cache and store the response
            caches.open(DYNAMIC_CACHE)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });
            
            return response;
          })
          .catch(error => {
            // If it's a page request, show offline page
            if (event.request.headers.get('accept').includes('text/html')) {
              return caches.match('/offline');
            }
            
            console.error('Fetch failed:', error);
            // For other resources, just fail
            throw error;
          });
      })
  );
});

// Handle API requests
function handleApiRequest(event) {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        return response;
      })
      .catch(error => {
        // If offline, return cached data if available
        return caches.match(event.request);
      })
  );
}

// Listen for messages from the client
self.addEventListener('message', event => {
  if (event.data.action === 'skipWaiting') {
    self.skipWaiting();
  }
});