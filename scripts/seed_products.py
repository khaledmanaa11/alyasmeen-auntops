"""
seed_products.py — Insert the 3 real ALYASMEEN products into Supabase.

Usage:
    python scripts/seed_products.py

Rules followed:
- Uses app/db/database.py (never imports supabase directly)
- Loads secrets via app/services/config.py (never hardcodes secrets)
- Checks for existing products before inserting (safe to run twice)
- SQL uses %s placeholders only
"""
import sys
from pathlib import Path

# Force UTF-8 output so Arabic + emoji print correctly on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make `app.*` importable when running from project root or scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import execute_returning, query  # noqa: E402

# ---------------------------------------------------------------------------
# Product data
# ---------------------------------------------------------------------------

PRODUCTS = [
    {
        "name": "مقشر طبيعي للجسم وكفي الأرجل",
        "price": 65.00,
        "description": (
            "مقشر فاخر مصنوع يدويًا من أجود المكونات الطبيعية، "
            "برائحة الورد والياسمين والمسك الأبيض التي تمنحكِ إحساسًا بالانتعاش والأناقة. "
            "يعمل على تقشير الجلد الميت بلطف، وتوحيد لون البشرة، وعلاج التشققات في الكعبين والكفين. "
            "يحفّز إنتاج الكولاجين لمنح بشرتكِ نضارة وشبابًا دائمًا. "
            "مناسب للاستخدام الأسبوعي على جميع أنواع البشرة. "
            "المكونات: زبدة الشيا، زبدة الكاكاو، زيت اللوز، زيت جوز الهند، "
            "فيتامين E، زيت عطري، BTMS، حبيبات تقشير طبيعية. "
            "الحجم: 300 غرام."
        ),
        "tags": "مقشر,جسم,أرجل,ورد,ياسمين,بشرة,كولاجين,تشققات",
        "active": True,
    },
    {
        "name": "فرطب طبيعي للجسم - Lotion Bar",
        "price": 55.00,
        "description": (
            "مرطب جسم صلب فريد من نوعه، يذوب عند ملامسة الجلد ليمنحكِ ترطيبًا عميقًا وفوريًا. "
            "برائحة النيرولي واللافندر الهادئة التي تريح الأعصاب وتجدد النشاط. "
            "يُليّن البشرة الجافة والمتشققة، ويساعد على مقاومة علامات الشيخوخة، "
            "ويوفر طبقة خفيفة من الحماية من الشمس. "
            "مثالي لليدين والقدمين والجسم كاملاً. "
            "المكونات: زبدة الكوكوم، زبدة الشيا، زبدة الكاكاو، زيت الجوجوبا، "
            "زيت اللوز، شمع الكانديلا، فيتامين E."
        ),
        "tags": "مرطب,لوشن,جسم,أيدي,أرجل,نيرولي,لافندر,تشققات,ترطيب",
        "active": True,
    },
    {
        "name": "مزيل العرق الطبيعي",
        "price": 45.00,
        "description": (
            "مزيل عرق طبيعي 100% خالٍ من المواد الكيميائية الضارة، "
            "برائحة العسل والكراميل الدافئة التي تدوم طوال اليوم. "
            "يمنحكِ انتعاشًا حقيقيًا دون أن يترك آثارًا بيضاء على ملابسكِ. "
            "يعتني ببشرة الإبط ويحافظ على صحتها ونعومتها. "
            "آمن للبشرة الحساسة ومناسب للاستخدام اليومي. "
            "المكونات: زبدة الكوكوم، زبدة الشيا، زيت الجوجوبا، زيت اللوز، "
            "شمع الكانديلا، فيتامين E، زيت أثيري. "
            "الحجم: 45 غرام."
        ),
        "tags": "مزيل عرق,طبيعي,عسل,كراميل,انتعاش,بشرة",
        "active": True,
    },
]

# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

def main() -> None:
    print("🌿 ALYASMEEN AuntOps — بدء إضافة المنتجات\n")

    # Safety check — do not insert if products already exist
    existing = query("SELECT COUNT(*) AS cnt FROM products")
    count = existing[0]["cnt"] if existing else 0

    if int(count) > 0:
        print(f"⚠️  جدول المنتجات يحتوي على {count} منتج/ات بالفعل.")
        print("   لتجنب التكرار، لم يتم إضافة أي منتجات.")
        print("   إذا أردتِ إعادة الإضافة، احذفي المنتجات الحالية أولاً من لوحة التحكم.")
        return

    inserted = 0
    for product in PRODUCTS:
        row = execute_returning(
            """
            INSERT INTO products (name, price, description, tags, active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, price
            """,
            (
                product["name"],
                product["price"],
                product["description"],
                product["tags"],
                product["active"],
            ),
        )
        if row:
            print(f"✅ تمت الإضافة: [{row['id']}] {row['name']} — {row['price']}₪")
            inserted += 1
        else:
            print(f"❌ فشل إضافة: {product['name']}")

    print(f"\n✅ {inserted} منتجات تم إضافتها بنجاح")


if __name__ == "__main__":
    main()
