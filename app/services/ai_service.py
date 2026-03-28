"""
ai_service.py — Single AI layer for ALYASMEEN bot (Claude only).

Replaces the old ai_aunt.py + ai/assistant.py + ai/claude_client.py split.

Public API:
    generate_reply(user_message, previous_messages) -> str
    ai_available() -> bool

Note: This file is ~198 lines — within acceptable range (under 200). No split needed.
"""
from __future__ import annotations

import glob
import logging
import os
from typing import Callable

try:
    from anthropic import Anthropic
except Exception:
    Anthropic = None  # type: ignore

from app.services.config import Config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Knowledge base (loaded once from app/data/knowledge/*.md)
# ---------------------------------------------------------------------------

_KNOWLEDGE: str | None = None


def _load_knowledge() -> str:
    base = os.path.join(os.getcwd(), "app", "data", "knowledge")
    parts: list[str] = []
    for path in glob.glob(os.path.join(base, "**", "*.md"), recursive=True):
        try:
            with open(path, encoding="utf-8") as f:
                parts.append(f"# {os.path.basename(path)}\n" + f.read())
        except Exception:
            pass
    return "\n\n".join(parts)[:20_000]


def _knowledge() -> str:
    global _KNOWLEDGE
    if _KNOWLEDGE is None:
        _KNOWLEDGE = _load_knowledge()
    return _KNOWLEDGE


# ---------------------------------------------------------------------------
# Product context from catalog
# ---------------------------------------------------------------------------

def _product_context(user_message: str) -> str:
    try:
        from app.ai.retriever import search_products
        items = search_products(user_message, None)
    except Exception:
        return ""
    if not items:
        return ""
    lines = ["Matching products from catalog:"]
    for r in items[:6]:
        name = r.get("name", "")
        price = r.get("price", "")
        desc = (r.get("description") or "").strip()
        if desc:
            lines.append(f"- {name} — {price} | {desc[:90]}")
        else:
            lines.append(f"- {name} — {price}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _is_arabic(text: str) -> bool:
    try:
        return any("\u0600" <= ch <= "\u06FF" for ch in text)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "أنتِ 'عمة ALYASMEEN' — مساعدة ودودة ومتخصصة في منتجات العناية الطبيعية "
    "والمصنوعة يدويًا (كريمات، لوشن، شموع) من فلسطين.\n\n"
    "القواعد:\n"
    "- اقترحي فقط منتجات موجودة في الكتالوج المرفق. لا تخترعي أسماء أو أسعارًا.\n"
    "- إذا كان طلب الزبون واضحًا (نوع البشرة + المشكلة)، ابدئي بتوصية 1–3 منتجات مباشرة.\n"
    "- اسألي 1–2 سؤال توضيحي فقط عند الضرورة.\n"
    "- لكل منتج: الاسم + الفائدة الرئيسية + السعر (إن وُجد) + سطر قصير للاستخدام.\n"
    "- ردودك قصيرة ومباشرة (3 فقرات كحد أقصى أو 6 نقاط).\n"
    "- هذا ليس بديلاً عن استشارة طبيب.\n"
    "- إذا كتب المستخدم بالإنجليزية، ردّي بالإنجليزية. وإلا فبالعربية.\n"
)


# ---------------------------------------------------------------------------
# Tool definitions — passed to Claude so it can call them
# ---------------------------------------------------------------------------

_TOOLS: list[dict] = [
    {
        "name": "add_to_cart",
        "description": (
            "Add a product to the customer's shopping cart. "
            "Use this when the customer clearly says they want to order or buy a specific product. "
            "Match by the product name the customer mentioned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "The product name the customer wants (Arabic or English as they said it)",
                },
                "qty": {
                    "type": "integer",
                    "description": "Quantity to add. Defaults to 1 if the customer did not specify.",
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "show_menu",
        "description": (
            "Show the product catalog to the customer as a numbered list. "
            "Use when the customer asks to see products, browse, or asks what is available. "
            "Optionally filter by category keyword."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "Optional category keyword to filter by (e.g. 'candles', 'creams', 'lotions'). "
                        "Leave empty to show all products."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_order_status",
        "description": (
            "Look up the customer's most recent order and return its status. "
            "Use when the customer asks about their order, delivery, or where their package is."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "save_address",
        "description": (
            "Save the customer's delivery address. "
            "Use when the customer provides their address for delivery during checkout."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "The full delivery address as the customer wrote it",
                },
            },
            "required": ["address"],
        },
    },
]


def _build_messages(
    user_message: str,
    previous_messages: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Build the messages list for Claude API (no system role in messages list)."""
    messages: list[dict[str, str]] = []

    # Inject previous conversation (last 6 turns)
    if previous_messages:
        for m in previous_messages[-6:]:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    # Append current user message, attaching catalog context inline
    ctx = _product_context(user_message)
    full_user_content = user_message
    if ctx:
        full_user_content += f"\n\n---\n{ctx}"

    messages.append({"role": "user", "content": full_user_content})
    return messages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ai_available() -> bool:
    return bool(Config.CLAUDE_API_KEY and Anthropic)


def generate_reply(
    user_message: str,
    previous_messages: list[dict[str, str]] | None = None,
    cart: list[dict] | None = None,
    customer_name: str | None = None,
    tool_executor: Callable[[str, dict], str] | None = None,
) -> str:
    """
    Generate an AI reply using Claude.

    - user_message: the latest message from the customer
    - previous_messages: list of {"role": "user"/"assistant", "content": "..."} from DB
    - cart: current cart items so Claude can reference them in context
    - tool_executor: optional callable(tool_name, tool_input) -> result_str.
        When provided, Claude is given the 4 action tools and can call them.
        A second API call is made after tool execution to get the final reply.

    Returns the assistant's reply as a plain string.
    """
    if not ai_available():
        return (
            "ميزة الذكاء الاصطناعي غير مفعّلة حالياً. "
            "أضف CLAUDE_API_KEY في ملف .env لتفعيلها ✨"
        )

    know = _knowledge()
    system = _SYSTEM_PROMPT
    if customer_name:
        system += f"\n\nاسم الزبون/ة: {customer_name}. خاطبيه/ا باسمه/ا عند الترحيب أو التوصية."
    if know:
        system += f"\n\nمعلومات عن المتجر (للقراءة فقط):\n{know}"

    # Tell Claude about the cart so it can guide the customer
    if cart:
        cart_lines = []
        total = 0.0
        for item in cart:
            name = item.get("name", "")
            qty = int(item.get("qty", 1))
            price = float(item.get("price", 0) or 0)
            total += qty * price
            cart_lines.append(f"- {name} × {qty} = {qty * price:.2f}₪")
        cart_lines.append(f"الإجمالي: {total:.2f}₪")
        system += (
            "\n\nسلة الزبون الحالية:\n"
            + "\n".join(cart_lines)
            + "\n(إذا أراد الزبون التأكيد، ذكّره بكتابة 'confirm')"
        )

    try:
        client = Anthropic(api_key=Config.CLAUDE_API_KEY)  # type: ignore
        messages = _build_messages(user_message, previous_messages)

        create_kwargs: dict = dict(
            model=Config.CLAUDE_MODEL,
            max_tokens=400,
            temperature=0.3,
            system=system,
            messages=messages,
        )
        if tool_executor:
            create_kwargs["tools"] = _TOOLS

        resp = client.messages.create(**create_kwargs)

        # ---------------------------------------------------------------
        # Agentic loop: if Claude chose to call a tool, execute it and
        # make a second call to get the final text reply.
        # ---------------------------------------------------------------
        if tool_executor and resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    try:
                        result_text = tool_executor(block.name, dict(block.input))
                    except Exception as exc:
                        log.warning("Tool %s failed: %s", block.name, exc)
                        result_text = f"خطأ في تنفيذ الأداة: {exc}"
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        }
                    )

            # Append assistant turn (with tool_use blocks) + tool results
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})

            # Second call — Claude now knows the tool results and writes the reply
            resp = client.messages.create(**{**create_kwargs, "messages": messages})

        parts = [
            block.text
            for block in (resp.content or [])
            if getattr(block, "text", None)
        ]
        return "\n".join(parts).strip() or "(no reply)"
    except Exception as e:
        log.exception("Claude API error")
        return f"عذرًا، صار خلل مؤقت. جرّب مرة ثانية. ({e})"


# ---------------------------------------------------------------------------
# Broadcast message improvement
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """Return 'ar' if text contains Arabic script characters, else 'en'."""
    return "ar" if any("\u0600" <= ch <= "\u06FF" for ch in text) else "en"


def improve_message(draft: str) -> dict:
    """
    Improve tone and grammar of a broadcast draft without changing meaning.
    Returns {"original": str, "improved": str, "language": "ar"|"en"}.
    Raises Exception if the AI call fails (caller handles HTTP error response).
    """
    if not ai_available():
        raise RuntimeError("CLAUDE_API_KEY not set — AI improvement unavailable")

    language = detect_language(draft)

    if language == "ar":
        system_prompt = (
            "أنت مساعد متخصص في تحسين أسلوب رسائل التواصل التجاري باللغة العربية.\n"
            "مهمتك:\n"
            "- حسّن نبرة الرسالة لتكون أكثر ودية واحترافية.\n"
            "- صحّح الأخطاء الإملائية والنحوية وعلامات الترقيم فقط.\n"
            "- لا تغيّر المعنى أبداً.\n"
            "- لا تعدّل أي أسعار أو أسماء منتجات أو تواريخ.\n"
            "- لا تضف منتجات أو ادعاءات جديدة غير موجودة في النص.\n"
            "- أجب باللغة العربية فقط.\n"
            "- أعد الرسالة المحسّنة فقط بدون أي تفسير أو مقدمة."
        )
    else:
        system_prompt = (
            "You are an assistant that improves the tone and grammar of business broadcast messages.\n"
            "Your task:\n"
            "- Improve tone to be friendly and professional.\n"
            "- Fix spelling, grammar, and punctuation only.\n"
            "- Never change the meaning of the message.\n"
            "- Never alter any prices, product names, or dates.\n"
            "- Never add new products, features, or claims not in the original.\n"
            "- Reply in English only.\n"
            "- Return only the improved message with no explanation or preamble."
        )

    client = Anthropic(api_key=Config.CLAUDE_API_KEY)  # type: ignore
    response = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=Config.BROADCAST_IMPROVEMENT_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": draft}],
    )
    improved = response.content[0].text.strip()

    return {"original": draft, "improved": improved, "language": language}
