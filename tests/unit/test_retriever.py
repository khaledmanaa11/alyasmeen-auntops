"""
test_retriever.py — Unit tests for app/ai/retriever.py

Tests product catalog caching, normalization, keyword search,
and product lookup by SKU/name. All Supabase calls are mocked.
"""
import pytest

FAKE_PRODUCTS = [
    {
        "id": 1,
        "name": "كريم اليدين",
        "price": 25.0,
        "description": "كريم مرطب للأيدي الجافة",
        "tags": "ترطيب,يدين",
        "active": True,
    },
    {
        "id": 2,
        "name": "لوشن الجسم",
        "price": 40.0,
        "description": "لوشن طبيعي للجسم",
        "tags": "ترطيب,جسم",
        "active": True,
    },
    {
        "id": 3,
        "name": "شمعة العود",
        "price": 35.0,
        "description": "شمعة عطرية بعطر العود",
        "tags": "شموع,عطر",
        "active": True,
    },
]


@pytest.fixture(autouse=True)
def reset_catalog():
    """Reset the cached catalog before each test."""
    import app.ai.retriever as r

    r.invalidate_catalog()
    yield
    r.invalidate_catalog()


@pytest.fixture()
def mock_catalog(monkeypatch):
    import app.ai.retriever as r

    monkeypatch.setattr(r, "_CATALOG", list(FAKE_PRODUCTS))


class TestInvalidateCatalog:
    def test_sets_catalog_to_none(self):
        import app.ai.retriever as r

        r._CATALOG = [{"id": 1}]
        r.invalidate_catalog()
        assert r._CATALOG is None


class TestNormalize:
    def test_lowercases(self):
        from app.ai.retriever import _normalize

        assert _normalize("Hello") == "hello"

    def test_strips_whitespace(self):
        from app.ai.retriever import _normalize

        assert _normalize("  test  ") == "test"

    def test_handles_none_like_empty(self):
        from app.ai.retriever import _normalize

        result = _normalize(None)
        assert result == ""

    def test_arabic_preserved(self):
        from app.ai.retriever import _normalize

        result = _normalize("كريم")
        assert "كريم" in result


class TestSearchProducts:
    def test_returns_all_when_no_query(self, monkeypatch):
        import app.ai.retriever as r

        monkeypatch.setattr(r, "_CATALOG", list(FAKE_PRODUCTS))
        results = r.search_products(None, None)
        assert len(results) > 0

    def test_keyword_match_in_name(self, monkeypatch):
        import app.ai.retriever as r

        monkeypatch.setattr(r, "_CATALOG", list(FAKE_PRODUCTS))
        results = r.search_products("كريم", None)
        names = [res["name"] for res in results]
        assert "كريم اليدين" in names

    def test_keyword_match_in_description(self, monkeypatch):
        import app.ai.retriever as r

        monkeypatch.setattr(r, "_CATALOG", list(FAKE_PRODUCTS))
        results = r.search_products("عطرية", None)
        assert len(results) >= 1

    def test_no_match_returns_empty(self, monkeypatch):
        import app.ai.retriever as r

        monkeypatch.setattr(r, "_CATALOG", list(FAKE_PRODUCTS))
        results = r.search_products("بيتزا", None)
        assert results == []

    def test_empty_catalog_returns_empty(self, monkeypatch):
        import app.ai.retriever as r

        monkeypatch.setattr(r, "_CATALOG", [])
        results = r.search_products("كريم", None)
        assert results == []

    def test_limits_results_to_12(self, monkeypatch):
        import app.ai.retriever as r

        big_catalog = [
            {"sku": str(i), "name": f"product {i}", "price": 10.0, "description": "test", "tags": []}
            for i in range(20)
        ]
        monkeypatch.setattr(r, "_CATALOG", big_catalog)
        results = r.search_products("product", None)
        assert len(results) <= 12


class TestDescribeProduct:
    def test_finds_by_exact_name(self, monkeypatch):
        import app.ai.retriever as r

        monkeypatch.setattr(r, "_CATALOG", list(FAKE_PRODUCTS))
        result = r.describe_product("كريم اليدين")
        assert result.get("name") == "كريم اليدين"

    def test_returns_empty_for_unknown(self, monkeypatch):
        import app.ai.retriever as r

        monkeypatch.setattr(r, "_CATALOG", list(FAKE_PRODUCTS))
        result = r.describe_product("منتج غير موجود")
        assert result == {}
