"""Product search module — loads active products from Supabase and provides keyword/tag-based search for the AI service."""
# retriever.py
from __future__ import annotations

import unicodedata


def _normalize(s: str) -> str:
    """Normalize Unicode text for case-insensitive matching.

    Decomposes the string using NFKD normalization, strips combining characters
    (diacritics), lowercases, and strips surrounding whitespace so that Arabic
    and Latin text can be compared uniformly.
    """
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()

_CATALOG = None

def invalidate_catalog() -> None:
    """Call this after any product create/update/delete so the bot picks up changes."""
    global _CATALOG
    _CATALOG = None

def _load_catalog() -> list[dict]:
    """Load active products from the Supabase products table.

    Queries all rows where active=true, ordered by id, and returns them as a
    list of dicts with keys: sku, name, price, description, tags.
    """
    from app.db.database import query
    rows = query(
        "SELECT id, name, price, description, tags, aliases, active FROM products WHERE active = true ORDER BY id"
    )
    result = []
    for r in rows:
        result.append({
            "sku": str(r["id"]),
            "name": r["name"],
            "price": float(r["price"]),
            "description": r.get("description") or "",
            "tags": [t.strip() for t in (r.get("tags") or "").split(",") if t.strip()],
            "aliases": r.get("aliases") or "",
        })
    return result

def _catalog() -> list[dict]:
    """Return the cached product catalog, loading it from Supabase on first call.

    Subsequent calls return the module-level cache. Call invalidate_catalog()
    to force a fresh load on the next access.
    """
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = _load_catalog()
    return _CATALOG

def search_products(query: str | None, category: str | None) -> list[dict]:
    """Search the product catalog by keyword and/or category.

    Performs a substring match against normalized name, description, and SKU
    fields. If neither query nor category is given, returns the first 8 products.

    Args:
        query:    Free-text search string (Arabic or Latin). None means no filter.
        category: Category name to filter by. None means no filter.

    Returns:
        Up to 8 products when no filter is given; up to 12 when a filter is applied.
    """
    rows = _catalog()
    if not rows:
        return []

    if not query and not category:
        return rows[:8]

    qn = _normalize(query or "")
    cn = _normalize(category or "")

    out = []
    for r in rows:
        if category and not any(cn in _normalize(t) for t in r.get("tags", [])):
            continue
        if query:
            hay = " ".join([
                _normalize(r.get("name", "")),
                _normalize(r.get("description", "")),
                _normalize(str(r.get("sku", ""))),
                _normalize(r.get("aliases", "")),
            ])
            if qn not in hay:
                continue
        out.append(r)
    return out[:12]

def describe_product(sku_or_name: str) -> dict:
    """Find a product by SKU or exact name.

    Compares the normalized input against each product's SKU and name fields.

    Args:
        sku_or_name: A product SKU (numeric string) or exact product name.

    Returns:
        The matching product dict, or an empty dict if not found.
    """
    q = _normalize(sku_or_name)
    for r in _catalog():
        if q in (_normalize(str(r.get("sku", ""))), _normalize(r.get("name", ""))):
            return r
    return {}
