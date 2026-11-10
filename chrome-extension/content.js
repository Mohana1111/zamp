// ClearPay AP — Gmail Ingestion & Dashboard Bridge Content Script
(function () {
  const isLocalDashboard =
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1';

  // 1. If running on ClearPay Dashboard tab: notify Dashboard that Extension is active
  if (isLocalDashboard) {
    try {
      window.__CLEARPAY_EXTENSION_ACTIVE__ = true;
      window.dispatchEvent(new CustomEvent('clearpay-extension-connected', { detail: { version: '2.4.0' } }));
      document.dispatchEvent(new CustomEvent('clearpay-extension-connected', { detail: { version: '2.4.0' } }));
    } catch (e) {
      console.warn('[ClearPay Extension] Bridge event dispatch error', e);
    }
    return;
  }

  // 2. If running on mail.google.com: Inject Right-Side Dock, Drawer, and Inline Action Buttons
  console.log('[ClearPay AP Extension] Initialized on mail.google.com');

  const FORWARD_EMAIL = 'ap-invoices@acmemfg.in';
  const BACKEND_URL = 'http://localhost:8000';
  const DASHBOARD_URL = 'http://localhost:5173';

  // Helper: Scrape active open Gmail thread
  function scrapeActiveThread() {
    // Subject
    const subjectEl = document.querySelector('h2.hP');
    const subject = subjectEl ? subjectEl.textContent.trim() : document.title || 'Vendor Invoice Email';

    // Sender
    const senderEl = document.querySelector('span.gD');
    const senderEmail = senderEl?.getAttribute('email') || '';
    const senderName = senderEl?.textContent?.trim() || '';
    const sender = senderEmail ? `${senderName} <${senderEmail}>` : senderName || 'vendor@accounts.com';

    // Date
    const dateEl = document.querySelector('span.g3');
    const dateStr = dateEl?.getAttribute('title') || dateEl?.textContent?.trim() || new Date().toISOString();

    // Body & Thread Messages
    const bodyContainers = document.querySelectorAll('div.a3s');
    const threadHistory = [];
    let combinedBody = '';

    bodyContainers.forEach((bEl, idx) => {
      const text = bEl.innerText.trim();
      if (text) {
        if (!combinedBody) combinedBody = text;
        threadHistory.push({
          sender: idx === 0 ? sender : 'Thread Participant',
          timestamp: dateStr,
          body: text.substring(0, 2500)
        });
      }
    });

    // Attachment Names
    const attEls = document.querySelectorAll('.aZo, [download_url], .aV3, .aVo, .a4U');
    const attNames = [];
    attEls.forEach((el) => {
      let name = el.getAttribute('download_url') || el.textContent.trim();
      if (name) {
        if (name.includes(':')) {
          const parts = name.split(':');
          name = parts[1] || parts[0];
        }
        if (name && !attNames.includes(name)) attNames.push(name);
      }
    });

    return {
      sender,
      subject,
      date: dateStr,
      body: combinedBody,
      thread_history: threadHistory.length > 0 ? threadHistory : null,
      attachment_name: attNames[0] || null,
      quotation_name: attNames[1] || null,
      attNames
    };
  }

  // Toast Notification
  function showClearPayToast(data, customTitle = '⚡ ClearPay Autonomous Agent') {
    const existing = document.getElementById('clearpay-toast-banner');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'clearpay-toast-banner';
    toast.className = 'clearpay-toast';

    const alreadyExists = data && data.already_exists;
    const invNo = data?.run?.standard_invoice?.invoice_number?.value || data?.run?.run_id || 'INV';
    const quoteNo = data?.matched_quotation_number || 'Quotation Ledger';

    toast.innerHTML = `
      <div class="clearpay-toast-header">
        <div class="clearpay-toast-title">
          <span>${customTitle}</span>
        </div>
        <button class="clearpay-toast-close" id="clearpay-toast-close">&times;</button>
      </div>
      <div class="clearpay-toast-body">
        ${
          alreadyExists
            ? `<strong>Skipped Duplicate:</strong> Invoice <strong>${invNo}</strong> and Quotation <strong>${quoteNo}</strong> are already present on the Dashboard!`
            : `<strong>Invoice Received:</strong> Ingested <strong>${invNo}</strong> on Dashboard & matched with <strong>${quoteNo}</strong>!`
        }
      </div>
      <div>
        <a href="${DASHBOARD_URL}" target="_blank" class="clearpay-toast-action">
          View on ClearPay Dashboard &rarr;
        </a>
      </div>
    `;

    document.body.appendChild(toast);

    document.getElementById('clearpay-toast-close')?.addEventListener('click', () => {
      toast.remove();
    });

    setTimeout(() => {
      if (toast.parentNode) toast.remove();
    }, 9000);
  }

  // Send Thread to Site Agent
  async function sendThreadToClearPay(btnElement, isForwardMode = false) {
    const originalText = btnElement ? btnElement.innerHTML : '';
    if (btnElement) {
      btnElement.disabled = true;
      btnElement.innerHTML = `<span>⏳ Ingesting to ClearPay...</span>`;
    }

    try {
      const threadData = scrapeActiveThread();
      const payload = {
        sender: threadData.sender,
        subject: isForwardMode ? `Fwd: ${threadData.subject}` : threadData.subject,
        date: threadData.date,
        body: threadData.body,
        thread_history: threadData.thread_history,
        attachment_name: threadData.attachment_name,
        quotation_name: threadData.quotation_name
      };

      const res = await fetch(`${BACKEND_URL}/api/sources/gmail/extension-push`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server returned HTTP ${res.status}`);
      }

      const resData = await res.json();
      if (btnElement) {
        btnElement.innerHTML = `<span>✓ On Dashboard</span>`;
        btnElement.style.background = '#059669';
      }

      showClearPayToast(
        resData,
        isForwardMode
          ? `↪ Forwarded to ${FORWARD_EMAIL}`
          : '⚡ Sent Directly to ClearPay Site'
      );
    } catch (err) {
      console.error('[ClearPay Extension] Push error', err);
      if (btnElement) {
        btnElement.disabled = false;
        btnElement.innerHTML = originalText;
      }
      alert(`Could not connect to ClearPay AP backend (${BACKEND_URL}):\n${err.message}\n\nPlease verify ClearPay AP backend is running.`);
    }
  }

  // 1. Inject Right-Side Dock Button & Slide-Out Panel
  function injectRightSideDockAndPanel() {
    if (document.getElementById('clearpay-side-dock-btn')) return;

    // Side Dock Tab on right edge
    const dockBtn = document.createElement('div');
    dockBtn.id = 'clearpay-side-dock-btn';
    dockBtn.className = 'clearpay-side-dock-btn';
    dockBtn.innerHTML = `
      <span class="clearpay-dock-icon">⚡</span>
      <span class="clearpay-dock-text">CLEARPAY AP</span>
    `;

    // Slide-out Drawer Panel
    const panel = document.createElement('div');
    panel.id = 'clearpay-side-panel';
    panel.className = 'clearpay-side-panel';
    panel.innerHTML = `
      <div class="clearpay-panel-header">
        <div class="clearpay-panel-title">
          <span>⚡ ClearPay AP Assistant</span>
        </div>
        <button class="clearpay-panel-close" id="clearpay-panel-close">&times;</button>
      </div>

      <div class="clearpay-panel-content">
        <div class="clearpay-info-card">
          <div class="clearpay-info-row">
            <span class="clearpay-info-label">Current Thread:</span>
            <span class="clearpay-info-val" id="clearpay-panel-subject">No thread selected</span>
          </div>
          <div class="clearpay-info-row">
            <span class="clearpay-info-label">Sender:</span>
            <span class="clearpay-info-val" id="clearpay-panel-sender">-</span>
          </div>
          <div class="clearpay-info-row">
            <span class="clearpay-info-label">Attachments:</span>
            <span class="clearpay-info-val" id="clearpay-panel-files">None</span>
          </div>
        </div>

        <button class="clearpay-action-btn-primary" id="clearpay-panel-send-btn">
          <span>⚡ Send Thread to ClearPay Site</span>
        </button>

        <button class="clearpay-action-btn-secondary" id="clearpay-panel-forward-btn">
          <span>↪ Forward to ap-invoices@acmemfg.in</span>
        </button>

        <div style="border-top: 1px solid #262626; padding-top: 12px; margin-top: auto;">
          <a href="${DASHBOARD_URL}" target="_blank" style="color: #34D399; font-size: 11px; text-decoration: underline; display: block; text-align: center;">
            Open ClearPay Autonomous Dashboard &rarr;
          </a>
        </div>
      </div>
    `;

    dockBtn.addEventListener('click', () => {
      panel.classList.toggle('open');
      // Update info in panel
      const thread = scrapeActiveThread();
      const subEl = document.getElementById('clearpay-panel-subject');
      const senderEl = document.getElementById('clearpay-panel-sender');
      const filesEl = document.getElementById('clearpay-panel-files');
      if (subEl) subEl.textContent = thread.subject || 'No open thread';
      if (senderEl) senderEl.textContent = thread.sender || '-';
      if (filesEl) filesEl.textContent = thread.attNames.length > 0 ? thread.attNames.join(', ') : 'None detected';
    });

    panel.querySelector('#clearpay-panel-close')?.addEventListener('click', () => {
      panel.classList.remove('open');
    });

    panel.querySelector('#clearpay-panel-send-btn')?.addEventListener('click', (e) => {
      sendThreadToClearPay(e.currentTarget, false);
    });

    panel.querySelector('#clearpay-panel-forward-btn')?.addEventListener('click', (e) => {
      sendThreadToClearPay(e.currentTarget, true);
    });

    document.body.appendChild(dockBtn);
    document.body.appendChild(panel);
  }

  // 2. Inject Bottom Buttons alongside Gmail's native Reply / Reply all / Forward bar
  function injectBottomReplyForwardButtons() {
    // Gmail reply/forward bottom bar is in div.amn or div.btC or .gA.gt
    const replyBars = document.querySelectorAll('div.amn, div.btC');
    replyBars.forEach((bar) => {
      if (bar.querySelector('.clearpay-bottom-bar-strip')) return;

      const strip = document.createElement('div');
      strip.className = 'clearpay-bottom-bar-strip';

      const sendBtn = document.createElement('button');
      sendBtn.type = 'button';
      sendBtn.className = 'clearpay-inline-btn clearpay-btn-send';
      sendBtn.innerHTML = `<span>⚡ Send to ClearPay Site</span>`;
      sendBtn.title = 'Scrapes this entire email thread & attachments and sends directly to ClearPay AP Dashboard';
      sendBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        sendThreadToClearPay(sendBtn, false);
      });

      const forwardBtn = document.createElement('button');
      forwardBtn.type = 'button';
      forwardBtn.className = 'clearpay-inline-btn clearpay-btn-forward';
      forwardBtn.innerHTML = `<span>↪ Forward to ap-invoices@acmemfg.in</span>`;
      forwardBtn.title = 'Automatically routes this email thread to ap-invoices@acmemfg.in for autonomous processing';
      forwardBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        sendThreadToClearPay(forwardBtn, true);
      });

      strip.appendChild(sendBtn);
      strip.appendChild(forwardBtn);
      bar.appendChild(strip);
    });

    // Also inject header button next to Subject (h2.hP)
    const subjectEl = document.querySelector('h2.hP');
    if (subjectEl && !subjectEl.parentNode.querySelector('.clearpay-subject-btn')) {
      const topBtn = document.createElement('button');
      topBtn.type = 'button';
      topBtn.className = 'clearpay-inline-btn clearpay-btn-send clearpay-subject-btn';
      topBtn.style.marginLeft = '16px';
      topBtn.style.fontSize = '12px';
      topBtn.innerHTML = `<span>⚡ Send to ClearPay Site</span>`;
      topBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        sendThreadToClearPay(topBtn, false);
      });
      subjectEl.parentNode.appendChild(topBtn);
    }
  }

  // 3. Native Gmail Forward Interception:
  // Watch if user forwards an email to ap-invoices@acmemfg.in using Gmail's own compose window
  function watchNativeForwardCompose() {
    const sendButtons = document.querySelectorAll('div[data-tooltip*="Send"], div[aria-label*="Send"]');
    sendButtons.forEach((btn) => {
      if (btn.__clearpay_intercepted) return;
      btn.__clearpay_intercepted = true;

      btn.addEventListener('click', () => {
        try {
          const composeBox = btn.closest('div[role="dialog"]') || document.querySelector('div.M9');
          if (composeBox) {
            const textContent = composeBox.innerText || '';
            if (textContent.includes('ap-invoices@acmemfg.in') || textContent.includes('acmemfg.in')) {
              // The user is forwarding to ap-invoices@acmemfg.in!
              sendThreadToClearPay(null, true);
            }
          }
        } catch (e) {
          console.warn('[ClearPay Extension] Compose intercept check error', e);
        }
      });
    });
  }

  // Initial Run
  injectRightSideDockAndPanel();
  injectBottomReplyForwardButtons();
  watchNativeForwardCompose();

  // Observer for Gmail SPA dynamic page transitions
  const observer = new MutationObserver(() => {
    injectRightSideDockAndPanel();
    injectBottomReplyForwardButtons();
    watchNativeForwardCompose();
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
