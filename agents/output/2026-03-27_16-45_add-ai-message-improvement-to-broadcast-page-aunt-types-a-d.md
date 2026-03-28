# Pipeline Output — Add AI message improvement to broadcast page: aunt types a draft message, clicks an improve button, sees her original vs AI-improved version side by side, can accept the AI version, edit it, or ignore it and send her original. AI only polishes tone and grammar, never changes meaning or adds products. Works for Arabic and English drafts.

**Generated:** 2026-03-27 16:45
**QA Status:** FAIL (after 2 retries)

---

## 1. Product Manager Brief

# PRODUCT BRIEF — AI Message Improvement for Broadcast Page

---

## 1. Summary

This feature adds an optional AI-powered message polish tool to the broadcast page, allowing the aunt to draft a broadcast message and optionally improve its tone, grammar, and clarity via Claude before sending. The feature presents original and improved versions side-by-side, lets the aunt accept, edit, or discard the AI version, and maintains the original meaning and tone intent — never adding unsolicited products or changing the core message. This reduces friction for the aunt, who may not be a native English speaker, and helps her send more professional, clear broadcasts while remaining fully in control of the message. The feature auto-detects Arabic/English and works seamlessly in both languages.

---

## 2. Affected Files

- **`app/pages/broadcast.py`** — Add UI components for draft input, improve button, side-by-side display, and version selection
- **`app/api/broadcast_routes.py`** — Add POST `/api/broadcast/improve` endpoint that calls Claude Haiku with a message improvement prompt
- **`app/services/claude_service.py`** — Add `improve_message()` method that calls Claude with constraints (tone only, no product injection, preserve meaning)
- **`app/schemas/broadcast.py`** — Add `MessageImprovementRequest` and `MessageImprovementResponse` Pydantic models
- **`tests/test_broadcast_improvement.py`** — Unit tests for Claude improvement prompt, Arabic/English detection, error handling
- **`app/data/prompts/message_improvement.md`** — System prompt for message improvement (no hallucination of products, preserve meaning)

---

## 3. User Stories

**US-11: Draft and improve a broadcast message**
As the business owner, I want to type a draft message in the broadcast page and click "Improve" to see an AI-polished version side-by-side with my original, so I can send more professional broadcasts without hiring a copywriter.

Acceptance criteria:
- Draft textarea visible on broadcast page (above the existing "Compose Message" section)
- "Improve" button is disabled until at least 10 characters are typed
- AI improvement call completes within 3 seconds
- Side-by-side display shows original on left, improved on right with clear labels
- Improved version is read-only in the display
- Works for both Arabic and English drafts

**US-12: Accept, edit, or reject the AI improvement**
As the business owner, I want to click "Use Improved Version" to copy the AI version into my message field, "Edit Improved" to manually adjust it, or simply ignore it and send my original.

Acceptance criteria:
- "Use Improved Version" button copies improved text into the draft textarea and closes the side-by-side view
- "Edit Improved" button copies improved text into the draft textarea for manual adjustment
- "Keep Original" button discards the improvement and keeps the original draft
- "Try Again" button reruns the improvement prompt (e.g., if the first attempt was poor)
- All three options preserve the user's ability to edit further before sending
- Once a version is selected, the side-by-side view closes and the textarea shows the chosen version

**US-13: AI never changes the core meaning or adds products**
As the business owner, I need to trust that the AI improvement only polishes grammar and tone, never rewrites my message to suggest products or change my intent.

Acceptance criteria:
- System prompt explicitly forbids product suggestions, product names, prices
- System prompt forbids changing the core meaning or marketing angle
- System prompt allows only tone, grammar, clarity, and formality adjustments
- If the AI attempts to add a product or change meaning, the improvement is rejected and an error message shows: "AI improvement failed — could not preserve your message intent. Please try again or send your original."
- Aunt's original draft is always preserved and never lost

**US-14: Language auto-detection**
As the business owner speaking Arabic or English, the AI should understand which language I'm drafting in and improve it in the same language.

Acceptance criteria:
- Bot detects language (Arabic/English) from the draft text
- Improvement request specifies the detected language in the Claude prompt
- Response is in the same language as the input
- If language is mixed (e.g., English with Arabic numbers), the primary language is detected
- Language detection is logged (for debugging) but not shown to the user

---

##

---

## 2. Developer Code

Looking at the QA feedback, I need to fix these blockers:

1. **Complete JavaScript file** (cut off at line 126)
2. **Register router in `app/main.py`**
3. **Import `_check_auth()` from `ui.py`** instead of re-implementing it
4. **Fix import order in `ai_service.py`** and complete `_get_client()`
5. **Add fallback/logging for missing prompt file**
6. **Add diagnostic logging to `_safety_check()`**

Let me output all affected files completely.

### FILE: app/schemas/broadcast.py
```python
from pydantic import BaseModel, Field
from typing import Optional


class MessageImprovementRequest(BaseModel):
    draft: str = Field(..., min_length=10)
    language_hint: Optional[str] = None


class MessageImprovementResponse(BaseModel):
    original: str
    improved: str
    detected_language: str
    success: bool
    error: Optional[str] = None
```

### FILE: app/data/prompts/message_improvement.md
```markdown
You are a professional message editor for a small Palestinian handmade skincare business called ALYASMEEN.

Your ONLY job is to improve the tone, grammar, clarity, and formality of the provided message draft.

STRICT RULES — violating any of these is not allowed:
1. DO NOT add, mention, suggest, or imply any products, product names, or prices that are not already in the draft.
2. DO NOT change the core meaning, intent, or marketing angle of the message.
3. DO NOT add any new offers, discounts, or promotions that are not already stated.
4. DO NOT translate the message — keep it in the same language as the input.
5. DO NOT add hashtags, emojis, or social media elements unless they already appear in the draft.
6. ONLY fix: grammar mistakes, awkward phrasing, unclear sentences, and overall tone/formality.
7. Keep the improved version approximately the same length as the original.
8. If the message is already well-written, return it with only minimal changes.

Respond with ONLY the improved message text — no explanations, no preamble, no labels.
```

### FILE: app/services/config.py
```python
import os


class Config:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "admin")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key")
    AUNT_PHONE: str = os.getenv("AUNT_PHONE", "")
    CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    WA_META_TOKEN: str = os.getenv("WA_META_TOKEN", "")
    WA_META_PHONE_ID: str = os.getenv("WA_META_PHONE_ID", "")
    WA_META_VERIFY_TOKEN: str = os.getenv("WA_META_VERIFY_TOKEN", "")
    WA_META_APP_SECRET: str = os.getenv("WA_META_APP_SECRET", "")
    USE_MOCK_WHATSAPP: bool = os.getenv("USE_MOCK_WHATSAPP", "1") == "1"
    WAVE_API_KEY: str = os.getenv("WAVE_API_KEY", "")
    WAVE_BUSINESS_ID: str = os.getenv("WAVE_BUSINESS_ID", "")
    WAVE_INCOME_ACCOUNT_ID: str = os.getenv("WAVE_INCOME_ACCOUNT_ID", "")
    AI_IMPROVEMENT_FAILED_MSG: str = os.getenv(
        "AI_IMPROVEMENT_FAILED_MSG",
        "AI improvement failed — could not preserve your message intent. Please try again or send your original."
    )
```

### FILE: app/services/ai_service.py
```python
import logging
import os
from pathlib import Path
from typing import Optional

from app.services.config import Config

logger = logging.getLogger(__name__)

_IMPROVEMENT_PROMPT_CACHE: Optional[str] = None
_IMPROVEMENT_PROMPT_PATH = Path(__file__).parent.parent / "data" / "prompts" / "message_improvement.md"


def _get_client():
    import anthropic
    return anthropic.Anthropic(api_key=Config.CLAUDE_API_KEY)


def _load_improvement_prompt() -> str:
    global _IMPROVEMENT_PROMPT_CACHE
    if _IMPROVEMENT_PROMPT_CACHE is not None:
        return _IMPROVEMENT_PROMPT_CACHE
    if not _IMPROVEMENT_PROMPT_PATH.exists():
        logger.warning(
            "message_improvement.md not found at %s — using fallback prompt",
            _IMPROVEMENT_PROMPT_PATH
        )
        _IMPROVEMENT_PROMPT_CACHE = (
            "You are a professional message editor. "
            "Improve the tone, grammar, and clarity of the message. "
            "Do NOT add products, change the core meaning, or translate."
        )
        return _IMPROVEMENT_PROMPT_CACHE
    _IMPROVEMENT_PROMPT_CACHE = _IMPROVEMENT_PROMPT_PATH.read_text(encoding="utf-8")
    return _IMPROVEMENT_PROMPT_CACHE


def _detect_language(text: str) -> str:
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    ratio = arabic_chars / max(len(text.strip()), 1)
    lang = "arabic" if ratio > 0.2 else "english"
    logger.debug("Language detection: arabic_chars=%d ratio=%.2f result=%s", arabic_chars, ratio, lang)
    return lang


def _safety_check(original: str, improved: str) -> bool:
    from app.db.database import query

    try:
        rows = query(
            "SELECT name FROM products WHERE active = true",
            []
        )
        product_names = [r["name"].lower() for r in rows if r.get("name")]
    except Exception as exc:
        logger.warning("Safety check: could not load products — skipping product injection check: %s", exc)
        product_names = []

    original_lower = original.lower()
    improved_lower = improved.lower()

    for name in product_names:
        if name not in original_lower and name in improved_lower:
            logger.warning(
                "Safety check FAILED: product '%s' injected by AI. "
                "Not present in original but found in improved version.",
                name
            )
            return False

    original_words = set(original_lower.split())
    improved_words = set(improved_lower.split())
    overlap = original_words & improved_words
    if original_words:
        overlap_ratio = len(overlap) / len(original_words)
        if overlap_ratio < 0.2:
            logger.warning(
                "Safety check FAILED: low word overlap between original and improved "
                "(ratio=%.2f). Core meaning may have changed. "
                "Original word count=%d, improved word count=%d, overlapping words=%d",
                overlap_ratio,
                len(original_words),
                len(improved_words),
                len(overlap)
            )
            return False

    return True


def get_ai_reply(phone: str, message: str, session_context: dict = None) -> str:
    from app.db.database import query

    try:
        rows = query(
            "SELECT content FROM chat_history WHERE phone = %s ORDER BY created_at DESC LIMIT 12",
            [phone]
        )
        history = [r["content"] for r in reversed(rows)]
    except Exception as exc:
        logger.error("Failed to load chat history for %s: %s", phone, exc)
        history = []

    system_parts = [
        "You are a helpful assistant for ALYASMEEN, a natural handmade skincare business in Palestine.",
        "Be friendly, concise, and helpful. Answer in the same language the customer uses.",
        "Do not invent products or prices — only mention products you know exist.",
    ]

    if session_context:
        system_parts.append(f"Current session context: {session_context}")

    try:
        knowledge_dir = Path(__file__).parent.parent / "data" / "knowledge"
        for md_file in knowledge_dir.glob("*.md"):
            system_parts.append(md_file.read_text(encoding="utf-8"))
    except Exception:
        pass

    try:
        product_rows = query("SELECT name, price, description FROM products WHERE active = true", [])
        if product_rows:
            lines = ["Available products:"]
            for p in product_rows:
                lines.append(f"- {p['name']}: {p['price']}₪ — {p.get('description', '')}")
            system_parts.append("\n".join(lines))
    except Exception as exc:
        logger.warning("Could not load products for AI context: %s", exc)

    messages = []
    for i, content in enumerate(history):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    client = _get_client()
    response = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=512,
        system="\n\n".join(system_parts),
        messages=messages,
    )
    return response.content[0].text.strip()


def improve_message(draft: str) -> dict:
    detected_language = _detect_language(draft)
    logger.info("improve_message called: detected_language=%s draft_length=%d", detected_language, len(draft))

    system_prompt = _load_improvement_prompt()
    lang_instruction = (
        "The message is in Arabic. Improve it in Arabic only."
        if detected_language == "arabic"
        else "The message is in English. Improve it in English only."
    )
    full_system = f"{system_prompt}\n\n{lang_instruction}"

    client = _get_client()
    try:
        response = client.messages.create(
            model=Config.CLAUDE_MODEL,
            max_tokens=1024,
            system=full_system,
            messages=[{"role": "user", "content": draft}],
        )
        improved = response.content[0].text.strip()
    except Exception as exc:
        logger.error("Claude API call failed in improve_message: %s", exc)
        return {
            "original": draft,
            "improved": "",
            "detected_language": detected_language,
            "success": False,
            "error": Config.AI_IMPROVEMENT_FAILED_MSG,
        }

    if not _safety_check(draft, improved):
        logger.warning("improve_message: safety check failed for draft (length=%d)", len(draft))
        return {
            "original": draft,
            "improved": "",
            "detected_language": detected_language,
            "success": False,
            "error": Config.AI_IMPROVEMENT_FAILED_MSG,
        }

    return {
        "original": draft,
        "improved": improved,
        "detected_language": detected_language,
        "success": True,
        "error": None,
    }
```

### FILE: app/routers/ui.py
```python
import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Request, Response, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.database import query, execute
from app.services.config import Config
from app.services.whatsapp_meta import send_whatsapp_message

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _hash(password: str) -> str:
    return hashlib.sha256(f"{Config.SECRET_KEY}:{password}".encode()).hexdigest()


def check_auth(request: Request) -> bool:
    token = request.cookies.get("auth")
    return token == _hash(Config.DASHBOARD_PASSWORD)


def require_auth(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(request: Request, response: Response, password: str = Form(...)):
    if password == Config.DASHBOARD_PASSWORD:
        response = RedirectResponse(url="/orders", status_code=303)
        response.set_cookie("auth", _hash(password), httponly=True, samesite="lax")
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "كلمة المرور غير صحيحة"})


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("auth")
    return response


@router.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("orders.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("products.html", {"request": request})


@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("broadcast.html", {"request": request})


@router.get("/api/orders")
async def get_orders(request: Request, status: Optional[str] = None):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    if status:
        rows = query(
            "SELECT o.*, c.name as customer_name, c.phone as customer_phone "
            "FROM orders o JOIN customers c ON o.customer_id = c.id "
            "WHERE o.status = %s ORDER BY o.created_at DESC",
            [status]
        )
    else:
        rows = query(
            "SELECT o.*, c.name as customer_name, c.phone as customer_phone "
            "FROM orders o JOIN customers c ON o.customer_id = c.id "
            "ORDER BY o.created_at DESC LIMIT 100",
            []
        )
    return JSONResponse(content=rows)


@router.get("/api/orders/{order_id}/lines")
async def get_order_lines(request: Request, order_id: int):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    rows = query(
        "SELECT ol.*, p.name as product_name FROM order_lines ol "
        "JOIN products p ON ol.product_id = p.id WHERE ol.order_id = %s",
        [order_id]
    )
    return JSONResponse(content=rows)


@router.post("/api/orders/{order_id}/status")
async def update_order_status(request: Request, order_id: int):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    new_status = body.get("status")
    if new_status not in ("to_do", "ready", "delivered", "done"):
        raise HTTPException(status_code=400, detail="Invalid status")

    rows = query(
        "SELECT o.order_ref, c.phone, c.name FROM orders o "
        "JOIN customers c ON o.customer_id = c.id WHERE o.id = %s",
        [order_id]
    )
    if not rows:
        raise HTTPException(status_code=404)

    execute(
        "UPDATE orders SET status = %s WHERE id = %s",
        [new_status, order_id]
    )

    customer = rows[0]
    status_labels = {
        "to_do": "يجب التجهيز",
        "ready": "جاهز",
        "delivered": "في الطريق",
        "done": "مكتمل",
    }
    label = status_labels.get(new_status, new_status)
    msg = f"مرحباً {customer['name']}، تم تحديث حالة طلبك {customer['order_ref']} إلى: {label}"

    try:
        send_whatsapp_message(customer["phone"], msg)
    except Exception as exc:
        logger.warning("Failed to notify customer on status update: %s", exc)

    return JSONResponse(content={"ok": True})


@router.get("/api/dashboard/stats")
async def dashboard_stats(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=401)

    totals = query(
        "SELECT status, COUNT(*) as count FROM orders GROUP BY status",
        []
    )
    monthly = query(
        "SELECT TO_CHAR(created_at, 'YYYY-MM') as month, "
        "COUNT(*) as orders, SUM(total) as revenue "
        "FROM orders GROUP BY month ORDER BY month DESC LIMIT 12",
        []
    )
    top_products = query(
        "SELECT p.name, SUM(ol.quantity) as total_qty "
        "FROM order_lines ol JOIN products p ON ol.product_id = p.id "
        "GROUP BY p.name ORDER BY total_qty DESC LIMIT 5",
        []
    )
    daily = query(
        "SELECT TO_CHAR(created_at, 'YYYY-MM-DD') as day, COUNT(*) as count "
        "FROM orders WHERE created_at >= NOW() - INTERVAL '30 days' "
        "GROUP BY day ORDER BY day",
        []
    )

    return JSONResponse(content={
        "totals": totals,
        "monthly": monthly,
        "top_products": top_products,
        "daily": daily,
    })


@router.get("/api/products")
async def list_products(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    rows = query("SELECT * FROM products ORDER BY created_at DESC", [])
    return JSONResponse(content=rows)


@router.post("/api/products")
async def create_product(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    row = execute(
        "INSERT INTO products (name, price, description, tags, active) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING *",
        [body["name"], body["price"], body.get("description", ""), body.get("tags", ""), True]
    )
    return JSONResponse(content=row)


@router.post("/api/products/{product_id}")
async def update_product(request: Request, product_id: int):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    execute(
        "UPDATE products SET name = %s, price = %s, description = %s, tags = %s WHERE id = %s",
        [body["name"], body["price"], body.get("description", ""), body.get("tags", ""), product_id]
    )
    return JSONResponse(content={"ok": True})


@router.post("/api/products/{product_id}/toggle")
async def toggle_product(request: Request, product_id: int):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    execute(
        "UPDATE products SET active = NOT active WHERE id = %s",
        [product_id]
    )
    return JSONResponse(content={"ok": True})


@router.post("/api/products/{product_id}/delete")
async def delete_product(request: Request, product_id: int):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    execute("DELETE FROM products WHERE id = %s", [product_id])
    return JSONResponse(content={"ok": True})
```

### FILE: app/routers/broadcast.py
```python
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from app.db.database import query
from app.routers.ui import check_auth
from app.schemas.broadcast import MessageImprovementRequest, MessageImprovementResponse
from app.services.ai_service import improve_message
from app.services.config import Config
from app.services.whatsapp_meta import send_whatsapp_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/broadcast/recipients")
async def get_recipients(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=401)
    rows = query(
        "SELECT id, name, phone FROM customers ORDER BY name ASC",
        []
    )
    return JSONResponse(content=rows)


@router.post("/api/broadcast/improve")
async def improve_broadcast_message(request: Request, body: MessageImprovementRequest):
    if not check_auth(request):
        raise HTTPException(status_code=401)

    logger.info("improve_broadcast_message: draft_length=%d", len(body.draft))

    result = improve_message(body.draft)

    return JSONResponse(content=MessageImprovementResponse(**result).dict())


@router.post("/api/broadcast/send")
async def send_broadcast(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=401)

    body = await request.json()
    message = body.get("message", "").strip()
    recipient_ids = body.get("recipient_ids", [])

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if not recipient_ids:
        raise HTTPException(status_code=400, detail="At least one recipient required")

    placeholders = ", ".join(["%s"] * len(recipient_ids))
    customers = query(
        f"SELECT id, name, phone FROM customers WHERE id IN ({placeholders})",
        recipient_ids
    )

    sent = 0
    failed = 0
    for customer in customers:
        try:
            send_whatsapp_message(customer["phone"], message)
            sent += 1
        except Exception as exc:
            logger.error("Broadcast send failed for %s: %s", customer["phone"], exc)
            failed += 1

    logger.info("Broadcast complete: sent=%d failed=%d", sent, failed)
    return JSONResponse(content={"sent": sent, "failed": failed})
```

### FILE: app/templates/broadcast.html
```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>البث — ALYASMEEN</title>
  <link rel="stylesheet" href="/static/css/broadcast.css" />
</head>
<body>
  <nav class="navbar">
    <div class="nav-brand">🌿 ALYASMEEN</div>
    <div class="nav-links">
      <a href="/orders">الطلبات</a>
      <a href="/dashboard">الإحصائيات</a>
      <a href="/products">المنتجات</a>
      <a href="/broadcast" class="active">البث</a>
      <a href="/logout">خروج</a>
    </div>
  </nav>

  <main class="container">
    <h1 class="page-title">📢 البث الجماعي</h1>

    <!-- Draft & Improve Section -->
    <section class="card" id="compose-section">
      <h2>✍️ صياغة الرسالة</h2>

      <label for="draft-textarea" class="field-label">اكتب رسالتك هنا</label>
      <textarea
        id="draft-textarea"
        class="message-textarea"
        placeholder="اكتب رسالتك هنا... (على الأقل ١٠ أحرف)"
        rows="5"
      ></textarea>

      <div class="draft-actions">
        <button id="improve-btn" class="btn btn-secondary" disabled>
          ✨ تحسين بالذكاء الاصطناعي
        </button>
        <span id="improve-status" class="status-text"></span>
      </div>

      <!-- Side-by-side comparison -->
      <div id="comparison-panel" class="comparison-panel hidden">
        <div class="comparison-grid">
          <div class="comparison-col">
            <div class="comparison-label original-label">📝 النص الأصلي</div>
            <div id="original-display" class="comparison-text"></div>
          </div>
          <div class="comparison-col">
            <div class="comparison-label improved-label">✨ النص المحسّن</div>
            <div id="improved-display" class="comparison-text improved-text"></div>
          </div>
        </div>

        <div class="comparison-actions">
          <button id="use-improved-btn" class="btn btn-primary">✅ استخدام النص المحسّن</button>
          <button id="edit-improved-btn" class="btn btn-secondary">✏️ تعديل النص المحسّن</button>
          <button id="keep-original-btn" class="btn btn-ghost">↩️ الاحتفاظ بالأصل</button>
          <button id="try-again-btn" class="btn btn-ghost">🔄 إعادة المحاولة</button>
        </div>
      </div>

      <div id="improve-error" class="error-message hidden"></div>
    </section>

    <!-- Recipients Section -->
    <section class="card" id="recipients-section">
      <h2>👥 المستلمون</h2>
      <div class="recipients-toolbar">
        <button id="select-all-btn" class="btn btn-ghost btn-sm">تحديد الكل</button>
        <button id="deselect-all-btn" class="btn btn-ghost btn-sm">إلغاء التحديد</button>
        <span id="selected-count" class="selected-count">٠ محدد</span>
      </div>
      <div id="recipients-list" class="recipients-list">
        <div class="loading-text">جاري تحميل جهات الاتصال...</div>
      </div>
    </section>

    <!-- Send Section -->
    <section class="card" id="send-section">
      <button id="send-btn" class="btn btn-primary btn-large" disabled>
        📤 إرسال البث
      </button>
      <div id="send-result" class="send-result hidden"></div>
    </section>
  </main>

  <script src="/static/js/broadcast.js"></script>
</body>
</html>
```

### FILE: app/static/css/broadcast.css
```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
  background: #f5f5f0;
  color: #2d2d2d;
  direction: rtl;
}

.navbar {
  background: #2d5a3d;
  color: #fff;
  padding: 0.75rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-brand { font-size: 1.2rem; font-weight: 700; }

.nav-links { display: flex; gap: 1.25rem; }
.nav-links a { color: rgba(255,255,255,0.85); text-decoration: none; font-size: 0.95rem; }
.nav-links a:hover, .nav-links a.active { color: #fff; font-weight: 600; }

.container { max-width: 900px; margin: 2rem auto; padding: 0 1rem; }

.page-title { font-size: 1.6rem; font-weight: 700; margin-bottom: 1.5rem; color: #2d5a3d; }

.card {
  background: #fff;
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.card h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #333; }

.field-label { display: block; font-size: 0.9rem; color: #555; margin-bottom: 0.4rem; }

.message-textarea {
  width: 100%;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 0.75rem;
  font-size: 1rem;
  font-family: inherit;
  resize: vertical;
  direction: rtl;
  transition: border-color 0.2s;
}
.message-textarea:focus { outline: none; border-color: #2d5a3d; }

.draft-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 0.75rem;
}

.status-text { font-size: 0.85rem; color: #888; }

/* Buttons */
.btn {
  padding: 0.55rem 1.2rem;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.95rem;
  font-family: inherit;
  font-weight: 500;
  transition: background 0.2s, opacity 0.2s;
}
.btn:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-primary { background: #2d5a3d; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #234a32; }

.btn-secondary { background: #e8f5e9; color: #2d5a3d; border: 1px solid #b2dfdb; }
.btn-secondary:hover:not(:disabled) { background: #c8e6c9; }

.btn-ghost { background: transparent; color: #666; border: 1px solid #ddd; }
.btn-ghost:hover:not(:disabled) { background: #f5f5f5; }

.btn-sm { padding: 0.35rem 0.8rem; font-size: 0.85rem; }

.btn-large { width: 100%; padding: 0.9rem; font-size: 1.1rem; }

/* Comparison panel */
.comparison-panel { margin-

---

## 3. QA Result

FAIL

[FILE app/static/css/broadcast.css:98] INCOMPLETE_FILE — CSS file cuts off mid-rule at line 98; missing closing braces and remaining styles

[FILE app/static/js/broadcast.js:MISSING] MISSING_FILE — JavaScript file referenced in broadcast.html but not provided; required for interactivity

[FILE app/main.py:MISSING_REGISTRATION] ROUTER_NOT_REGISTERED — broadcast router not registered in app.main:app; `app.include_router(broadcast_router)` missing

[FILE app/routers/broadcast.py:7] IMPORT_VIOLATION — importing `check_auth` from `ui.py` is correct, but the function signature and logic must match exactly; verify they are identical

[FILE app/services/ai_service.py:18] INCOMPLETE_FUNCTION — `_get_client()` function body incomplete; missing full anthropic import and client instantiation logic

[FILE app/data/prompts/message_improvement.md:MISSING] FILE_MISSING — prompt file not created at `app/data/prompts/message_improvement.md`; required for fallback detection

[FILE app/schemas/broadcast.py:1] PYDANTIC_MODEL_LOCATION — schemas should live in `app/api/` not root `app/`; move to `app/api/schemas/broadcast.py` for consistency

[FILE app/routers/broadcast.py:25] ROUTE_PATH_MISMATCH — endpoint `/api/broadcast/improve` but no corresponding schema validation in the route handler; `body` parameter lacks type annotation `body: MessageImprovementRequest`

[FILE app/templates/broadcast.html:98] INCOMPLETE_HTML — HTML file cuts off mid-structure; missing closing `</div>` and `</body>` tags

**Summary:** Developer code is incomplete across 6 files (CSS, JS missing entirely, HTML truncated, Python functions cut off). Router not wired into FastAPI app. Multiple file organization and import issues. Cannot QA incomplete code — request full, working versions of all affected files before resubmission.

---

## 4. Test Code

Looking at the approved backend code, I need to write tests covering:
- `/api/broadcast/improve` endpoint (happy path, auth, validation, Claude failure, safety check failure)
- `/api/broadcast/send` endpoint (happy path, missing message, missing recipients, auth)
- `improve_message()` service (language detection, safety check, Claude failure)
- `_detect_language()` and `_safety_check()` helpers

I'll split into two files to stay under 150 lines each.

```
### FILE: tests/test_broadcast_improve_endpoint.py

import pytest
import hashlib
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.config import Config


def _auth_cookie() -> dict:
    token = hashlib.sha256(
        f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}".encode()
    ).hexdigest()
    return {"auth": token}


# ---------------------------------------------------------------------------
# POST /api/broadcast/improve
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_improve_returns_improved_text_for_english_draft():
    mock_result = {
        "original": "hello this is a message",
        "improved": "Hello, this is a polished message.",
        "detected_language": "english",
        "success": True,
        "error": None,
    }
    with patch("app.routers.broadcast.improve_message", return_value=mock_result):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/broadcast/improve",
                json={"draft": "hello this is a message"},
                cookies=_auth_cookie(),
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["improved"] == "Hello, this is a polished message."
    assert data["detected_language"] == "english"
    assert data["error"] is None


@pytest.mark.asyncio
async def test_improve_returns_improved_text_for_arabic_draft():
    mock_result = {
        "original": "مرحبا كيف حالك اليوم",
        "improved": "مرحباً، كيف حالك اليوم؟",
        "detected_language": "arabic",
        "success": True,
        "error": None,
    }
    with patch("app.routers.broadcast.improve_message", return_value=mock_result):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/broadcast/improve",
                json={"draft": "مرحبا كيف حالك اليوم"},
                cookies=_auth_cookie(),
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected_language"] == "arabic"
    assert data["success"] is True


@pytest.mark.asyncio
async def test_improve_returns_422_when_draft_is_too_short():
    """Draft shorter than 10 chars should be rejected by Pydantic schema."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/broadcast/improve",
            json={"draft": "hi"},
            cookies=_auth_cookie(),
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_improve_returns_422_when_draft_is_missing():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/broadcast/improve",
            json={},
            cookies=_auth_cookie(),
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_improve_returns_401_when_unauthenticated():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/broadcast/improve",
            json={"draft": "hello this is a message"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_improve_returns_success_false_when_claude_fails():
    mock_result = {
        "original": "hello this is a message",
        "improved": "",
        "detected_language": "english",
        "success": False,
        "error": Config.AI_IMPROVEMENT_FAILED_MSG,
    }
    with patch("app.routers.broadcast.improve_message", return_value=mock_result):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/broadcast/improve",
                json={"draft": "hello this is a message"},
                cookies=_auth_cookie(),
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == Config.AI_IMPROVEMENT_FAILED_MSG
    assert data["improved"] == ""


# ---------------------------------------------------------------------------
# POST /api/broadcast/send
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_broadcast_delivers_to_all_recipients():
    mock_customers = [
        {"id": 1, "name": "Rania", "phone": "970591000001"},
        {"id": 2, "name": "Hana", "phone": "970591000002"},
    ]
    with (
        patch("app.routers.broadcast.query", return_value=mock_customers),
        patch("app.routers.broadcast.send_whatsapp_message") as mock_send,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/broadcast/send",
                json={"message": "Sale today!", "recipient_ids": [1, 2]},
                cookies=_auth_cookie(),
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 2
    assert data["failed"] == 0
    assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_send_broadcast_returns_400_when_message_is_empty():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/broadcast/send",
            json={"message": "", "recipient_ids": [1]},
            cookies=_auth_cookie(),
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_broadcast_returns_400_when_recipients_list_is_empty():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/broadcast/send",
            json={"message": "Hello everyone!", "recipient_ids": []},
            cookies=_auth_cookie(),
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_broadcast_returns_401_when_unauthenticated():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/broadcast/send",
            json={"message": "Hello!", "recipient_ids": [1]},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_send_broadcast_counts_failed_when_whatsapp_raises():
    mock_customers = [
        {"id": 1, "name": "Rania", "phone": "970591000001"},
        {"id": 2, "name": "Hana", "phone": "970591000002"},
    ]
    with (
        patch("app.routers.broadcast.query", return_value=mock_customers),
        patch(
            "app.routers.broadcast.send_whatsapp_message",
            side_effect=Exception("Meta API down"),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/broadcast/send",
                json={"message": "Sale today!", "recipient_ids": [1, 2]},
                cookies=_auth_cookie(),
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 0
    assert data["failed"] == 2
```

```
### FILE: tests/test_broadcast_improve_service.py

import pytest
from unittest.mock import patch, MagicMock

from app.services.ai_service import (
    _detect_language,
    _safety_check,
    improve_message,
)
from app.services.config import Config


# ---------------------------------------------------------------------------
# _detect_language
# ---------------------------------------------------------------------------

def test_detect_language_returns_english_for_latin_text():
    assert _detect_language("Hello, how are you today?") == "english"


def test_detect_language_returns_arabic_for_arabic_text():
    assert _detect_language("مرحبا كيف حالك اليوم في هذا اليوم الجميل") == "arabic"


def test_detect_language_returns_english_for_mixed_text_with_low_arabic_ratio():
    # Arabic numerals mixed with mostly English
    assert _detect_language("Order 3 items for 50 shekels today") == "english"


def test_detect_language_returns_arabic_when_arabic_ratio_exceeds_threshold():
    # >20 % Arabic chars
    arabic_heavy = "مرحبا hello كيف today حالك"
    result = _detect_language(arabic_heavy)
    assert result == "arabic"


# ---------------------------------------------------------------------------
# _safety_check
# ---------------------------------------------------------------------------

def test_safety_check_passes_when_no_products_injected():
    with patch("app.services.ai_service.query", return_value=[{"name": "Rose Cream"}]):
        result = _safety_check(
            "We have a great deal for you today",
            "We have a wonderful deal for you today",
        )
    assert result is True


def test_safety_check_fails_when_ai_injects_product_not_in_original():
    with patch("app.services.ai_service.query", return_value=[{"name": "rose cream"}]):
        result = _safety_check(
            "We have a great deal today",
            "We have a great deal today — try our rose cream!",
        )
    assert result is False


def test_safety_check_fails_when_word_overlap_is_too_low():
    with patch("app.services.ai_service.query", return_value=[]):
        result = _safety_check(
            "Short sale today only",
            "Completely different unrelated sentences about nothing whatsoever here and beyond",
        )
    assert result is False


def test_safety_check_passes_when_product_appears_in_both_original_and_improved():
    with patch("app.services.ai_service.query", return_value=[{"name": "rose cream"}]):
        result = _safety_check(
            "Buy our rose cream now",
            "Purchase our rose cream today for a great experience",
        )
    assert result is True


def test_safety_check_passes_when_product_query_fails():
    """If DB is unreachable, product check is skipped and only overlap is checked."""
    with patch(
        "app.services.ai_service.query",
        side_effect=Exception("DB connection failed"),
    ):
        result = _safety_check(
            "Great deals today for you",
            "Wonderful deals today for you",
        )
    assert result is True


# ---------------------------------------------------------------------------
# improve_message (full service integration with Claude mocked)
# ---------------------------------------------------------------------------

def _make_claude_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_improve_message_returns_success_true_for_valid_english_draft():
    improved_text = "Hello, this is a polished message for our valued customers."
    draft = "hello this is a message for our customers"

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_claude_response(improved_text)

    with (
        patch("app.services.ai_service._get_client", return_value=mock_client),
        patch("app.services.ai_service.query", return_value=[]),
    ):
        result = improve_message(draft)

    assert result["success"] is True
    assert result["improved"] == improved_text
    assert result["original"] == draft
    assert result["detected_language"] == "english"
    assert result["error"] is None


def test_improve_message_returns_success_true_for_arabic_draft():
    draft = "مرحبا نحن نقدم عروض رائعة لكم اليوم"
    improved_text = "مرحباً، نقدم لكم عروضاً رائعة اليوم."

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_claude_response(improved_text)

    with (
        patch("app.services.ai_service._get_client", return_value=mock_client),
        patch("app.services.ai_service.query", return_value=[]),
    ):
        result = improve_message(draft)

    assert result["success"] is True
    assert result["detected_language"] == "arabic"


def test_improve_message_returns_success_false_when_claude_api_raises():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Connection timeout")

    with patch("app.services.ai_service._get_client", return_value=mock_client):
        result = improve_message("hello this is a test message for the store")

    assert result["success"] is False
    assert result["improved"] == ""
    assert result["error"] == Config.AI_IMPROVEMENT_FAILED_MSG


def test_improve_message_returns_success_false_when_safety_check_fails():
    draft = "Sale today for all customers"
    injected = "Sale today — try our Jasmine Serum and Rose Cream for all customers!"

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_claude_response(injected)

    with (
        patch("app.services.ai_service._get_client", return_value=mock_client),
        patch(
            "app.services.ai_service.query",
            return_value=[{"name": "jasmine serum"}, {"name": "rose cream"}],
        ),
    ):
        result = improve_message(draft)

    assert result["success"] is False
    assert result["error"] == Config.AI_IMPROVEMENT_FAILED_MSG


def test_improve_message_uses_fallback_prompt_when_file_missing(tmp_path):
    """_load_improvement_prompt should fall back gracefully if .md file absent."""
    import app.services.ai_service as svc

    # Reset cache so the missing-file path is exercised
    svc._IMPROVEMENT_PROMPT_CACHE = None
    original_path = svc._IMPROVEMENT_PROMPT_PATH
    svc._IMPROVEMENT_PROMPT_PATH = tmp_path / "nonexistent.md"

    draft = "hello this is a test message for the store"
    improved_text = "Hello, this is a

---

## 5. DevOps Checklist

# Deployment Checklist

## Issues Detected

Your approved code has **critical blockers** that must be resolved **before deployment**:

1. **`app/static/js/broadcast.js` is incomplete** — cut off mid-file
2. **`app/static/css/broadcast.css` is incomplete** — cut off mid-line
3. **Broadcast router NOT registered in `app/main.py`**
4. **Import cycle risk:** `broadcast.py` imports `check_auth` from `ui.py`, but `ui.py` must define it before broadcast is loaded

### ACTION REQUIRED — Do Not Deploy Yet

**You must:**
1. Complete and submit the full `broadcast.js` and `broadcast.css` files
2. Add broadcast router registration to `app/main.py`
3. Verify no circular imports
4. Re-run QA tests on the complete code

---

## Deployment Checklist (Assuming Code Is Complete)

### 1. requirements.txt
**Yes** — Add anthropic if not already present:
```
anthropic>=0.25.0
```
(Already in your requirements.txt — ✅ no changes needed)

---

### 2. Database Migration
**No** — No new tables, columns, or indices needed. The `products` table already exists from previous deployment.
- No migration needed

---

### 3. .env.example
**Yes** — Add new environment variables:
```
CLAUDE_API_KEY=your_anthropic_api_key_here
CLAUDE_MODEL=claude-haiku-4-5-20251001
AI_IMPROVEMENT_FAILED_MSG=AI improvement failed — could not preserve your message intent. Please try again or send your original.
```

---

### 4. Procfile
**No** — Existing uvicorn command is correct:
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
No changes needed.

---

### 5. Railway / Render
**Yes** — Platform configuration steps:

1. **Add environment variables in dashboard:**
   - `CLAUDE_API_KEY` = (get from Anthropic console)
   - `CLAUDE_MODEL` = `claude-haiku-4-5-20251001`
   - `AI_IMPROVEMENT_FAILED_MSG` = (copy from .env.example)

2. **Verify build command:** (should auto-detect from Procfile)
   ```
   pip install -r requirements.txt
   ```

3. **Health check path:** (optional, but recommended)
   - Path: `/`
   - Expected: 200 OK (FastAPI root responds with message)

4. **Redeploy after adding env vars:**
   - Trigger a new deployment (push to main branch, or manual redeploy in platform UI)

---

### 6. Meta WhatsApp
**No** — No new webhook events or subscriptions needed.
- Existing webhook URL remains valid
- No changes needed

---

### 7. Supabase
**No** — No new RLS policies, RPC functions, or RLS changes needed.
- Existing `products` table is used by the new broadcast feature
- `customers` table (existing) is queried for broadcast recipients
- No migration needed

---

## Pre-Deployment Checklist

- [ ] **BLOCKER:** Complete and test `broadcast.js` (currently cut off at line 126)
- [ ] **BLOCKER:** Complete and test `broadcast.css` (currently cut off mid-line)
- [ ] **BLOCKER:** Register broadcast router in `app/main.py`:
  ```python
  from app.routers import broadcast
  app.include_router(broadcast.router)
  ```
- [ ] Run full QA suite on complete code
- [ ] Test broadcast feature locally with mock WhatsApp
- [ ] Add `CLAUDE_API_KEY` to `.env` locally and verify `improve_message()` works
- [ ] Test all dashboard pages load and respond to auth
- [ ] Verify no import errors by running:
  ```bash
  python -c "from app.main import app; print('✓ Imports OK')"
  ```

---

## Deployment Sequence (After Blockers Fixed)

1. Push complete code to GitHub
2. Add env vars to Railway/Render dashboard
