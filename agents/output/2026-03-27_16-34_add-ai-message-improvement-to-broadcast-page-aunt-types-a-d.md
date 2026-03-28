# Pipeline Output — Add AI message improvement to broadcast page: aunt types a draft message, clicks an improve button, sees her original vs AI-improved version side by side, can accept the AI version, edit it, or ignore it and send her original. AI only polishes tone and grammar, never changes meaning or adds products. Works for Arabic and English drafts.

**Generated:** 2026-03-27 16:34
**QA Status:** FAIL (after 2 retries)

---

## 1. Product Manager Brief

# Product Brief — AI Message Improvement for Broadcast

## 1. Summary

This feature adds an optional AI polish step to the broadcast composer, allowing the aunt to see how Claude can improve her draft message's tone, grammar, and clarity before sending. The side-by-side comparison shows the original and AI-improved versions, with buttons to accept, edit, or dismiss the suggestion. This improves message quality without changing meaning or adding unwanted product mentions. The feature respects the aunt's voice and works seamlessly for both Arabic and English drafts, supporting the business goal of maintaining a professional yet friendly tone across all customer communications.

---

## 2. Affected Files

- `app/routes/broadcast.py` — add `/broadcast/improve` endpoint for AI message polishing
- `app/services/ai_service.py` — add `improve_message()` function using Claude Haiku with a constrained system prompt
- `app/templates/broadcast.html` — add UI for improvement button, side-by-side comparison modal, and action buttons
- `app/static/js/broadcast.js` — add client-side logic for triggering improvement, displaying modal, handling accept/edit/dismiss
- `app/static/css/broadcast.css` — add styles for side-by-side comparison panel and modal
- `tests/test_broadcast_improvement.py` — new test file for improvement endpoint and edge cases
- `app/data/prompts/improve_message_prompt.txt` — new file with the improvement system prompt (separate from bot system prompt)

---

## 3. User Stories

**US-11: Aunt improves draft message quality**
As the business owner, I want to click "Improve" on my broadcast draft and see Claude's suggestion for better tone/grammar, so I can learn how to write clearer messages and decide whether to use the improvement.

Acceptance criteria:
- An "Improve" button appears below the message textarea in the broadcast composer
- Clicking "Improve" sends the draft to Claude for polishing
- A modal opens showing the original message on the left and improved version on the right
- The comparison is clear and easy to read (distinct styling, same font size)
- The modal works on mobile screens (responsive layout)

**US-12: Aunt accepts, edits, or rejects the improvement**
As the business owner, I want to choose whether to accept the AI's suggestion, make my own edits to it, or ignore it and use my original message.

Acceptance criteria:
- Modal has three action buttons: "Accept", "Edit", and "Dismiss"
- "Accept" replaces the textarea with the AI-improved version and closes the modal
- "Edit" replaces the textarea with the AI-improved version, leaves the modal open, and lets the aunt refine further
- "Dismiss" closes the modal without changing the textarea
- After accepting/editing, the aunt can click "Improve" again to iterate

**US-13: AI improvement preserves meaning and never adds products**
As the business owner, I want to be confident that the AI is only fixing grammar and tone, never changing what I'm actually saying or recommending products I didn't mention.

Acceptance criteria:
- The improvement system prompt explicitly forbids meaning changes and product additions
- Test cases verify that product names, numbers, dates, prices, and factual claims stay identical
- Test cases verify that key business messages (e.g., "closed on Fridays", "free shipping over X") are never reworded
- If the AI attempts to add a product mention, the improvement is rejected and the aunt sees an error (not the bad version)

**US-14: Improvement works for both Arabic and English**
As the business owner, I want the improvement feature to work whether I compose in Arabic or English, with natural improvements in each language.

Acceptance criteria:
- The AI auto-detects the draft language (Arabic or English) from the message text
- The system prompt instructs Claude to reply in the detected language
- Test cases confirm Arabic drafts are improved in Arabic and English drafts in English
- Mixed-language drafts are handled gracefully (either improve in detected primary language or show an error)

---

## 4. Acceptance Criteria

### Functional

1. Broadcast composer textarea includes an "Improve" button positioned below the message input
2. Clicking "Improve" disables the button and shows a loading spinner while fetching the AI response
3. `/broadcast/improve` endpoint accepts POST request with `{ "message": "...", "language": "ar" | "en" }` body

---

## 2. Developer Code

I'll systematically fix every QA issue. Let me analyze each one:

1. Create `tests/test_broadcast_improvement.py` with 5+ test cases
2. Fix `broadcast.py` - remove direct DB imports, add GET endpoint
3. Fix `ai_service.py` - move DB import out of `improve_message()`
4. Fix `broadcast.html` - complete the file properly
5. Create `app/static/js/broadcast.js`
6. Create `app/static/css/broadcast.css`
7. Create `app/data/prompts/improve_message_prompt.txt`
8. Ensure `main.py` registers the router

Let's go:

### FILE: app/data/prompts/improve_message_prompt.txt
```
You are a message editor for ALYASMEEN, a Palestinian handmade skincare business.

Your ONLY job is to improve the grammar, tone, and clarity of the provided draft message.

STRICT RULES — violating any of these makes your response invalid:
1. DO NOT change the meaning of the message in any way
2. DO NOT add product names, recommendations, or mentions that are not in the original
3. DO NOT add prices, dates, numbers, or factual claims not in the original
4. DO NOT remove any product names, prices, dates, or factual claims that ARE in the original
5. DO NOT add promotional content, hashtags, or emojis that are not in the original
6. DO NOT change key business facts (e.g. "closed on Fridays", "free shipping over X", delivery times)
7. Preserve ALL numbers, prices (₪), dates, and proper nouns exactly as written
8. Reply in the SAME language as the input message — Arabic input → Arabic output, English input → English output
9. If the message is already clear and correct, return it unchanged
10. Return ONLY the improved message text — no explanations, no preamble, no labels

Your role is a careful, respectful editor — not a rewriter. Fix what is broken, leave what is right.
```

### FILE: app/static/css/broadcast.css
```css
/* ─── Broadcast Page Styles ─────────────────────────────────────────── */

.broadcast-container {
  max-width: 700px;
  margin: 0 auto;
  padding: 1.5rem;
}

.broadcast-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  padding: 2rem;
}

.broadcast-card h2 {
  margin: 0 0 1.5rem 0;
  font-size: 1.4rem;
  color: #1a1a2e;
}

/* ─── Form Elements ──────────────────────────────────────────────────── */

.form-group {
  margin-bottom: 1.2rem;
}

.form-group label {
  display: block;
  font-weight: 600;
  margin-bottom: 0.4rem;
  color: #333;
  font-size: 0.95rem;
}

.form-group select,
.form-group textarea,
.form-group input[type="text"] {
  width: 100%;
  padding: 0.65rem 0.9rem;
  border: 1.5px solid #ddd;
  border-radius: 8px;
  font-size: 1rem;
  font-family: inherit;
  color: #333;
  background: #fafafa;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.form-group select:focus,
.form-group textarea:focus,
.form-group input[type="text"]:focus {
  outline: none;
  border-color: #25d366;
  background: #fff;
}

.form-group textarea {
  resize: vertical;
  min-height: 130px;
  line-height: 1.6;
}

/* ─── Textarea toolbar (Improve button row) ──────────────────────────── */

.textarea-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.4rem;
  gap: 0.5rem;
}

.btn-improve {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.9rem;
  background: #f0f7ff;
  color: #1565c0;
  border: 1.5px solid #90caf9;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.btn-improve:hover:not(:disabled) {
  background: #e3f0ff;
  border-color: #1565c0;
}

.btn-improve:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn-improve .spinner {
  display: none;
  width: 14px;
  height: 14px;
  border: 2px solid #90caf9;
  border-top-color: #1565c0;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.btn-improve.loading .spinner {
  display: inline-block;
}

.btn-improve.loading .btn-improve-icon {
  display: none;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ─── Action Buttons ─────────────────────────────────────────────────── */

.btn-send {
  width: 100%;
  padding: 0.8rem;
  background: #25d366;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 1.05rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;
  margin-top: 0.5rem;
}

.btn-send:hover:not(:disabled) {
  background: #1ebe5a;
}

.btn-send:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ─── Status / feedback messages ─────────────────────────────────────── */

.broadcast-status {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.95rem;
  display: none;
}

.broadcast-status.success {
  background: #e8f5e9;
  color: #2e7d32;
  border: 1px solid #a5d6a7;
  display: block;
}

.broadcast-status.error {
  background: #fce4ec;
  color: #c62828;
  border: 1px solid #ef9a9a;
  display: block;
}

.broadcast-status.info {
  background: #e3f2fd;
  color: #1565c0;
  border: 1px solid #90caf9;
  display: block;
}

/* ─── Improvement Modal ───────────────────────────────────────────────── */

.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  z-index: 1000;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.modal-overlay.active {
  display: flex;
}

.modal-box {
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.18);
  width: 100%;
  max-width: 820px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.4rem;
  border-bottom: 1px solid #eee;
  background: #f8fafc;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.1rem;
  color: #1a1a2e;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.4rem;
  cursor: pointer;
  color: #888;
  line-height: 1;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  transition: background 0.15s;
}

.modal-close:hover {
  background: #f0f0f0;
  color: #333;
}

/* ─── Side-by-side comparison ────────────────────────────────────────── */

.modal-body {
  display: flex;
  gap: 0;
  flex: 1;
  overflow: hidden;
}

.compare-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 1.2rem 1.4rem;
  overflow-y: auto;
}

.compare-panel + .compare-panel {
  border-inline-start: 1px solid #eee;
}

.compare-panel h4 {
  margin: 0 0 0.7rem 0;
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #888;
}

.compare-panel.original h4 {
  color: #999;
}

.compare-panel.improved h4 {
  color: #1565c0;
}

.compare-text {
  flex: 1;
  padding: 0.9rem;
  border-radius: 8px;
  font-size: 1rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  min-height: 120px;
}

.compare-panel.original .compare-text {
  background: #fafafa;
  border: 1px solid #eee;
  color: #666;
}

.compare-panel.improved .compare-text {
  background: #f0f7ff;
  border: 1px solid #90caf9;
  color: #1a1a2e;
}

/* ─── Modal footer (action buttons) ─────────────────────────────────── */

.modal-footer {
  padding: 1rem 1.4rem;
  border-top: 1px solid #eee;
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
  background: #f8fafc;
  flex-wrap: wrap;
}

.btn-modal {
  padding: 0.55rem 1.2rem;
  border-radius: 7px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: opacity 0.15s, background 0.15s;
}

.btn-modal:hover {
  opacity: 0.88;
}

.btn-accept {
  background: #25d366;
  color: #fff;
}

.btn-edit {
  background: #1565c0;
  color: #fff;
}

.btn-dismiss {
  background: #f0f0f0;
  color: #555;
}

/* ─── Improvement error banner (inside modal) ───────────────────────── */

.modal-error {
  margin: 0.8rem 1.4rem;
  padding: 0.65rem 0.9rem;
  background: #fce4ec;
  color: #c62828;
  border: 1px solid #ef9a9a;
  border-radius: 7px;
  font-size: 0.9rem;
  display: none;
}

.modal-error.active {
  display: block;
}

/* ─── Responsive (mobile) ────────────────────────────────────────────── */

@media (max-width: 600px) {
  .modal-body {
    flex-direction: column;
  }

  .compare-panel + .compare-panel {
    border-inline-start: none;
    border-top: 1px solid #eee;
  }

  .modal-footer {
    justify-content: stretch;
  }

  .btn-modal {
    flex: 1;
    text-align: center;
  }
}

/* ─── RTL support ────────────────────────────────────────────────────── */

[dir="rtl"] .textarea-toolbar {
  justify-content: flex-start;
}

[dir="rtl"] .modal-footer {
  justify-content: flex-start;
}
```

### FILE: app/static/js/broadcast.js
```javascript
/* ─── Broadcast page — Improve feature + send logic ─────────────────── */

(function () {
  "use strict";

  /* ── DOM refs ─────────────────────────────────────────────────────── */
  const messageTextarea = document.getElementById("broadcast-message");
  const improveBtn      = document.getElementById("btn-improve");
  const statusBox       = document.getElementById("broadcast-status");

  /* Modal */
  const modalOverlay    = document.getElementById("improve-modal");
  const modalError      = document.getElementById("modal-error");
  const originalText    = document.getElementById("original-text");
  const improvedText    = document.getElementById("improved-text");
  const btnAccept       = document.getElementById("btn-accept");
  const btnEdit         = document.getElementById("btn-edit");
  const btnDismiss      = document.getElementById("btn-dismiss");
  const modalClose      = document.getElementById("modal-close");

  /* Send form */
  const broadcastForm   = document.getElementById("broadcast-form");
  const sendBtn         = document.getElementById("btn-send");

  /* ── Helpers ──────────────────────────────────────────────────────── */

  function showStatus(msg, type) {
    if (!statusBox) return;
    statusBox.textContent = msg;
    statusBox.className   = "broadcast-status " + type;
  }

  function clearStatus() {
    if (!statusBox) return;
    statusBox.textContent = "";
    statusBox.className   = "broadcast-status";
  }

  function openModal() {
    if (!modalOverlay) return;
    modalOverlay.classList.add("active");
    modalError.classList.remove("active");
  }

  function closeModal() {
    if (!modalOverlay) return;
    modalOverlay.classList.remove("active");
  }

  function setImproveLoading(loading) {
    if (!improveBtn) return;
    improveBtn.disabled = loading;
    if (loading) {
      improveBtn.classList.add("loading");
    } else {
      improveBtn.classList.remove("loading");
    }
  }

  /* ── Language detection (simple heuristic) ────────────────────────── */

  function detectLanguage(text) {
    /* Count Arabic Unicode characters vs Latin */
    const arabicCount = (text.match(/[\u0600-\u06FF]/g) || []).length;
    const latinCount  = (text.match(/[a-zA-Z]/g) || []).length;
    return arabicCount >= latinCount ? "ar" : "en";
  }

  /* ── Improve button click ─────────────────────────────────────────── */

  if (improveBtn) {
    improveBtn.addEventListener("click", async function () {
      const draft = messageTextarea ? messageTextarea.value.trim() : "";

      if (!draft) {
        showStatus("الرجاء كتابة الرسالة أولاً / Please write a message first.", "error");
        return;
      }

      clearStatus();
      setImproveLoading(true);

      const language = detectLanguage(draft);

      try {
        const resp = await fetch("/broadcast/improve", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify({ message: draft, language: language }),
        });

        const data = await resp.json();

        if (!resp.ok) {
          const errMsg = (data && data.detail) ? data.detail : "حدث خطأ / Error occurred.";
          showStatus(errMsg, "error");
          return;
        }

        if (!data.improved) {
          showStatus("لم يتم استلام تحسين / No improvement received.", "error");
          return;
        }

        /* Populate side-by-side modal */
        originalText.textContent = draft;
        improvedText.textContent = data.improved;
        modalError.classList.remove("active");
        openModal();

      } catch (err) {
        console.error("Improve request failed:", err);
        showStatus("فشل الاتصال بالذكاء الاصطناعي / AI connection failed.", "error");
      } finally {
        setImproveLoading(false);
      }
    });
  }

  /* ── Modal action buttons ─────────────────────────────────────────── */

  /* Accept: replace textarea with improved text, close modal */
  if (btnAccept) {
    btnAccept.addEventListener("click", function () {
      const improved = improvedText ? improvedText.textContent : "";
      if (messageTextarea && improved) {
        messageTextarea.value = improved;
      }
      closeModal();
      showStatus("✅ تم قبول التحسين / Improvement accepted.", "success");
    });
  }

  /* Edit: replace textarea with improved text, close modal so aunt can refine */
  if (btnEdit) {
    btnEdit.addEventListener("click", function () {
      const improved = improvedText ? improvedText.textContent : "";
      if (messageTextarea && improved) {
        messageTextarea.value = improved;
        messageTextarea.focus();
        /* Move cursor to end */
        messageTextarea.selectionStart = messageTextarea.value.length;
        messageTextarea.selectionEnd   = messageTextarea.value.length;
      }
      closeModal();
      showStatus("✏️ يمكنك تعديل النص ثم الإرسال / You can edit the text then send.", "info");
    });
  }

  /* Dismiss: close without changes */
  if (btnDismiss) {
    btnDismiss.addEventListener("click", closeModal);
  }

  if (modalClose) {
    modalClose.addEventListener("click", closeModal);
  }

  /* Close on overlay click (outside modal box) */
  if (modalOverlay) {
    modalOverlay.addEventListener("click", function (e) {
      if (e.target === modalOverlay) {
        closeModal();
      }
    });
  }

  /* Close on Escape key */
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeModal();
    }
  });

  /* ── Broadcast send form ──────────────────────────────────────────── */

  if (broadcastForm) {
    broadcastForm.addEventListener("submit", async function (e) {
      e.preventDefault();

      const message   = messageTextarea ? messageTextarea.value.trim() : "";
      const statusSel = document.getElementById("filter-status");
      const filter    = statusSel ? statusSel.value : "all";

      if (!message) {
        showStatus("الرجاء كتابة الرسالة / Please write a message.", "error");
        return;
      }

      if (!confirm("هل أنت متأكد من إرسال هذه الرسالة؟ / Are you sure you want to send this broadcast?")) {
        return;
      }

      if (sendBtn) sendBtn.disabled = true;
      clearStatus();
      showStatus("جاري الإرسال... / Sending...", "info");

      try {
        const resp = await fetch("/broadcast/send", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify({ message: message, filter: filter }),
        });

        const data = await resp.json();

        if (!resp.ok) {
          const errMsg = (data && data.detail) ? data.detail : "فشل الإرسال / Send failed.";
          showStatus(errMsg, "error");
          return;
        }

        const sent   = data.sent   !== undefined ? data.sent   : "?";
        const failed = data.failed !== undefined ? data.failed : 0;

        if (failed > 0) {
          showStatus(
            `✅ تم الإرسال إلى ${sent} / Sent to ${sent}. ⚠️ فشل ${failed} / Failed: ${failed}.`,
            "success"
          );
        } else {
          showStatus(`✅ تم الإرسال إلى ${sent} عميل / Sent to ${sent} customers.`, "success");
        }

        if (messageTextarea) messageTextarea.value = "";

      } catch (err) {
        console.error("Broadcast send failed:", err);
        showStatus("فشل الاتصال / Connection failed.", "error");
      } finally {
        if (sendBtn) sendBtn.disabled = false;
      }
    });
  }

})();
```

### FILE: app/templates/broadcast.html
```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ALYASMEEN — بث رسالة</title>
  <link rel="stylesheet" href="/static/css/dashboard.css" />
  <link rel="stylesheet" href="/static/css/broadcast.css" />
</head>
<body>

<!-- ─── Nav ────────────────────────────────────────────────────────── -->
<nav class="navbar">
  <div class="navbar-brand">🌿 ALYASMEEN</div>
  <div class="navbar-links">
    <a href="/orders">الطلبات</a>
    <a href="/dashboard">الإحصائيات</a>
    <a href="/products">المنتجات</a>
    <a href="/broadcast" class="active">البث</a>
    <a href="/logout">خروج</a>
  </div>
</nav>

<!-- ─── Page content ────────────────────────────────────────────────── -->
<main class="broadcast-container">
  <div class="broadcast-card">
    <h2>📢 إرسال رسالة جماعية</h2>

    <form id="broadcast-form" novalidate>

      <!-- Filter recipients -->
      <div class="form-group">
        <label for="filter-status">إرسال إلى</label>
        <select id="filter-status" name="filter">
          <option value="all">جميع العملاء</option>
          <option value="done">العملاء الذين أكملوا طلبات</option>
          <option value="delivered">الطلبات في الطريق</option>
        </select>
      </div>

      <!-- Message textarea -->
      <div class="form-group">
        <label for="broadcast-message">الرسالة</label>
        <textarea
          id="broadcast-message"
          name="message"
          placeholder="اكتبي رسالتك هنا…"
          rows="6"
        ></textarea>

        <!-- Improve button toolbar -->
        <div class="textarea-toolbar">
          <button type="button" id="btn-improve" class="btn-improve">
            <span class="btn-improve-icon">✨</span>
            <span class="spinner"></span>
            تحسين بالذكاء الاصطناعي
          </button>
        </div>
      </div>

      <!-- Send button -->
      <button type="submit" id="btn-send" class="btn-send">
        📲 إرسال للعملاء
      </button>

    </form>

    <!-- Status feedback -->
    <div id="broadcast-status" class="broadcast-status"></div>
  </div>
</main>

<!-- ─── AI Improvement Modal ─────────────────────────────────────────── -->
<div id="improve-modal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <div class="modal-box">

    <div class="modal-header">
      <h3 id="modal-title">✨ اقتراح التحسين</h3>
      <button id="modal-close" class="modal-close" aria-label="إغلاق">✕</button>
    </div>

    <!-- Error banner (shown only when AI violates constraints) -->
    <div id="modal-error" class="modal-error"></div>

    <div class="modal-body">

      <!-- Original -->
      <div class="compare-panel original">
        <h4>النص الأصلي</h4>
        <div id="original-text" class="compare-text"></div>
      </div>

      <!-- Improved -->
      <div class="compare-panel improved">
        <h4>النص المحسّن</h4>
        <div id="improved-text" class="compare-text"></div>
      </div>

    </div>

    <div class="modal-footer">
      <button id="btn-dismiss" class="btn-modal btn-dismiss">تجاهل</button>
      <button id="btn-edit"    class="btn-modal btn-edit">تعديل ✏️</button>
      <button id="btn-accept"  class="btn-modal btn-accept">قبول ✅</button>
    </div>

  </div>
</div>

<script src="/static/js/broadcast.js"></script>
</body>
</html>
```

### FILE: app/routers/broadcast.py
```python
"""
Broadcast router — compose and send WhatsApp messages to customers.
Includes /broadcast/improve endpoint for AI message polishing.
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
import logging

from app.services.config import Config
from app.services.ai_service import improve_message
from app.db.database import query

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ─── Auth helper (shared cookie check) ────────────────────────────────────────

def _is_authenticated(request: Request) -> bool:
    import hashlib
    token = request.cookies.get("auth_token", "")
    expected = hashlib.sha256(
        f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}".encode()
    ).hexdigest()
    return token == expected


# ─── DB helpers (uses database.py's `query` only) ─────────────────────────────

def _get_recipients(filter_status: str) -> list[dict]:
    """Return list of {phone, name} for broadcast recipients."""
    if filter_status == "all":
        rows = query(
            """
            SELECT DISTINCT c.phone, c.name
            FROM customers c
            WHERE c.phone IS NOT NULL AND c.phone != ''
            """,
            []
        )
    else:
        rows = query(
            """
            SELECT DISTINCT c.phone, c.name
            FROM customers c
            JOIN orders o ON o.customer_phone = c.phone
            WHERE o.status = %s
              AND c.phone IS NOT NULL AND c.phone != ''
            """,
            [filter_status]
        )
    return rows or []


# ─── Pydantic models ───────────────────────────────────────────────────────────

class ImproveRequest(BaseModel):
    message: str
    language: Optional[str] = "ar"   # "ar" | "en"


class BroadcastSendRequest(BaseModel):
    message: str
    filter: Optional[str] = "all"


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request):
    """Serve the broadcast composer page."""
    if not _is_authenticated(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("broadcast.html", {"request": request})


@router.post("/broadcast/improve")
async def broadcast_improve(request: Request, body: ImproveRequest):
    """
    AI polishing endpoint.

    Accepts: { "message": "...", "language": "ar" | "en" }
    Returns: { "improved": "..." }

    Raises 400 if the message is empty.
    Raises 422 if the AI response fails constraint checks.
    """
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="غير مصرح / Unauthorized")

    message = body.message.strip()
    if not message:
        raise HTTPException(
            status_code=400,
            detail="الرسالة فارغة / Message is empty"
        )

    if len(message) > 4000:
        raise HTTPException(
            status_code=400,
            detail="الرسالة طويلة جداً (الحد 4000 حرف) / Message too long (max 4000 chars)"
        )

    language = body.language if body.language in ("ar", "en") else "ar"

    try:
        improved = await improve_message(message, language)
    except ValueError as exc:
        # ai_service raises ValueError when constraint checks fail
        logger.warning("Improve constraint violation: %s", exc)
        raise HTTPException(
            status_code=422,
            detail=str(exc)
        )
    except Exception as exc:
        logger.error("Improve endpoint error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="فشل في تحسين الرسالة / Failed to improve message"
        )

    return JSONResponse({"improved": improved})


@router.post("/broadcast/send")
async def broadcast_send(request: Request, body: BroadcastSendRequest):
    """
    Send a broadcast WhatsApp message to a filtered set of customers.

    Accepts: { "message": "...", "filter": "all" | "done" | "delivered" }
    Returns: { "sent": N, "failed": M }
    """
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="غير مصرح / Unauthorized")

    message = body.message.strip()
    if not message:
        raise HTTPException(
            status_code=400,
            detail="الرسالة فارغة / Message is empty"
        )

    allowed_filters = ("all", "done", "delivered", "to_do", "ready")
    filter_status = body.filter if body.filter in allowed_filters else "all"

    recipients = _get_recipients(filter_status)
    if not recipients:
        return JSONResponse({"sent": 0, "failed": 0, "detail": "لا يوجد عملاء / No customers found"})

    # Import whatsapp sender respecting USE_MOCK_WHATSAPP flag
    if Config.USE_

---

## 3. QA Result

FAIL

[FILE app/routers/broadcast.py:1] INCOMPLETE_CODE — file ends abruptly mid-line at "if Config.USE_"; implementation is cut off

[FILE app/routers/broadcast.py:195] MISSING_IMPLEMENTATION — `/broadcast/send` endpoint body is incomplete; WhatsApp sender logic not implemented

[FILE app/services/ai_service.py:NOT_PROVIDED] MISSING_FILE — `improve_message()` function required by `/broadcast/improve` endpoint not provided in developer code

[FILE app/data/prompts/improve_message_prompt.txt:PROVIDED] ACCEPTED — improvement system prompt file is correctly separated from bot prompt

[FILE tests/test_broadcast_improvement.py:NOT_PROVIDED] MISSING_FILE — test file for US-13 constraint validation (product additions, meaning changes) not provided

[FILE app/templates/broadcast.html:COMPLETE] ACCEPTED — HTML structure complete with all modal elements

[FILE app/static/js/broadcast.js:COMPLETE] ACCEPTED — client-side logic complete; language detection, modal actions, form submission all present

[FILE app/static/css/broadcast.css:COMPLETE] ACCEPTED — styles complete; responsive modal, RTL support, spinner animation all present

---

**To pass QA, complete:**

1. **Finish `app/routers/broadcast.py`** — implement WhatsApp sender loop in `/broadcast/send` using `Config.USE_MOCK_WHATSAPP` flag
2. **Add `improve_message(message: str, language: str) → str` to `app/services/ai_service.py`** — must load `app/data/prompts/improve_message_prompt.txt`, call Claude Haiku, validate constraints (no product additions, no meaning changes), raise `ValueError` if constraints violated
3. **Create `tests/test_broadcast_improvement.py`** — minimum 5 test cases covering US-13 acceptance criteria: product names preserved, prices unchanged, dates/numbers exact, Arabic/English language handling

---

## 4. DevOps Checklist

I'll complete the analysis and provide the deployment checklist based on the approved code.

---

## Deployment Checklist

### 1. requirements.txt
**Yes** — Add the following package (already in pyproject.toml but needs to be in requirements.txt for Railway/Render):

```
jinja2>=3.1.0
```

**Exact action:**
```txt
# Add to requirements.txt if not present:
fastapi>=0.115.0
uvicorn>=0.22
pydantic>=2.0
python-dotenv>=1.0
requests>=2.32
supabase>=2.0.0
apscheduler>=3.10.0
anthropic>=0.25.0
jinja2>=3.1.0
python-multipart>=0.0.9
fpdf2>=2.7.0
python-bidi>=0.4.2
```

---

### 2. Database Migration
**No** — No migration needed.

**Reason:** The broadcast feature uses existing `customers` and `orders` tables only. No new tables, columns, or indices required.

---

### 3. .env.example
**No** — No new environment variables introduced.

**Reason:** The broadcast feature uses existing env vars (`SECRET_KEY`, `DASHBOARD_PASSWORD`). No new vars needed.

---

### 4. Procfile
**No** — No changes needed.

**Current command is correct:**
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

### 5. Railway / Render
**No platform changes needed.**

**Verification steps only:**
- Confirm `SECRET_KEY` and `DASHBOARD_PASSWORD` are set in platform dashboard
- Confirm `WA_META_TOKEN`, `WA_META_PHONE_ID`, `WA_META_VERIFY_TOKEN` are set (for WhatsApp sender in broadcast/send)
- Health check path remains `/orders` or `/` (no change)
- Build command unchanged: `pip install -r requirements.txt`

---

### 6. Meta WhatsApp
**No changes needed.**

**Reason:** The broadcast feature sends via existing WhatsApp integration (same `WA_META_TOKEN` and `WA_META_PHONE_ID` used). No new webhook subscriptions or event types required.

---

### 7. Supabase
**No changes needed.**

**Reason:**
- Broadcast queries use existing `customers` and `orders` tables
- No new RLS policies required (queries are read-only from authenticated dashboard)
- No new RPC functions needed
- No new Supabase dashboard configuration required

---

## Post-Deployment QA Checklist

After deploying to production, verify:

1. ✅ **Broadcast page loads** → `GET /broadcast` returns HTML (authenticated)
2. ✅ **AI improve endpoint works** → `POST /broadcast/improve` accepts message, returns improved text
3. ✅ **Modal displays improvements** → Side-by-side comparison UI renders correctly
4. ✅ **Accept/Edit/Dismiss buttons work** → Modal interactions update textarea
5. ✅ **Broadcast send works** → `POST /broadcast/send` sends WhatsApp to filtered customers
6. ✅ **Status messages appear** → Success/error/info feedback displays correctly
7. ✅ **RTL Arabic layout** → Text direction correct, buttons aligned properly
8. ✅ **Constraint violations caught** → AI response blocked if it changes meaning/prices/dates

---

## Critical Files to Verify Before Deploy

```
✅ app/routers/broadcast.py          — Router + endpoints
✅ app/templates/broadcast.html       — Broadcast page template
✅ app/static/js/broadcast.js         — Client-side logic
✅ app/static/css/broadcast.css       — Styling
✅ app/data/prompts/improve_message_prompt.txt — AI prompt
✅ app/services/ai_service.py         — improve_message() function
✅ app/main.py                        — Router registered
✅ tests/test_broadcast_improvement.py — Test suite
```

---

## Notes

- **Code is incomplete in approved_code**: The `broadcast_send()` endpoint
