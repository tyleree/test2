/**
 * Minimal analytics tracking script
 * Tracks pageviews and chat questions without external dependencies
 */
(function(){
  'use strict';
  
  function post(path, type, meta) {
    type = type || 'pageview';
    try {
      fetch('/api/analytics/event', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          type: type,
          path: path,
          ref: document.referrer || null,
          meta: meta ? JSON.stringify(meta) : null
        }),
        keepalive: true
      }).catch(function() {
        // Silently fail - analytics shouldn't break the site
      });
    } catch(e) {
      // Silently fail - analytics shouldn't break the site
    }
  }
  
  function currentPath() {
    return location.pathname + location.search;
  }
  
  // Track initial pageview when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      post(currentPath(), 'pageview');
    });
  } else {
    // DOM already loaded
    post(currentPath(), 'pageview');
  }
  
  // Expose global functions for manual tracking
  window.analyticsTrack = function(path, meta) { 
    post(path || currentPath(), 'pageview', meta); 
  };
  
  window.analyticsChatHit = function(meta) { 
    post(currentPath(), 'chat_question', meta); 
  };
  
  // Track SPA navigation (if using History API)
  if (window.history && window.history.pushState) {
    var originalPushState = window.history.pushState;
    var originalReplaceState = window.history.replaceState;
    
    window.history.pushState = function() {
      originalPushState.apply(window.history, arguments);
      setTimeout(function() {
        post(currentPath(), 'pageview');
      }, 0);
    };
    
    window.history.replaceState = function() {
      originalReplaceState.apply(window.history, arguments);
      setTimeout(function() {
        post(currentPath(), 'pageview');
      }, 0);
    };
    
    window.addEventListener('popstate', function() {
      setTimeout(function() {
        post(currentPath(), 'pageview');
      }, 0);
    });
  }
})();
