"""
constants.py — Immutable project-wide constants for ALYASMEEN AuntOps.

All magic strings and numbers that appear in multiple places across the
codebase live here. Import from this module instead of hardcoding values.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Order lifecycle
# ---------------------------------------------------------------------------

ORDER_STATUSES: frozenset[str] = frozenset({"to_do", "ready", "delivered", "done"})

FULFILLMENT_TYPES: frozenset[str] = frozenset({"pickup", "delivery"})

ARABIC_STATUS_LABELS: dict[str, str] = {
    "to_do":     "قيد التحضير 🔄",
    "ready":     "جاهز للاستلام ✅",
    "delivered": "تم التوصيل 🚚",
    "done":      "مكتمل ✅",
}

# Labels shown in the dashboard (Arabic UI)
DASHBOARD_STATUS_LABELS: dict[str, str] = {
    "to_do":     "يجب التجهيز",
    "ready":     "جاهز",
    "delivered": "في الطريق",
    "done":      "مكتمل",
}

# ---------------------------------------------------------------------------
# Bot commands
# ---------------------------------------------------------------------------

HARD_COMMANDS: frozenset[str] = frozenset({
    "cart", "clear", "pickup", "delivery", "confirm", "menu", "وين طلبي",
})

ORDER_TRACKING_KEYWORDS: tuple[str, ...] = (
    "طلبي", "وين طلب", "where is my order", "order status", "متى يجهز",
)

# ---------------------------------------------------------------------------
# Conversation / AI
# ---------------------------------------------------------------------------

MAX_CHAT_HISTORY_TURNS: int = 6
MAX_AI_TOKENS: int = 400
AI_TEMPERATURE: float = 0.3

# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

WHATSAPP_MENU_LIMIT: int = 3
MAX_CART_ITEMS: int = 20

# ---------------------------------------------------------------------------
# Scheduler intervals (defaults — overridden by config/setup.json at runtime)
# ---------------------------------------------------------------------------

FOLLOWUP_INTERVAL_HOURS: int = 6
RETRY_INTERVAL_MINUTES: int = 15
MONTHLY_REPORT_DAY: int = 1
MONTHLY_REPORT_HOUR: int = 8

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

COOKIE_NAME: str = "alyasmeen_session"
