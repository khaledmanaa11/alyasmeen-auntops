"""
verify_products.py — Fetch and display all products from Supabase.

Usage:
    python scripts/verify_products.py

Rules followed:
- Uses app/db/database.py (never imports supabase directly)
- Loads secrets via app/services/config.py (never hardcodes secrets)
"""
import sys
from pathlib import Path

# Force UTF-8 output so Arabic + emoji print correctly on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make `app.*` importable when running from project root or scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import query  # noqa: E402


def main() -> None:
    print("🌿 ALYASMEEN AuntOps — التحقق من المنتجات\n")

    rows = query("SELECT id, name, price, active, created_at FROM products ORDER BY id")

    if not rows:
        print("⚠️  لا توجد منتجات في قاعدة البيانات.")
        print("   شغّلي seed_products.py أولاً.")
        return

    print(f"{'ID':<5} {'الاسم':<40} {'السعر':<10} {'الحالة'}")
    print("-" * 70)

    for row in rows:
        status = "✅ نشط" if row.get("active") else "⏸ غير نشط"
        name   = row.get("name", "")
        price  = row.get("price", 0)
        pid    = row.get("id", "")
        print(f"{str(pid):<5} {name:<40} {str(price)+'₪':<10} {status}")

    print("-" * 70)
    print(f"\n✅ إجمالي المنتجات: {len(rows)}")


if __name__ == "__main__":
    main()
