"""
ai_service.py — Single AI layer for ALYASMEEN bot (Claude only).

Replaces the old ai_aunt.py + ai/assistant.py + ai/claude_client.py split.

Public API:
    generate_reply(user_message, previous_messages) -> str
    ai_available() -> bool

Note: This file contains the full AI layer — prompt, tools, knowledge, and catalog injection.
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
from app.shared.gatekeeper import gatekeeper

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Knowledge base (app/data/knowledge/*.md) — selectively injected per message
# ---------------------------------------------------------------------------

# Cache: filename → (triggers_set, full_content)
_KNOWLEDGE_FILES: dict[str, tuple[set[str], str]] | None = None


def _load_knowledge_files() -> dict[str, tuple[set[str], str]]:
    """Load all .md files from the knowledge directory.

    Each file may start with a comment line:
        # triggers: word1, word2, word3
    If present, the file is only injected when the user message contains one
    of those trigger words. Files without a triggers line are always included.
    """
    base = os.path.join(os.getcwd(), "app", "data", "knowledge")
    result: dict[str, tuple[set[str], str]] = {}
    for path in glob.glob(os.path.join(base, "**", "*.md"), recursive=True):
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            triggers: set[str] = set()
            first_line = content.split("\n", 1)[0].strip()
            if first_line.startswith("# triggers:"):
                raw = first_line[len("# triggers:"):].strip()
                triggers = {t.strip() for t in raw.replace("،", ",").split(",") if t.strip()}
            result[os.path.basename(path)] = (triggers, content)
        except Exception:
            pass
    return result


def _knowledge_files() -> dict[str, tuple[set[str], str]]:
    global _KNOWLEDGE_FILES
    if _KNOWLEDGE_FILES is None:
        _KNOWLEDGE_FILES = _load_knowledge_files()
    return _KNOWLEDGE_FILES


def _relevant_knowledge(user_message: str) -> str:
    """Return only the knowledge files whose trigger keywords appear in the user message.

    Falls back to returning all files if none match, so the context is never
    completely empty when the knowledge base has content.
    """
    files = _knowledge_files()
    if not files:
        return ""
    msg_lower = user_message.lower()
    matched: list[str] = []
    unfiltered: list[str] = []
    for _name, (triggers, content) in files.items():
        if not triggers:
            # No trigger line — always include
            unfiltered.append(content)
        elif any(t.lower() in msg_lower for t in triggers):
            matched.append(content)
    selected = matched or unfiltered  # use matched if any, else files with no triggers
    return "\n\n".join(selected)[:20_000]


# ---------------------------------------------------------------------------
# Product context — always inject full catalog into system prompt
# ---------------------------------------------------------------------------

def _full_catalog_context() -> str:
    """Return all active products formatted as a <catalog> XML block.

    For a small store (≤30 products ≈ 1 500 tokens) it is always cheaper to
    include the full catalog in the system prompt than to do per-message
    keyword retrieval, which silently returns nothing when the customer says
    'بدي اطلب' without mentioning a product name.
    """
    try:
        from app.ai.retriever import _catalog as get_catalog
        items = get_catalog()
    except Exception:
        return ""
    if not items:
        return ""
    lines = ["<catalog>"]
    for r in items:
        name  = r.get("name", "")
        price = r.get("price", "")
        desc  = (r.get("description") or "").strip()
        tags  = ", ".join(r.get("tags", []))
        line  = f"- {name} | {price}₪"
        if tags:
            line += f" | tags: {tags}"
        if desc:
            line += f" | {desc[:100]}"
        lines.append(line)
    lines.append("</catalog>")
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

_SYSTEM_PROMPT = """\
<role>
أنتِ "عمة ALYASMEEN" — مساعدة ودودة ومتخصصة في منتجات العناية الطبيعية
والمصنوعة يدويًا (كريمات، لوشن، شموع) من فلسطين.
استخدمي دائمًا اللهجة الفلسطينية الدارجة، وكوني دافئة ومشجعة.
</role>

<catalog_grounding>
اقترحي فقط منتجات موجودة في قائمة <catalog> أدناه.
لا تخترعي أسماء منتجات أو أسعارًا أبدًا.
إذا لم يطابق طلب الزبون أي منتج، استدعي show_menu أو اطرحي سؤالاً توضيحيًا.
</catalog_grounding>

<tool_rules>
<decision_tree>
- إذا ذكر الزبون اسم منتج + فعل شراء (بدي، بشتري، أطلب، I want، add، buy)
  → استدعي add_to_cart مباشرة بدون أسئلة إضافية
- إذا ذكر الزبون فئة منتجات (كريمات، شموع، لوشن، creams، candles، lotions)
  → استدعي show_menu مع تصفية الفئة المناسبة
- إذا قال الزبون "بدي اطلب" أو "شو عندكم" أو "I want to order" أو "show me products" أو أي جملة تعني العرض العام
  → استدعي show_menu بدون تصفية
- إذا وصف الزبون مشكلة بشرة (جافة، دهنية، حساسية، حب شباب) بدون فعل شراء واضح
  → اسألي سؤالاً واحداً لتوضيح نوع البشرة، ثم أوصي بمنتج مناسب، ثم انتظري تأكيد الرغبة في الشراء
- إذا ذكر الزبون اسم منتج بدون فعل شراء (مثلاً "الكريم الفلاني")
  → اسألي: "بدك تضيفه للسلة؟" — لا تستدعي add_to_cart حتى يؤكد
- إذا اعترض الزبون على السعر ("غالي"، "expensive"، "كتير")
  → ردّي بأسلوب ودّي تشرحي فيه القيمة الطبيعية والجودة — لا تستدعي أي أداة
</decision_tree>
</tool_rules>

<examples>
<example>
<user>بدي كريم لبشرتي الجافة</user>
<action>call show_menu with category="كريمات"</action>
<reply>تفضلي كريماتنا الطبيعية المناسبة للبشرة الجافة 👇</reply>
</example>
<example>
<user>I want to order the hand cream</user>
<action>call add_to_cart with product_name="hand cream", qty=1</action>
<reply>Done! Hand cream is in your cart 🛒 Want to add anything else?</reply>
</example>
<example>
<user>شو عندكم؟</user>
<action>call show_menu with no category filter</action>
<reply>هاي كل منتجاتنا الطبيعية 🌿👇</reply>
</example>
<example>
<user>الكريم غالي شوي</user>
<action>no tool call — conversational reply only</action>
<reply>فاهمة قصدك 😊 منتجاتنا مصنوعة يدوياً بمكونات طبيعية 100% — مش في عليها أي كيماويات. الجودة بتفرق كتير على البشرة وبتحسيها من أول استخدام!</reply>
</example>
<example>
<user>بدي الكريم والشمعة</user>
<action>call add_to_cart twice — once for each product</action>
<reply>تمام! أضفت الاثنين للسلة 🎉</reply>
</example>
</examples>

<reply_rules>
- الردود قصيرة ومباشرة (3 فقرات كحد أقصى)
- إذا كتب الزبون بالإنجليزية، ردّي بالإنجليزية. وإلا فبالعربية
- إذا خلط الزبون العربية والإنجليزية، ردّي بالعربية واستخدمي أسماء المنتجات بنفس اللغة التي كتبها الزبون
- خاطبي الزبون باسمه عند الترحيب أو التوصية إذا كان الاسم متاحًا
</reply_rules>\
"""


# ---------------------------------------------------------------------------
# Tool definitions — passed to Claude so it can call them
# ---------------------------------------------------------------------------

_TOOLS: list[dict] = [
    {
        "name": "add_to_cart",
        "description": (
            "Add a product to the customer's shopping cart. "
            "Use this IMMEDIATELY — without asking follow-up questions — when: "
            "the customer names a specific product and uses a buying verb (بدي، بشتري، أطلب، I want، add، buy، order), "
            "the customer picks a numbered product from the menu, "
            "or the customer clearly wants to purchase something specific. "
            "Do NOT call this tool if the customer just mentions a product name without buying intent — ask 'بدك تضيفه للسلة؟' first. "
            "If the product name is ambiguous or matches multiple products, pick the closest match and add it — do not ask. "
            "Never confirm before adding — add immediately and let the customer see their cart."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": (
                        "The product name the customer wants, in Arabic or English exactly as they said it. "
                        "Examples: 'كريم اليدين', 'hand cream', 'الشمعة', 'lavender candle'."
                    ),
                },
                "qty": {
                    "type": "integer",
                    "description": (
                        "Quantity to add. Defaults to 1 if the customer did not specify. "
                        "Accept both Western numerals (1, 2, 3) and Arabic-Indic numerals (١، ٢، ٣)."
                    ),
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "show_menu",
        "description": (
            "Show the product catalog to the customer as a numbered list. "
            "Use when: the customer asks to see products ('شو عندكم؟', 'وريني المنتجات', 'what do you have?'), "
            "says they want to order without specifying a product ('بدي اطلب', 'I want to order'), "
            "or mentions a product category ('كريمات', 'شموع', 'لوشن', 'creams', 'candles', 'lotions'). "
            "Category filtering works by matching the keyword against product tags — "
            "pass the Arabic or English category word as-is (e.g. 'كريمات', 'candles'). "
            "Leave category empty to show all available products."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "Optional category keyword to filter by. "
                        "Examples: 'كريمات', 'شموع', 'لوشن', 'creams', 'candles'. "
                        "Leave empty or omit to show all products."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_order_status",
        "description": (
            "Look up the customer's most recent order and return its current status. "
            "Use when the customer asks about their order, delivery, or where their package is "
            "('وين طلبي؟', 'متى بوصل؟', 'شو صار بطلبي؟', 'where is my order?')."
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
            "Save the customer's delivery address during checkout. "
            "Use when the customer provides their address for delivery. "
            "IMPORTANT: Only save if the address contains at minimum a city AND neighborhood or street — "
            "at least 15 characters. "
            "If the customer sends only a city name (e.g. 'رام الله' alone), do NOT call this tool — "
            "instead ask: 'وين بالضبط؟ اكتبي المدينة والحي والشارع لو سمحتِ 🙏'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "The full delivery address as the customer wrote it (city + neighborhood + street minimum).",
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

    messages.append({"role": "user", "content": user_message})
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
        return "عذرًا، الخدمة غير متاحة حالياً. جرّب مرة ثانية بعد قليل 🙏"

    know = _relevant_knowledge(user_message)
    system = _SYSTEM_PROMPT

    # Always inject full catalog — grounding must be authoritative, not per-message
    catalog_ctx = _full_catalog_context()
    if catalog_ctx:
        system += f"\n\n{catalog_ctx}"

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
        client = Anthropic(api_key=Config.CLAUDE_API_KEY, timeout=30.0)  # type: ignore
        messages = _build_messages(user_message, previous_messages)

        create_kwargs: dict = dict(
            model=Config.CLAUDE_MODEL,
            max_tokens=600 if tool_executor else 400,
            temperature=0.3,
            system=system,
            messages=messages,
        )
        if tool_executor:
            create_kwargs["tools"] = _TOOLS

        resp = gatekeeper.execute("claude_ai", client.messages.create, **create_kwargs)

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

            # Second call — force a text reply (tool_choice="none") so that if
            # Claude tries to call another tool here, it writes a reply instead;
            # this stays a fixed 2-call loop, not a multi-round agentic loop.
            resp = gatekeeper.execute(
                "claude_ai",
                client.messages.create,
                **{**create_kwargs, "messages": messages, "tool_choice": {"type": "none"}},
            )

        parts = [
            block.text
            for block in (resp.content or [])
            if getattr(block, "text", None)
        ]
        return "\n".join(parts).strip() or "(no reply)"
    except Exception:
        log.exception("Claude API error")
        return "عذرًا، صار خلل مؤقت. جرّب مرة ثانية 🙏"


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

    client = Anthropic(api_key=Config.CLAUDE_API_KEY, timeout=30.0)  # type: ignore
    response = gatekeeper.execute(
        "claude_ai",
        client.messages.create,
        model=Config.CLAUDE_MODEL,
        max_tokens=Config.BROADCAST_IMPROVEMENT_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": draft}],
    )
    improved = response.content[0].text.strip()

    return {"original": draft, "improved": improved, "language": language}
