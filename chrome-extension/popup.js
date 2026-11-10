// ClearPay AP Extension Popup
document.addEventListener('DOMContentLoaded', async () => {
  const apiStatusEl = document.getElementById('api-status');
  const openDashboardBtn = document.getElementById('open-dashboard');
  const pushActiveTabBtn = document.getElementById('push-active-tab');

  // Check Backend Status
  try {
    const res = await fetch('http://localhost:8000/api/health', { method: 'GET' });
    if (res.ok) {
      apiStatusEl.innerHTML = '<span class="dot-green"></span> <span style="color:#10B981;">Online (8000)</span>';
    } else {
      apiStatusEl.innerHTML = '<span class="dot-red"></span> <span style="color:#EF4444;">Offline</span>';
    }
  } catch (e) {
    apiStatusEl.innerHTML = '<span class="dot-red"></span> <span style="color:#EF4444;">Offline</span>';
  }

  // Open Dashboard in New Tab
  openDashboardBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:5173' });
  });

  // Push active Gmail tab
  pushActiveTabBtn.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url && tab.url.includes('mail.google.com')) {
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          const btn = document.querySelector('.clearpay-gmail-btn');
          if (btn) {
            btn.click();
          } else {
            alert('Please open an email in Gmail first, then click Send to ClearPay Dashboard.');
          }
        }
      });
      window.close();
    } else {
      chrome.tabs.create({ url: 'https://mail.google.com' });
    }
  });
});
