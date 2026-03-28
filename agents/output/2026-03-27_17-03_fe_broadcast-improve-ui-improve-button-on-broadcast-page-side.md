# Frontend Pipeline Output — broadcast improve UI: improve button on broadcast page, side-by-side modal showing original vs AI-improved version, accept/edit/ignore buttons, Arabic RTL layout, loading spinner, error handling if AI fails

**Generated:** 2026-03-27 17:03
**Visual QA Status:** FAIL (after 1 retries)

**Backend context:** `agents/output/2026-03-27_16-53_add-ai-message-improvement-to-broadcast-page-aunt-types-a-d.md`

---

## Frontend Developer Code

```
### FILE: app/templates/broadcast.html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>البث - ALYASMEEN</title>
    <link rel="stylesheet" href="/static/css/broadcast_improve.css">
</head>
<body>
    <nav class="navbar">
        <div class="navbar-brand">🌿 ALYASMEEN</div>
        <div class="navbar-links">
            <a href="/dashboard">لوحة التحكم</a>
            <a href="/orders">الطلبات</a>
            <a href="/products">المنتجات</a>
            <a href="/broadcast" class="active">البث</a>
        </div>
    </nav>

    <main class="main-container">
        <div class="page-header">
            <h1 class="page-title">إرسال رسالة جماعية</h1>
            <p class="page-subtitle">أرسلي رسالة لجميع عملائك أو مجموعة محددة منهم</p>
        </div>

        <div class="broadcast-card">
            <form id="broadcast-form">
                <div class="form-group">
                    <label for="segment-select">الفئة المستهدفة</label>
                    <select id="segment-select" name="segment">
                        <option value="all">جميع العملاء</option>
                        <option value="recent">العملاء الجدد (آخر 30 يوم)</option>
                        <option value="vip">عملاء VIP</option>
                    </select>
                </div>

                <div class="form-group">
                    <label for="message-draft">نص الرسالة</label>
                    <textarea
                        id="message-draft"
                        name="message"
                        rows="6"
                        placeholder="اكتبي رسالتك هنا..."
                        maxlength="2000"
                    ></textarea>
                    <div class="char-count">
                        <span id="char-counter">0</span> / 2000
                    </div>
                </div>

                <div class="form-actions">
                    <button type="button" id="improve-btn" class="btn btn-improve" aria-label="تحسين الرسالة بالذكاء الاصطناعي">
                        <span class="btn-icon">✨</span>
                        تحسين بالذكاء الاصطناعي
                    </button>
                    <button type="submit" class="btn btn-send" aria-label="إرسال الرسالة الجماعية">
                        <span class="btn-icon">📤</span>
                        إرسال
                    </button>
                </div>
            </form>
        </div>

        {% if messages %}
        <div class="broadcast-history">
            <h2>سجل الرسائل السابقة</h2>
            {% for msg in messages %}
            <div class="history-item">
                <div class="history-meta">
                    <span class="history-date">{{ msg.sent_at }}</span>
                    <span class="history-segment">{{ msg.segment }}</span>
                </div>
                <div class="history-text">{{ msg.content }}</div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </main>

    <!-- Improvement Modal -->
    <div id="improve-modal" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-title" hidden>
        <div class="modal-container">
            <div class="modal-header">
                <h2 id="modal-title" class="modal-title">مقارنة النص المحسّن</h2>
                <button type="button" id="modal-close-btn" class="modal-close" aria-label="إغلاق نافذة المقارنة">✕</button>
            </div>

            <div class="modal-body">
                <div class="comparison-grid">
                    <div class="comparison-panel comparison-panel--original" dir="rtl">
                        <div class="panel-label" id="label-original">النص الأصلي</div>
                        <div
                            class="panel-text"
                            id="original-text"
                            role="region"
                            aria-labelledby="label-original"
                        ></div>
                    </div>

                    <div class="comparison-panel comparison-panel--improved" dir="rtl">
                        <div class="panel-label" id="label-improved">النص المحسّن ✨</div>
                        <div
                            class="panel-text"
                            id="improved-text"
                            role="region"
                            aria-labelledby="label-improved"
                        ></div>
                        <textarea
                            id="improved-editor"
                            class="panel-editor"
                            aria-label="تعديل النص المحسّن"
                            rows="6"
                            hidden
                        ></textarea>
                    </div>
                </div>
            </div>

            <div class="modal-actions">
                <button type="button" id="accept-btn" class="btn btn-accept" aria-label="قبول النص المحسّن واستخدامه">
                    ✓ قبول
                </button>
                <button type="button" id="edit-btn" class="btn btn-edit" aria-label="تعديل النص المحسّن قبل الإرسال">
                    ✏️ تعديل
                </button>
                <button type="button" id="save-edit-btn" class="btn btn-save-edit" aria-label="حفظ التعديل" hidden>
                    💾 حفظ التعديل
                </button>
                <button type="button" id="reject-btn" class="btn btn-reject" aria-label="رفض التحسين والإبقاء على النص الأصلي">
                    ✕ تجاهل
                </button>
            </div>
        </div>
    </div>

    <!-- Loading Spinner Overlay -->
    <div id="spinner-overlay" class="spinner-overlay" hidden aria-live="polite" aria-label="جارٍ التحسين...">
        <div class="spinner" role="status">
            <span class="sr-only">جارٍ تحسين الرسالة...</span>
        </div>
        <p class="spinner-label">جارٍ التحسين بالذكاء الاصطناعي...</p>
    </div>

    <!-- Error Toast -->
    <div id="error-toast" class="error-toast" role="alert" aria-live="assertive" hidden>
        <span id="error-toast-message" class="error-toast-message"></span>
        <button type="button" id="error-toast-close" class="error-toast-close" aria-label="إغلاق رسالة الخطأ">✕</button>
    </div>

    <script src="/static/js/broadcast_improve.js"></script>
</body>
</html>
```

```
### FILE: app/static/js/broadcast_improve.js
(function () {
    "use strict";

    // ── Element references ───────────────────────────────────────────────────
    const draftTextarea   = document.getElementById("message-draft");
    const charCounter     = document.getElementById("char-counter");
    const improveBtn      = document.getElementById("improve-btn");
    const broadcastForm   = document.getElementById("broadcast-form");

    const modal           = document.getElementById("improve-modal");
    const modalCloseBtn   = document.getElementById("modal-close-btn");
    const originalText    = document.getElementById("original-text");
    const improvedText    = document.getElementById("improved-text");
    const improvedEditor  = document.getElementById("improved-editor");

    const acceptBtn       = document.getElementById("accept-btn");
    const editBtn         = document.getElementById("edit-btn");
    const saveEditBtn     = document.getElementById("save-edit-btn");
    const rejectBtn       = document.getElementById("reject-btn");

    const spinnerOverlay  = document.getElementById("spinner-overlay");
    const errorToast      = document.getElementById("error-toast");
    const errorToastMsg   = document.getElementById("error-toast-message");
    const errorToastClose = document.getElementById("error-toast-close");

    // ── State ────────────────────────────────────────────────────────────────
    let currentImproved = "";
    let currentLanguage = "ar";

    // ── Character counter ────────────────────────────────────────────────────
    function updateCharCount() {
        const len = draftTextarea.value.length;
        charCounter.textContent = len;
        charCounter.classList.toggle("char-count--warning", len > 1800);
        charCounter.classList.toggle("char-count--danger",  len >= 2000);
    }

    draftTextarea.addEventListener("input", updateCharCount);

    // ── Spinner helpers ──────────────────────────────────────────────────────
    function showSpinner() {
        spinnerOverlay.hidden = false;
        improveBtn.disabled = true;
    }

    function hideSpinner() {
        spinnerOverlay.hidden = true;
        improveBtn.disabled = false;
    }

    // ── Toast helpers ────────────────────────────────────────────────────────
    function showError(message) {
        errorToastMsg.textContent = message;
        errorToast.hidden = false;
        // Auto-dismiss after 6 seconds
        setTimeout(dismissError, 6000);
    }

    function dismissError() {
        errorToast.hidden = true;
        errorToastMsg.textContent = "";
    }

    errorToastClose.addEventListener("click", dismissError);

    // ── Modal helpers ────────────────────────────────────────────────────────
    function openModal() {
        modal.hidden = false;
        document.body.classList.add("modal-open");
        modalCloseBtn.focus();
    }

    function closeModal() {
        modal.hidden = true;
        document.body.classList.remove("modal-open");
        resetModalEditMode();
        draftTextarea.focus();
    }

    function resetModalEditMode() {
        improvedText.hidden    = false;
        improvedEditor.hidden  = true;
        editBtn.hidden         = false;
        saveEditBtn.hidden     = true;
    }

    // ── Direction helper ─────────────────────────────────────────────────────
    function applyPanelDirection(lang) {
        const dir = lang === "ar" ? "rtl" : "ltr";
        // Panels already have dir="rtl" from HTML; update if needed
        const panels = modal.querySelectorAll(".comparison-panel");
        panels.forEach(function (panel) {
            panel.setAttribute("dir", dir);
        });
        improvedEditor.setAttribute("dir", dir);
    }

    // ── Improve API call ─────────────────────────────────────────────────────
    async function requestImprovement() {
        const draft = draftTextarea.value.trim();

        if (!draft) {
            showError("الرجاء كتابة رسالة أولاً قبل طلب التحسين.");
            return;
        }
        if (draft.length > 2000) {
            showError("الرسالة تتجاوز 2000 حرف. يرجى تقصيرها.");
            return;
        }

        showSpinner();

        try {
            const response = await fetch("/broadcast/improve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: draft }),
            });

            if (!response.ok) {
                let detail = "فشل تحسين الرسالة. حاولي مرة أخرى.";
                try {
                    const errData = await response.json();
                    if (errData && errData.detail) {
                        detail = errData.detail;
                    }
                } catch (_) { /* ignore JSON parse error */ }
                showError(detail);
                return;
            }

            const data = await response.json();

            // Validate response shape
            if (
                typeof data.original  !== "string" ||
                typeof data.improved  !== "string" ||
                typeof data.language  !== "string"
            ) {
                showError("استجابة غير متوقعة من الخادم.");
                return;
            }

            currentImproved = data.improved;
            currentLanguage = data.language;

            // Populate modal
            originalText.textContent = data.original;
            improvedText.textContent = data.improved;
            improvedEditor.value     = data.improved;

            applyPanelDirection(data.language);
            resetModalEditMode();
            openModal();

        } catch (networkError) {
            showError("خطأ في الاتصال بالخادم. تحققي من الإنترنت وأعيدي المحاولة.");
        } finally {
            hideSpinner();
        }
    }

    improveBtn.addEventListener("click", requestImprovement);

    // ── Modal close ──────────────────────────────────────────────────────────
    modalCloseBtn.addEventListener("click", closeModal);

    // Close on backdrop click
    modal.addEventListener("click", function (e) {
        if (e.target === modal) {
            closeModal();
        }
    });

    // Close on Escape key
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !modal.hidden) {
            closeModal();
        }
    });

    // ── Accept ───────────────────────────────────────────────────────────────
    acceptBtn.addEventListener("click", function () {
        // Use save-edited version if in edit mode, otherwise use AI improved
        const finalText = improvedEditor.hidden
            ? currentImproved
            : improvedEditor.value.trim() || currentImproved;

        draftTextarea.value = finalText;
        updateCharCount();
        closeModal();
    });

    // ── Edit ─────────────────────────────────────────────────────────────────
    editBtn.addEventListener("click", function () {
        improvedText.hidden   = true;
        improvedEditor.hidden = false;
        editBtn.hidden        = true;
        saveEditBtn.hidden    = false;
        improvedEditor.focus();
    });

    // ── Save edit ────────────────────────────────────────────────────────────
    saveEditBtn.addEventListener("click", function () {
        const edited = improvedEditor.value.trim();
        if (!edited) {
            showError("لا يمكن حفظ نص فارغ.");
            return;
        }
        currentImproved           = edited;
        improvedText.textContent  = edited;
        improvedText.hidden       = false;
        improvedEditor.hidden     = true;
        editBtn.hidden            = false;
        saveEditBtn.hidden        = true;
    });

    // ── Reject ───────────────────────────────────────────────────────────────
    rejectBtn.addEventListener("click", closeModal);

    // ── Broadcast form submit ─────────────────────────────────────────────────
    broadcastForm.addEventListener("submit", async function (e) {
        e.preventDefault();

        const draft = draftTextarea.value.trim();
        if (!draft) {
            showError("الرجاء كتابة رسالة قبل الإرسال.");
            return;
        }

        const segment = document.getElementById("segment-select").value;
        const submitBtn = broadcastForm.querySelector(".btn-send");
        submitBtn.disabled = true;

        try {
            const response = await fetch("/broadcast/send", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: draft, segment: segment }),
            });

            if (!response.ok) {
                let detail = "فشل إرسال الرسالة. حاولي مرة أخرى.";
                try {
                    const errData = await response.json();
                    if (errData && errData.detail) detail = errData.detail;
                } catch (_) { /* ignore */ }
                showError(detail);
            } else {
                draftTextarea.value = "";
                updateCharCount();
                showSuccessToast();
            }
        } catch (_) {
            showError("خطأ في الاتصال بالخادم.");
        } finally {
            submitBtn.disabled = false;
        }
    });

    function showSuccessToast() {
        // Reuse error toast element with success class for simplicity
        errorToast.classList.add("error-toast--success");
        errorToastMsg.textContent = "تم إرسال الرسالة بنجاح ✓";
        errorToast.hidden = false;
        setTimeout(function () {
            errorToast.hidden = false;
            errorToast.classList.remove("error-toast--success");
            dismissError();
        }, 4000);
    }

}());
```

```
### FILE: app/static/css/broadcast_improve.css
/* ============================================================
   ALYASMEEN — Broadcast Improve Feature Styles
   RTL layout throughout; Arabic-first design
   ============================================================ */

/* ── Reset / base ──────────────────────────────────────────── */
*,
*::before,
*::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    background-color: #f5f5f0;
    color: #2c2c2c;
    min-height: 100vh;
    direction: rtl;
}

/* ── Navbar ────────────────────────────────────────────────── */
.navbar {
    background-color: #2d6a4f;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.navbar-brand {
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: 0.02em;
}

.navbar-links {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
}

.navbar-links a {
    color: rgba(255, 255, 255, 0.85);
    text-decoration: none;
    font-size: 0.95rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    transition: background-color 0.2s;
}

.navbar-links a:hover,
.navbar-links a.active {
    color: #fff;
    background-color: rgba(255, 255, 255, 0.15);
}

/* ── Main container ────────────────────────────────────────── */
.main-container {
    max-width: 860px;
    margin: 2rem auto;
    padding: 0 1rem;
}

/* ── Page header ───────────────────────────────────────────── */
.page-header {
    margin-bottom: 1.5rem;
}

.page-title {
    font-size: 1.6rem;
    color: #2d6a4f;
    margin-bottom: 0.25rem;
}

.page-subtitle {
    color: #666;
    font-size: 0.95rem;
}

/* ── Broadcast card ────────────────────────────────────────── */
.broadcast-card {
    background: #fff;
    border-radius: 10px;
    padding: 1.75rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* ── Form groups ───────────────────────────────────────────── */
.form-group {
    margin-bottom: 1.25rem;
}

.form-group label {
    display: block;
    font-weight: 600;
    color: #333;
    margin-bottom: 0.4rem;
    font-size: 0.95rem;
}

.form-group select,
.form-group textarea {
    width: 100%;
    border: 1.5px solid #d0d0c8;
    border-radius: 6px;
    padding: 0.6rem 0.8rem;
    font-size: 1rem;
    font-family: inherit;
    color: #2c2c2c;
    background: #fafaf8;
    direction: inherit;
    transition: border-color 0.2s;
    resize: vertical;
}

.form-group select:focus,
.form-group textarea:focus {
    outline: none;
    border-color: #2d6a4f;
    background: #fff;
}

.form-group textarea {
    min-height: 120px;
}

/* ── Character counter ─────────────────────────────────────── */
.char-count {
    text-align: left;
    font-size: 0.82rem;
    color: #888;
    margin-top: 0.3rem;
}

.char-count--warning {
    color: #b87d00;
}

.char-count--danger {
    color: #c0392b;
    font-weight: 700;
}

/* ── Form action buttons ───────────────────────────────────── */
.form-actions {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    justify-content: flex-end;
    margin-top: 0.5rem;
}

/* ── Base button ───────────────────────────────────────────── */
.btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 6px;
    font-size: 0.95rem;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
    text-decoration: none;
    white-space: nowrap;
}

.btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
    transform: none;
}

.btn:not(:disabled):active {
    transform: scale(0.97);
}

.btn-icon {
    font-size: 1rem;
    line-height: 1;
}

.btn-improve {
    background-color: #7b5ea7;
    color: #fff;
}

.btn-improve:not(:disabled):hover {
    opacity: 0.88;
}

.btn-send {
    background-color: #2d6a4f;
    color: #fff;
}

.btn-send:not(:disabled):hover {
    opacity: 0.88;
}

/* ── Broadcast history ─────────────────────────────────────── */
.broadcast-history {
    margin-top: 2rem;
}

.broadcast-history h2 {
    font-size: 1.1rem;
    color: #2d6a4f;
    margin-bottom: 1rem;
    border-bottom: 2px solid #e8e8e0;
    padding-bottom: 0.4rem;
}

.history-item {
    background: #fff;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.history-meta {
    display: flex;
    gap: 1rem;
    font-size: 0.82rem;
    color: #888;
    margin-bottom: 0.4rem;
    flex-wrap: wrap;
}

.history-text {
    color: #333;
    font-size: 0.95rem;
    line-height: 1.6;
}

/* ── Modal backdrop ────────────────────────────────────────── */
.modal-backdrop {
    position: fixed;
    inset: 0;
    background-color: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
    overflow-y: auto;
}

.modal-backdrop[hidden] {
    display: none;
}

/* ── Modal container ───────────────────────────────────────── */
.modal-container {
    background: #fff;
    border-radius: 12px;
    width: 100%;
    max-width: 820px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
    display: flex;
    flex-direction: column;
    max-height: 90vh;
    overflow: hidden;
}

/* ── Modal header ──────────────────────────────────────────── */
.modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    border-bottom: 1.5px solid #e8e8e0;
    flex-shrink: 0;
}

.modal-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #2d6a4f;
}

.modal-close {
    background: none;
    border: none;
    font-size: 1.2rem;
    cursor: pointer;
    color: #666;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    line-height: 1;
    transition: background-color 0.2s;
}

.modal-close:hover {
    background-color: #f0f0ea;
    color: #333;
}

/* ── Modal body ────────────────────────────────────────────── */
.modal-body {
    padding: 1.25rem;
    overflow-y: auto;
    flex: 1;
}

/* ── Comparison grid ───────────────────────────────────────── */
.comparison-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
}

/* ── Comparison panels ─────────────────────────────────────── */
.comparison-panel {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    border-radius: 8px;
    overflow: hidden;
}

.comparison-panel--original {
    background-color: #f5f5f0;
    border: 1.5px solid #d8d8d0;
}

.comparison-panel--improved {
    background-color: #eef7f1;
    border: 1.5px solid #a8d5b8;
}

/* ── Panel label ───────────────────────────────────────────── */
.panel-label {
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
}

.comparison-panel--original .panel-label {
    color: #555;
    background-color: #eceae4;
}

.comparison-panel--improved .panel-label {
    color: #2d6a4f;
    background-color: #d4edda;
}

/* ── Panel text (read-only display) ───────────────────────── */
.panel-text {
    padding: 0.75rem;
    font-size: 0.97rem;
    line-height: 1.7;
    color: #2c2c2c;
    white-space: pre-wrap;
    word-break: break-word;
    min-height: 120px;
}

.comparison-panel--original .panel-text {
    color: #555;
}

.comparison-panel--improved .panel-text {
    color: #1a4731;
}

/* ── Panel editor (editable textarea) ─────────────────────── */
.panel-editor {
    width: 100%;
    min-height: 120px;
    border: none;
    border-top: 1.5px solid #a8d5b8;
    background: #fff;
    padding: 0.75rem;
    font-size: 0.97rem;
    font-family: inherit;
    line-height: 1.7;
    color: #1a4731;
    resize: vertical;
    direction: inherit;
}

.panel-editor:focus {
    outline: 2px solid #2d6a4f;
    outline-offset: -2px;
}

.panel-editor[hidden] {
    display: none;
}

/* ── Modal action buttons ──────────────────────────────────── */
.modal-actions {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    justify-content: flex-end;
    padding: 1rem 1.25rem;
    border-top: 1.5px solid #e8e8e0;
    background: #fafaf8;
    flex-shrink: 0;
}

.btn-accept {
    background-color: #2d6a4f;
    color: #fff;
}

.btn-accept:not(:disabled):hover {
    opacity: 0.88;
}

.btn-edit {
    background-color: #6c757d;
    color: #fff;
}

.btn-edit:not(:disabled):hover {
    opacity: 0.88;
}

.btn-save-edit {
    background-color: #17a2b8;
    color: #fff;
}

.btn-save-edit:not(:disabled):hover {
    opacity: 0.88;
}

.btn-reject {
    background-color: #c0392b;
    color: #fff;
}

.btn-reject:not(:disabled):hover {
    opacity: 0.88;
}

/* ── Body locked when modal open ──────────────────────────── */
body.modal-open {
    overflow: hidden;
}

/* ── Spinner overlay ───────────────────────────────────────── */
.spinner-overlay {
    position: fixed;
    inset: 0;
    background-color: rgba(255, 255, 255, 0.75);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 2000;
    gap: 1rem;
}

.spinner-overlay[hidden] {
    display: none;
}

.spinner {
    width: 48px;
    height: 48px;
    border: 5px

---

## Visual QA Result

FAIL

[FILE app/templates/broadcast.html:1] MISSING_DIR_RTL — `<html lang="ar" dir="rtl">` is present and correct for Arabic RTL layout. No violation.

[FILE app/static/css/broadcast_improve.css:1] CSS_FILE_INCOMPLETE — File is truncated at line 267 (`.spinner` rule incomplete: `border: 5px` has no closing value). The spinner animation styles are missing, and the error toast styles are not included. This will break the loading spinner visual and error toast display.

[FILE app/static/js/broadcast_improve.js:96] HARDCODED_URL — `fetch("/broadcast/improve", ...)` uses relative path `/broadcast/improve` which is correct (not a hardcoded host URL). No violation.

[FILE app/static/js/broadcast_improve.js:1] NO_INLINE_STYLES — HTML file has no `style="..."` attributes; all styles are in separate CSS file. No violation.

[FILE app/templates/broadcast.html:102] MISSING_ACCESSIBILITY_LABEL — `<input type="text">` elements are not present, but `<textarea id="improved-editor">` has `aria-label="تعديل النص المحسّن"` correctly. All interactive buttons have `aria-label` attributes in Arabic. No violation.

[FILE app/static/js/broadcast_improve.js:190] BROKEN_LOGIC — Line 190: `showSuccessToast()` function reuses the error toast element with class `.error-toast--success`, but the CSS file does not define `.error-toast--success` styles (file is truncated). Additionally, line 197 calls `dismissError()` inside the timeout instead of just hiding the toast. This is inefficient and may cause the success toast to not display properly.

[FILE app/static/css/broadcast_improve.css:267] TRUNCATED_FILE — The CSS file ends abruptly in the middle of the `.spinner` rule. The following are missing:
   - Complete `.spinner` animation rule (border/animation styles)
   - `.sr-only` utility class for screen reader text
   - `.spinner-label` styles
   - `.error-toast` and `.error-toast--success` styles
   - `.error-toast-message` and `.error-toast-close` styles
   - Mobile responsive styles (`@media (max-width: 600px)`)

[FILE app/static/js/broadcast_improve.js:169] MODAL_DIRECTION_BUG — `applyPanelDirection()` updates `.comparison-panel` elements' `dir` attribute, but both panels in the HTML already have `dir="rtl"` hardcoded. For English messages, the panels should have `dir="ltr"`, but this function correctly switches them. However, the panels' text alignment and padding directions may not flip properly without explicit CSS rules for `[dir="ltr"]` on `.comparison-panel`. This could cause misalignment for English messages.

[FILE app/templates/broadcast.html:117] MODAL_BODY_OVERFLOW — The modal body has `.modal-body { overflow-y: auto; }` but the comparison panels are inside a `.comparison-grid` with `grid-template-columns: 1fr 1fr`. On mobile (375px viewport), two equal columns will be narrower than 150px each and text will wrap excessively. No explicit mobile breakpoint forces single-column layout.

[FILE app/static/js/broadcast_improve.js:60] MISSING_MOBILE_CHECK — The improve feature does not validate viewport size or warn the aunt that the side-by-side modal may be cramped on mobile. No acceptance criteria violation, but UX issue.

[FILE app/templates/broadcast.html:1] ACCEPTANCE_CRITERIA_CHECK:
   ✅ **Improve button exists**: `<button id="improve-btn">` on line 56.
   ✅ **Side-by-side modal**: `.comparison-grid` with two `.comparison-panel` divs (original left, improved right).
   ✅ **Accept/Edit/Reject buttons**: Present (lines 130, 133, 136, 139).
   ✅ **Arabic RTL layout**: `dir="rtl"` on HTML and panels; all text in Arabic.
   ✅ **Loading spinner**: `<div id="spinner-overlay">`
