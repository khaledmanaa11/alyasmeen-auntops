# Pipeline Output — Add AI message improvement to broadcast page: aunt types a draft message, clicks an improve button, sees her original vs AI-improved version side by side, can accept the AI version, edit it, or ignore it and send her original. AI only polishes tone and grammar, never changes meaning or adds products. Works for Arabic and English drafts.

**Generated:** 2026-03-27 16:28
**QA Status:** FAIL (after 2 retries)

---

## 1. Product Manager Brief

# Product Brief: AI Message Polish for Broadcast Page

---

## 1. Summary

This feature adds an optional AI-powered message refinement tool to the broadcast page, allowing the aunt to draft a promotional or announcement message and receive a polished version that improves tone, grammar, and readability without altering the core meaning or introducing products. The side-by-side comparison interface (original vs. improved) gives the aunt full control—she can accept the suggestion, manually edit it, or discard it and send her original draft. This maintains the aunt's voice and brand while reducing friction for non-native English speakers or Arabic typos. The feature auto-detects the draft language and processes it accordingly, with graceful fallback if the Claude API is unavailable.

---

## 2. Affected Files

- `app/pages/broadcast.py` — add "Improve with AI" button and modal UI; call new `/api/improve-message` endpoint
- `app/api/messages.py` (create new) — POST `/api/improve-message` endpoint; language detection, Claude call, response parsing
- `app/utils/ai_utils.py` — extract Claude Haiku calls into shared function (reuse from bot conversation logic)
- `app/data/prompts/message_improvement.txt` (create new) — system prompt for message polishing (Arabic + English instructions)
- `requirements.txt` — no new dependencies (uses existing `anthropic` and `langdetect`)
- `tests/test_api_messages.py` (create new) — unit tests for `/api/improve-message` (happy path, degraded Claude, language detection, meaning preservation)
- `tests/test_broadcast_ui.py` (create new) — integration tests for broadcast page UI (improvement button interaction, side-by-side display, accept/edit/discard flows)

---

## 3. User Stories

**US-11: Draft and improve announcement**
As the aunt, I want to draft a WhatsApp message (e.g., a seasonal promotion or store hours update), click "Improve with AI", and see a polished version side by side with my original, so I can send a more professional message without rewriting it myself.

Acceptance criteria:
- Broadcast page has an "Improve with AI" button below the draft text area
- Clicking the button sends the draft to the AI service
- Modal appears showing original and improved versions in two columns
- Improvement only touches grammar, tone, and phrasing—not meaning or product names
- Modal has three action buttons: "Use this version", "Edit", "Discard"

**US-12: Edit suggested improvement**
As the aunt, I want to click "Edit" in the improvement modal and tweak the AI version before sending it.

Acceptance criteria:
- "Edit" button opens the improved text in an editable field within the modal
- Aunt can modify the text and save the edited version
- Modified version becomes the active draft (replacing the original)
- "Send" button then sends the edited version

**US-13: Multilingual message polish**
As the aunt, I want to draft a message in Arabic or English and have the improvement work in my language.

Acceptance criteria:
- AI detects the draft language automatically
- Improvement is returned in the same language
- No language switching or code-mixing in the improved version

**US-14: Graceful fallback if AI is unavailable**
As the aunt, I want the improvement feature to not break the broadcast flow if Claude is down or `CLAUDE_API_KEY` is missing.

Acceptance criteria:
- If Claude API fails, an error toast appears: "Could not improve message. Check your connection or try again later."
- "Improve with AI" button remains clickable (aunt can retry)
- Aunt can still proceed to send her original draft without improvement
- No crash or blank page

---

## 4. Acceptance Criteria

1. **UI Button and Modal Layout**
   - Broadcast page has an "Improve with AI" button positioned below the draft text area (right-aligned, secondary button style)
   - Button is disabled if the draft text is empty or whitespace-only
   - Clicking it shows a loading spinner for 2–3 seconds (typical Claude response time)
   - Modal title: "Review AI Improvement" (English) / "راجع التحسين من الذكاء الاصطناعي" (Arabic)

2. **Side-by-Side Comparison**
   - Modal displays two columns:

---

## 2. Developer Code

Looking at the QA feedback, I need to fix:

1. Move Claude calls entirely into `ai_service.py` - no direct Anthropic imports in router
2. Move `_detect_language()` to `ai_service.py`
3. Complete `improve_message_draft()` implementation
4. Complete the `broadcast.html` template with all JS/modal logic
5. Add missing `/api/broadcast/send` endpoint
6. Create both test files
7. Ensure router is clean and properly registered

Let me build all files completely.

```
### FILE: app/services/ai_service.py
import json
import os
import glob
from anthropic import Anthropic
from app.services.config import Config
from app.db.database import query, execute

client = Anthropic(api_key=Config.CLAUDE_API_KEY)


def _load_knowledge() -> str:
    """Load all .md files from knowledge directory."""
    knowledge_dir = os.path.join(os.path.dirname(__file__), "../data/knowledge")
    knowledge_parts = []
    if os.path.isdir(knowledge_dir):
        for filepath in glob.glob(os.path.join(knowledge_dir, "*.md")):
            with open(filepath, "r", encoding="utf-8") as f:
                knowledge_parts.append(f.read())
    return "\n\n".join(knowledge_parts)


def _load_products_context() -> str:
    """Load active products from Supabase products table."""
    try:
        rows = query(
            "SELECT name, price, description, tags FROM products WHERE active = %s ORDER BY name",
            [True],
        )
        if not rows:
            return "No products currently available."
        lines = ["Available products:"]
        for r in rows:
            line = f"- {r['name']}: {r['price']}₪"
            if r.get("description"):
                line += f" — {r['description']}"
            if r.get("tags"):
                line += f" [tags: {r['tags']}]"
            lines.append(line)
        return "\n".join(lines)
    except Exception:
        return "Products temporarily unavailable."


def _load_improvement_prompt() -> str:
    """Load the message improvement system prompt from file."""
    prompt_path = os.path.join(
        os.path.dirname(__file__), "../data/prompts/message_improvement.txt"
    )
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        # Fallback inline prompt if file is missing
        return (
            "You are a professional message editor for a small Palestinian handmade skincare business called ALYASMEEN. "
            "Your job is to polish WhatsApp broadcast messages written by the business owner. "
            "Rules:\n"
            "1. Preserve the original language exactly — if Arabic, respond in Arabic; if English, respond in English.\n"
            "2. Do NOT change the meaning, add products, add offers, or invent information.\n"
            "3. Fix grammar, spelling, and punctuation.\n"
            "4. Improve tone to be warm, professional, and friendly — matching a small business voice.\n"
            "5. Keep the message concise — do not pad or expand unnecessarily.\n"
            "6. Return ONLY the improved message text. No explanations, no commentary, no labels.\n"
            "7. Preserve any emojis, bullet points, or formatting structure from the original.\n"
            "8. Never switch languages mid-message."
        )


def detect_language(text: str) -> str:
    """
    Detect whether text is primarily Arabic or English.
    Returns 'ar' for Arabic, 'en' for English.
    """
    try:
        from langdetect import detect
        lang = detect(text)
        return "ar" if lang == "ar" else "en"
    except Exception:
        # Fallback: count Arabic unicode characters
        arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
        return "ar" if arabic_chars > len(text) * 0.2 else "en"


def improve_message_draft(draft: str) -> dict:
    """
    Polish a broadcast message draft using Claude Haiku.

    Args:
        draft: The original message text (Arabic or English)

    Returns:
        dict with keys:
            - improved (str): The polished message
            - language (str): Detected language ('ar' or 'en')
            - original (str): Echo of the original draft

    Raises:
        RuntimeError: If Claude API call fails (caller should catch and return 503)
    """
    if not Config.CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY is not configured")

    language = detect_language(draft)
    system_prompt = _load_improvement_prompt()

    # Build user message with language hint
    if language == "ar":
        user_message = (
            f"يرجى تحسين رسالة واتساب التالية باللغة العربية فقط:\n\n{draft}"
        )
    else:
        user_message = (
            f"Please improve the following WhatsApp message in English only:\n\n{draft}"
        )

    response = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    improved_text = response.content[0].text.strip()

    return {
        "improved": improved_text,
        "language": language,
        "original": draft,
    }


def get_ai_reply(phone: str, user_message: str, products_context: str = "") -> str:
    """Get AI reply for a customer WhatsApp message."""
    # Load conversation history (last 6 turns)
    history_rows = query(
        "SELECT role, content FROM chat_history WHERE phone = %s ORDER BY created_at DESC LIMIT 12",
        [phone],
    )
    history = list(reversed(history_rows))

    # Build messages list
    messages = []
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    # Build system prompt
    knowledge = _load_knowledge()
    if not products_context:
        products_context = _load_products_context()

    system_parts = [
        "You are a helpful WhatsApp assistant for ALYASMEEN, a Palestinian handmade skincare business.",
        "Be warm, friendly, and concise. Reply in the same language the customer uses.",
        "Never invent products or prices — only reference what is listed below.",
        "",
        products_context,
    ]
    if knowledge:
        system_parts.append("")
        system_parts.append(knowledge)

    system_prompt = "\n".join(system_parts)

    response = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=512,
        system=system_prompt,
        messages=messages,
    )

    reply = response.content[0].text.strip()

    # Save to chat history
    execute(
        "INSERT INTO chat_history (phone, role, content) VALUES (%s, %s, %s)",
        [phone, "user", user_message],
    )
    execute(
        "INSERT INTO chat_history (phone, role, content) VALUES (%s, %s, %s)",
        [phone, "assistant", reply],
    )

    return reply
```

```
### FILE: app/routers/messages.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ai_service import improve_message_draft

router = APIRouter()


class ImproveRequest(BaseModel):
    draft: str


class ImproveResponse(BaseModel):
    improved: str
    language: str
    original: str


@router.post("/api/improve-message", response_model=ImproveResponse)
async def improve_message(payload: ImproveRequest):
    """
    Polish a broadcast message draft using Claude Haiku.

    - Detects language (Arabic or English) automatically
    - Returns improved version in the same language
    - Raises 400 if draft is empty
    - Raises 503 if Claude API is unavailable
    """
    draft = payload.draft.strip()
    if not draft:
        raise HTTPException(status_code=400, detail="Draft message cannot be empty.")

    try:
        result = improve_message_draft(draft)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        # Catch Anthropic API errors, network errors, etc.
        raise HTTPException(
            status_code=503,
            detail="Could not improve message. Check your connection or try again later.",
        ) from exc

    return ImproveResponse(
        improved=result["improved"],
        language=result["language"],
        original=result["original"],
    )
```

```
### FILE: app/routers/ui.py
import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.database import execute, execute_returning, query
from app.services.config import Config
from app.services.whatsapp_meta import send_whatsapp_message

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── Auth helpers ────────────────────────────────────────────────────────────

def _make_token() -> str:
    raw = f"{Config.SECRET_KEY}:{Config.DASHBOARD_PASSWORD}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _is_auth(session: str | None) -> bool:
    return bool(session and session == _make_token())


def _auth_required(session: str | None):
    if not _is_auth(session):
        raise HTTPException(status_code=302, headers={"Location": "/login"})


# ── Auth routes ──────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(password: str = Form(...)):
    if password == Config.DASHBOARD_PASSWORD:
        token = _make_token()
        response = RedirectResponse(url="/orders", status_code=302)
        response.set_cookie("session", token, httponly=True, max_age=86400 * 7)
        return response
    return RedirectResponse(url="/login?error=1", status_code=302)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


# ── Dashboard pages ──────────────────────────────────────────────────────────

@router.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, session: str | None = Cookie(default=None)):
    _auth_required(session)
    return templates.TemplateResponse("orders.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, session: str | None = Cookie(default=None)):
    _auth_required(session)
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/products", response_class=HTMLResponse)
async def products_page(request: Request, session: str | None = Cookie(default=None)):
    _auth_required(session)
    return templates.TemplateResponse("products.html", {"request": request})


@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request, session: str | None = Cookie(default=None)):
    _auth_required(session)
    return templates.TemplateResponse("broadcast.html", {"request": request})


# ── Orders API ───────────────────────────────────────────────────────────────

@router.get("/api/orders")
async def api_orders(status: str = "", session: str | None = Cookie(default=None)):
    _auth_required(session)
    if status:
        rows = query(
            "SELECT * FROM orders WHERE status = %s ORDER BY created_at DESC",
            [status],
        )
    else:
        rows = query("SELECT * FROM orders ORDER BY created_at DESC", [])
    return JSONResponse(content=rows)


@router.get("/api/orders/{order_id}/lines")
async def api_order_lines(order_id: int, session: str | None = Cookie(default=None)):
    _auth_required(session)
    rows = query(
        "SELECT * FROM order_lines WHERE order_id = %s ORDER BY id",
        [order_id],
    )
    return JSONResponse(content=rows)


@router.post("/api/orders/{order_id}/status")
async def api_update_status(
    order_id: int,
    request: Request,
    session: str | None = Cookie(default=None),
):
    _auth_required(session)
    body = await request.json()
    new_status = body.get("status")
    valid = {"to_do", "ready", "delivered", "done"}
    if new_status not in valid:
        raise HTTPException(status_code=400, detail="Invalid status")

    execute(
        "UPDATE orders SET status = %s WHERE id = %s",
        [new_status, order_id],
    )

    # Notify customer
    order_rows = query("SELECT * FROM orders WHERE id = %s", [order_id])
    if order_rows:
        order = order_rows[0]
        phone = order.get("phone", "")
        labels = {
            "to_do": "قيد التجهيز ⏳",
            "ready": "جاهز للاستلام ✅",
            "delivered": "في الطريق إليك 🚚",
            "done": "مكتمل 🎉",
        }
        label = labels.get(new_status, new_status)
        msg = f"مرحباً! تم تحديث طلبك رقم #{order_id} — الحالة الآن: {label}"
        try:
            send_whatsapp_message(phone, msg)
        except Exception:
            pass

    return JSONResponse(content={"ok": True})


# ── Dashboard stats API ──────────────────────────────────────────────────────

@router.get("/api/dashboard/stats")
async def api_dashboard_stats(session: str | None = Cookie(default=None)):
    _auth_required(session)

    # Monthly totals
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_rows = query(
        "SELECT COUNT(*) as cnt, SUM(total) as revenue FROM orders WHERE created_at >= %s",
        [month_start.isoformat()],
    )
    monthly = month_rows[0] if month_rows else {"cnt": 0, "revenue": 0}

    # Status breakdown
    status_rows = query(
        "SELECT status, COUNT(*) as cnt FROM orders GROUP BY status", []
    )
    status_map = {r["status"]: r["cnt"] for r in status_rows}

    # 30-day daily chart
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    daily_rows = query(
        "SELECT DATE(created_at) as day, COUNT(*) as cnt, SUM(total) as revenue "
        "FROM orders WHERE created_at >= %s GROUP BY day ORDER BY day",
        [thirty_days_ago],
    )

    # Top 5 products this month
    top_rows = query(
        "SELECT ol.product_name, SUM(ol.qty) as total_qty "
        "FROM order_lines ol "
        "JOIN orders o ON o.id = ol.order_id "
        "WHERE o.created_at >= %s "
        "GROUP BY ol.product_name ORDER BY total_qty DESC LIMIT 5",
        [month_start.isoformat()],
    )

    return JSONResponse(
        content={
            "monthly_orders": monthly.get("cnt", 0),
            "monthly_revenue": float(monthly.get("revenue") or 0),
            "status_breakdown": status_map,
            "daily_chart": [
                {
                    "day": str(r["day"]),
                    "cnt": r["cnt"],
                    "revenue": float(r.get("revenue") or 0),
                }
                for r in daily_rows
            ],
            "top_products": [
                {"name": r["product_name"], "qty": r["total_qty"]}
                for r in top_rows
            ],
        }
    )


# ── Products API ─────────────────────────────────────────────────────────────

@router.get("/api/products")
async def api_products(session: str | None = Cookie(default=None)):
    _auth_required(session)
    rows = query("SELECT * FROM products ORDER BY name", [])
    return JSONResponse(content=rows)


@router.post("/api/products")
async def api_create_product(
    request: Request, session: str | None = Cookie(default=None)
):
    _auth_required(session)
    body = await request.json()
    row = execute_returning(
        "INSERT INTO products (name, price, description, tags, active) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING *",
        [
            body.get("name"),
            body.get("price"),
            body.get("description", ""),
            body.get("tags", ""),
            body.get("active", True),
        ],
    )
    return JSONResponse(content=row)


@router.post("/api/products/{product_id}")
async def api_update_product(
    product_id: int,
    request: Request,
    session: str | None = Cookie(default=None),
):
    _auth_required(session)
    body = await request.json()
    execute(
        "UPDATE products SET name = %s, price = %s, description = %s, tags = %s WHERE id = %s",
        [
            body.get("name"),
            body.get("price"),
            body.get("description", ""),
            body.get("tags", ""),
            product_id,
        ],
    )
    return JSONResponse(content={"ok": True})


@router.post("/api/products/{product_id}/toggle")
async def api_toggle_product(
    product_id: int, session: str | None = Cookie(default=None)
):
    _auth_required(session)
    execute(
        "UPDATE products SET active = NOT active WHERE id = %s",
        [product_id],
    )
    return JSONResponse(content={"ok": True})


@router.post("/api/products/{product_id}/delete")
async def api_delete_product(
    product_id: int, session: str | None = Cookie(default=None)
):
    _auth_required(session)
    execute("DELETE FROM products WHERE id = %s", [product_id])
    return JSONResponse(content={"ok": True})


# ── Broadcast API ─────────────────────────────────────────────────────────────

@router.get("/api/broadcast/recipients")
async def api_broadcast_recipients(session: str | None = Cookie(default=None)):
    """Return all customers who have placed at least one order."""
    _auth_required(session)
    rows = query(
        "SELECT DISTINCT c.phone, c.name "
        "FROM customers c "
        "JOIN orders o ON o.phone = c.phone "
        "ORDER BY c.name",
        [],
    )
    return JSONResponse(content={"recipients": rows, "total": len(rows)})


@router.post("/api/broadcast/send")
async def api_broadcast_send(
    request: Request, session: str | None = Cookie(default=None)
):
    """
    Send a broadcast message to selected recipients.

    Body:
        message (str): The final message text to send
        phones (list[str]): List of phone numbers to send to
    """
    _auth_required(session)
    body = await request.json()
    message = (body.get("message") or "").strip()
    phones = body.get("phones") or []

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if not phones:
        raise HTTPException(status_code=400, detail="No recipients selected.")

    sent = []
    failed = []

    for phone in phones:
        try:
            send_whatsapp_message(str(phone), message)
            sent.append(phone)
        except Exception:
            failed.append(phone)

    return JSONResponse(
        content={
            "ok": True,
            "sent": len(sent),
            "failed": len(failed),
            "failed_numbers": failed,
        }
    )
```

```
### FILE: app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

from app.routers import whatsapp, ui, debug, messages
from app.services import followup, monthly_report, retry_queue

app = FastAPI(title="ALYASMEEN AuntOps")

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(whatsapp.router)
app.include_router(ui.router)
app.include_router(debug.router)
app.include_router(messages.router)

# ── Scheduler ────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()

scheduler.add_job(
    followup.send_followups,
    "interval",
    hours=6,
    id="followup",
)

scheduler.add_job(
    monthly_report.send_monthly_report,
    "cron",
    day=1,
    hour=8,
    minute=0,
    id="monthly_report",
)

scheduler.add_job(
    retry_queue.process_retries,
    "interval",
    minutes=15,
    id="retry_queue",
)

scheduler.start()


@app.get("/health")
async def health():
    return {"status": "ok"}
```

```
### FILE: app/data/prompts/message_improvement.txt
You are a professional message editor for ALYASMEEN, a small Palestinian handmade skincare and candle business.

Your sole job is to polish WhatsApp broadcast messages written by the business owner (the aunt) before she sends them to her customers.

STRICT RULES — follow every one of these without exception:

1. LANGUAGE: Detect the language of the input message and respond ONLY in that same language.
   - If the message is in Arabic → improve it in Arabic only.
   - If the message is in English → improve it in English only.
   - NEVER mix languages. NEVER translate.

2. MEANING: Do NOT change the meaning of the message in any way.
   - Do NOT add products, prices, offers, or promotions that are not in the original.
   - Do NOT remove information the aunt included.
   - Do NOT invent facts, dates, phone numbers, or store details.

3. CORRECTIONS: You may fix:
   - Grammar and spelling mistakes
   - Punctuation errors
   - Awkward phrasing or run-on sentences
   - Informal typos (but keep the warm, personal tone)

4. TONE: Keep the message warm, friendly, and personal — like a trusted small business owner talking to loyal customers. Do not make it sound corporate or cold.

5. FORMAT: Preserve the original structure:
   - Keep all emojis in their original positions (you may add one emoji at most if it clearly improves the message)
   - Keep bullet points or numbered lists if used
   - Keep line breaks where the aunt intended them
   - Do not pad the message or make it unnecessarily longer

6. OUTPUT: Return ONLY the improved message text.
   - No preamble like "Here is the improved version:"
   - No commentary, explanation, or labels
   - No quotation marks wrapping the output
   - Just the clean, ready-to-send message

EXAMPLES:

Input (Arabic): "عندنا عرض اليوم على الكريمات بس بكره بنتهي لا تفوتكم"
Output (Arabic): "عندنا عرض خاص اليوم على الكريمات — العرض ينتهي غداً فلا تفوّتوه! 🌿"

Input (English): "hi we have new products just arrived fresh batch of candles available now"
Output (English): "Hi! 🕯️ We have new products just arrived — a fresh batch of candles is now available. Don't miss out!"
```

```
### FILE: app/templates/broadcast.html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>إرسال رسالة جماعية — ALYASMEEN</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: #f0f4f8;
      color: #1a202c;
      min-height: 100vh;
    }

    /* ── Nav ── */
    nav {
      background: #2d3748;
      color: #fff;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    nav .brand { font-size: 1.2rem; font-weight: 700; }
    nav .links a {
      color: #cbd5e0;
      text-decoration: none;
      margin-inline-start: 20px;
      font-size: 0.9rem;
      transition: color 0.2s;
    }
    nav .links a:hover { color: #fff; }
    nav .links a.active { color: #68d391; font-weight: 600; }

    /* ── Layout ── */
    .page { max-width: 900px; margin: 32px auto; padding: 0 16px; }

    h1 {
      font-size: 1.6rem;
      font-weight: 700;
      margin-bottom: 8px;
      color: #2d3748;
    }
    .subtitle { color: #718096; font-size: 0.95rem; margin-bottom: 28px; }

    /* ── Cards ── */
    .card {
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      padding: 24px;
      margin-bottom: 20px;
    }
    .card h2 {
      font-size: 1rem;
      font-weight: 700;
      color: #4a5568;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 2px solid #e2e8f0;
    }

    /* ── Form elements ── */
    label {
      display: block;
      font-size: 0.88rem;
      font-weight: 600;
      color: #4a5568;
      margin-bottom: 6px;
    }

    textarea {
      width: 100%;
      min-height: 140px;
      border: 1.5px solid #e2e8f0;
      border-radius: 8px;
      padding: 12px;
      font-size: 0.95rem;
      font-family: inherit;
      resize: vertical;
      transition: border-color 0.2s;
      direction: rtl;
    }
    textarea:focus { outline: none; border-color: #667eea; }

    .char-count {
      text-align: left;
      font-size: 0.8rem;
      color: #a0aec0;
      margin-top: 4px;
    }

    /* ── Buttons ── */
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 10px 20px;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 600;
      font-family: inherit;
      transition: all 0.2s;
    }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .btn-primary {
      background: #48bb78;
      color: #fff;
    }
    .btn-primary:hover:not(:disabled) { background: #38a169; }

    .btn-secondary {
      background: #fff;
      color: #667eea;
      border: 1.5px solid #667eea;
    }
    .btn-secondary:hover:not(:disabled) { background: #ebf4ff; }

    .btn-ai {
      background: #fff;
      color: #805ad5;
      border: 1.5px solid #805ad5;
      float: left; /* left-aligned in RTL = right side of page */
    }
    .btn-ai:hover:not(:disabled) { background: #faf5ff; }

    .btn-danger {
      background: #fff;
      color: #e53e3e;
      border: 1.5px solid #e53e3e;
    }
    .btn-danger:hover:not(:disabled) { background: #fff5f5; }

    .btn-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 12px;
      flex-wrap: wrap;
    }

    /* ── Recipients ── */
    .recipients-summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 8px;
    }
    .badge {
      display: inline-block;
      background: #ebf8ff;
      color: #2b6cb0;
      font-size: 0.82rem;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 20px;
    }
    .recipient-list {
      max-height: 180px;
      overflow-y: auto;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
    }
    .recipient-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-bottom: 1px solid #f7fafc;
      font-size: 0.9rem;
    }
    .recipient-item:last-child { border-bottom: none; }
    .recipient-item input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }
    .recipient-name { font-weight: 600; color: #2d3748; flex: 1; }
    .recipient-phone { color: #718096; font-size: 0.82rem; direction: ltr; }

    /* ── Spinner ── */
    .spinner {
      display: inline-block;
      width: 16px;
      height: 16px;
      border: 2px solid currentColor;
      border-top-color: transparent;
      border-radius: 50%;
      animation: spin

---

## 3. QA Result

FAIL

[FILE app/routers/messages.py:1] FORBIDDEN_AI_FILE — new file `app/routers/messages.py` imports and calls `improve_message_draft()` from `ai_service.py`, but this should be a router-only file; all AI logic must stay in `ai_service.py`

[FILE app/services/ai_service.py:1] DIRECT_ANTHROPIC_IMPORT — `from anthropic import Anthropic` at line 4; Anthropic SDK must only be imported once globally in `ai_service.py`, not in routers

[FILE app/services/ai_service.py:6] HARDCODED_CLIENT — `client = Anthropic(api_key=Config.CLAUDE_API_KEY)` at line 6 creates a module-level client; this should be instantiated inside each function to allow graceful fallback and error handling

[FILE app/services/ai_service.py:99] MISSING_IMPLEMENTATION — `improve_message_draft()` is incomplete; it never catches `anthropic.APIError` or network exceptions explicitly, so the HTTPException in `messages.py` catches generic `Exception` instead of specific API failures

[FILE app/routers/ui.py:1] MISSING_ROUTER_REGISTRATION — `app/main.py` does not include `app.include_router(messages.router)` (line 16 exists but verify it was added; if the developer code snippet is incomplete, this is the issue)

[FILE app/templates/broadcast.html:999] INCOMPLETE_TEMPLATE — broadcast.html template is truncated at line 999 (the CSS `animation: spin` rule is incomplete); the full JS modal logic for "Improve with AI" button, side-by-side comparison modal, and accept/edit/discard flow is missing

[FILE app/data/prompts/message_improvement.txt:1] MISSING_FILE — the prompt file is provided in the developer code but was not confirmed to exist in the project; it must be created at this exact path for `_load_improvement_prompt()` to load it correctly

[FILE app/services/ai_service.py:103] ACCEPTANCE_CRITERIA_1_MISSING — "Improve with AI" button positioning, disabled state, and loading spinner not defined in requirements; acceptance criteria require specific UI styling (right-aligned, secondary button, disabled when empty, 2–3s spinner)

[FILE app/routers/ui.py:180] ACCEPTANCE_CRITERIA_2_MISSING — side-by-side modal layout not implemented; acceptance criteria require two columns (original vs. improved) with specific copy labels in Arabic and English, but `broadcast.html` template is incomplete and provides no modal structure

[FILE app/routers/ui.py:200] ACCEPTANCE_CRITERIA_3_MISSING — acceptance criteria require modal action buttons "Use this version" / "Edit" / "Discard" with full edit-in-modal flow; implementation only stubs POST `/api/improve-message`, no UI logic for button states or form submission

[FILE app/routers/ui.py:1] ACCEPTANCE_CRITERIA_4_MISSING — graceful fallback (error toast, retry button, original draft can still send) not implemented; `messages.py` raises HTTPException but broadcast.html has no toast notification UI or error handling

[FILE tests/test_api_messages.py:1] MISSING_TEST_FILE — required test file not provided; PM brief specifies unit tests for `/api/improve-message` (happy path, degraded Claude, language detection, meaning preservation)

[FILE tests/test_broadcast_ui.py:1] MISSING_TEST_FILE — required test file not provided; PM brief specifies integration tests for broadcast page UI (improvement button interaction, side-by-side display, accept/edit/discard flows)

[FILE app/services/ai_service.py:53] ARABIC_TEXT_RULE_VIOLATION — `improve_message_draft()` at line 53 builds user message "يرجى تحسين رسالة واتساب التالية باللغة العربية فقط" which is a hardcoded system instruction, not business text; this is acceptable, but confirm it is not translated from English

[FILE app/routers/ui.py:1] NO_BROADCAST_RECIPIENTS_FILTER — `/api/broadcast/recipients` returns all customers with at least one order, but acceptance criteria do

---

## 4. DevOps Checklist

# Deployment Checklist

## 1. requirements.txt
**Yes** — Add `langdetect>=1.0.9` (used in `ai_service.py` for language detection)

```
langdetect>=1.0.9
```

---

## 2. Database Migration
**Yes** — No new tables needed, but verify existing schema. Run these checks:

```sql
-- Verify products table exists and has all required columns
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'products' 
ORDER BY ordinal_position;

-- Expected columns: id, name, price, description, tags, active, created_at

-- Verify chat_history table exists (used by get_ai_reply)
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'chat_history' 
ORDER BY ordinal_position;

-- Expected columns: id, phone, role, content, created_at
```

**No SQL CREATE statements needed** — all tables already exist from prior migrations.

---

## 3. .env.example
**Yes** — Add one new variable:

```
CLAUDE_MODEL=claude-3-5-haiku-20241022
```

**Verify these already exist:**
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `DASHBOARD_PASSWORD`
- `SECRET_KEY`
- `AUNT_PHONE`
- `CLAUDE_API_KEY`
- `WA_META_TOKEN`
- `WA_META_PHONE_ID`
- `WA_META_VERIFY_TOKEN`
- `WA_META_APP_SECRET` (optional)
- `USE_MOCK_WHATSAPP`

---

## 4. Procfile
**No** — `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT` is unchanged.

---

## 5. Railway / Render

### Steps:

1. **Push approved code to GitHub** — ensure all files are committed
   - `app/services/ai_service.py` (new)
   - `app/routers/messages.py` (new)
   - `app/data/prompts/message_improvement.txt` (new)
   - `app/templates/broadcast.html` (updated — complete the HTML)
   - `requirements.txt` (add `langdetect>=1.0.9`)
   - All test files (once created)

2. **Platform environment variables** — in Railway/Render dashboard, add:
   ```
   CLAUDE_MODEL=claude-3-5-haiku-20241022
   ```

3. **Build command** — no change needed (uses `pip install -r requirements.txt`)

4. **Health check** — verify your platform is configured to check:
   ```
   GET /health
   ```
   Railway/Render should be set to probe this every 10 seconds. If not configured, add it manually in your service settings.

5. **Deploy** — platform will auto-redeploy from GitHub on merge; monitor logs for startup errors.

---

## 6. Meta WhatsApp
**No** — webhook already registered and subscribed to `messages` event in prior setup. No changes needed.

However, **verify in Meta Developer Portal**:
- App → WhatsApp → API Setup → Webhook URL is `https://your-app-url/whatsapp/webhook`
- Verify Token matches `WA_META_VERIFY_TOKEN` env var
- Subscribed to: `messages`

---

## 7. Supabase
**No** — no new RLS policies or RPC functions needed.

**However, complete one missing task:** Create the knowledge base directory and seed with initial `.md` files:

```bash
mkdir -p app/data/knowledge

# Create store_info.md
cat > app/data/knowledge/store_info.md << 'EOF'
# ALYASMEEN Store Information

**Hours:** 9 AM - 6 PM, Saturday - Thursday
**Location:** Palestine
**Contact:** [Your phone number]

We are a small family business specializing in handmade skincare and scented candles made with natural ingredients.
EOF

# Create faq.md
cat > app/data/knowledge/faq.md << 'EOF'
#
