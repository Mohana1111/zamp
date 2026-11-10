// ClearPay AP 1-Click Bookmarklet
// Can be saved as a Chrome Bookmark: drag or create a bookmark with the javascript: URL
javascript:(function(){
  if(window.__clearpay_bookmarklet_loaded) {
    alert('ClearPay AP is already active on this Gmail tab!');
    return;
  }
  window.__clearpay_bookmarklet_loaded = true;

  // Load CSS
  var cssLink = document.createElement('link');
  cssLink.rel = 'stylesheet';
  cssLink.href = 'http://localhost:8000/api/sources/gmail/extension-css';
  document.head.appendChild(cssLink);

  // Load Content Script
  var script = document.createElement('script');
  script.src = 'http://localhost:8000/api/sources/gmail/extension-js';
  document.body.appendChild(script);

  console.log('[ClearPay AP Bookmarklet] Injected successfully into Gmail!');
})();
