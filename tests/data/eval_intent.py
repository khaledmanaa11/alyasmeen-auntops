"""
eval_intent.py — ALYASMEEN bot robustness evaluator

Tests how well the bot understands customer messages at different noise levels.
Uses Claude Haiku (same model as the bot) to classify intent from each corrupted
message, then compares to the expected_intent label.

Usage
-----
# Quick run — 30 samples per noise level (240 API calls, ~$0.05 at Haiku prices)
python tests/data/eval_intent.py

# More samples for reliable numbers
python tests/data/eval_intent.py --samples 100

# Only specific noise levels
python tests/data/eval_intent.py --levels 10 30 50 80

# Save results to JSON for later analysis
python tests/data/eval_intent.py --out results.json

Cost estimate (Claude Haiku at ~$0.80/M input tokens)
------------------------------------------------------
  30 samples/level  × 8 levels = 240 calls ≈ $0.04–$0.06
 100 samples/level  × 8 levels = 800 calls ≈ $0.12–$0.18
 500 samples/level  × 8 levels = 4000 calls ≈ $0.60–$0.90
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from collections import defaultdict

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Load .env if present (for CLAUDE_API_KEY)
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# ── valid intents (from the 75 base examples) ────────────────────────────────
VALID_INTENTS = [
    "acknowledgment", "affirmation", "cancel_order", "check_availability",
    "check_delivery_cost_and_time", "check_delivery_zone",
    "check_delivery_zone_and_product_availability", "check_payment_methods",
    "check_product_availability", "check_product_availability_and_ingredients",
    "check_product_availability_and_price", "check_product_ingredients",
    "check_product_lifestyle_compliance", "check_product_medical_suitability",
    "check_product_safety", "check_restock_date", "clear_cart", "confirm_order",
    "correct_menu_selection", "create_custom_bulk_order_and_check_price",
    "create_order", "create_order_and_check_fulfillment",
    "create_order_and_check_ingredients", "create_order_and_check_logistics",
    "create_order_and_request_discount", "create_order_and_request_price",
    "create_order_with_gift_packaging_and_check_price",
    "duplicate_third_party_order", "greeting", "greeting_and_check_availability",
    "greeting_and_check_product_availability", "greeting_and_check_promotions",
    "modify_order_add_item_post_checkout", "modify_order_and_request_price",
    "modify_order_with_self_correction", "opt_out_of_messages",
    "order_by_image_reference", "positive_feedback", "price_objection",
    "privacy_concern", "report_damaged_item_and_request_resolution",
    "request_catalog_or_pricing", "request_deferred_payment",
    "request_human_handoff", "request_location_pin", "request_price_and_variants",
    "request_product_recommendation", "request_store_info",
    "resume_abandoned_cart_and_checkout", "select_menu_item",
    "select_menu_item_with_quantity", "set_fulfillment_delivery_with_address",
    "set_fulfillment_pickup", "submit_payment_proof",
    "thanks_and_close_conversation", "track_order_and_request_courier_contact",
    "track_order_with_complaint", "track_order_with_refund_threat",
    "unsupported_media_sticker", "unsupported_media_voice_note",
    "update_cart_quantity", "view_cart", "wholesale_inquiry", "wrong_recipient",
]

# Intents that are semantically close — partial credit for near-misses
NEAR_MISS_GROUPS = [
    {"greeting", "greeting_and_check_availability", "greeting_and_check_product_availability", "greeting_and_check_promotions"},
    {"create_order", "create_order_and_request_price", "create_order_and_check_fulfillment",
     "create_order_and_check_logistics", "create_order_and_check_ingredients",
     "create_order_and_request_discount", "create_order_with_gift_packaging_and_check_price",
     "create_custom_bulk_order_and_check_price"},
    {"modify_order_and_request_price", "modify_order_add_item_post_checkout", "modify_order_with_self_correction"},
    {"track_order_with_complaint", "track_order_and_request_courier_contact", "track_order_with_refund_threat"},
    {"check_product_availability", "check_product_availability_and_price",
     "check_product_availability_and_ingredients", "check_product_safety",
     "check_product_ingredients", "check_product_lifestyle_compliance",
     "check_product_medical_suitability"},
    {"acknowledgment", "affirmation", "thanks_and_close_conversation"},
    {"unsupported_media_voice_note", "unsupported_media_sticker", "order_by_image_reference"},
    {"view_cart", "clear_cart"},
    {"set_fulfillment_pickup", "set_fulfillment_delivery_with_address"},
]

def _near_miss(predicted: str, expected: str) -> bool:
    for group in NEAR_MISS_GROUPS:
        if predicted in group and expected in group:
            return True
    return False


# ── classification prompt ─────────────────────────────────────────────────────
CLASSIFY_SYSTEM = """You are an intent classifier for a WhatsApp ordering bot.
The bot sells natural skincare products and candles to customers in Palestine.
Messages are in Arabic (Levantine dialect), English, Arabizi, or a mix.
Some messages have typos, missing letters, or phonetic Hebrew loanwords — that is normal.

Respond with ONLY the intent label from this list, nothing else:
""" + "\n".join(f"- {i}" for i in VALID_INTENTS)

CLASSIFY_TEMPLATE = "Customer message: {msg}\nIntent:"


def classify_intent(client: Anthropic, model: str, message: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=30,
                temperature=0.0,
                system=CLASSIFY_SYSTEM,
                messages=[{"role": "user", "content": CLASSIFY_TEMPLATE.format(msg=message)}],
            )
            raw = (resp.content[0].text or "").strip().strip("-").strip()
            # normalise — strip leading spaces, take first word if Claude added explanation
            predicted = raw.split()[0].split("\n")[0] if raw else "unknown"
            return predicted if predicted in VALID_INTENTS else raw
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                return f"ERROR:{e}"
    return "unknown"


# ── report rendering ──────────────────────────────────────────────────────────

def print_report(results: dict, samples_per_level: int) -> None:
    levels = sorted(results.keys())
    print("\n" + "=" * 70)
    print("  ALYASMEEN BOT — Intent Classification Accuracy vs Noise Level")
    print("=" * 70)
    print(f"{'Level':>8}  {'Exact':>8}  {'Near-miss':>10}  {'Total':>7}")
    print("-" * 70)

    for lvl in levels:
        rows = results[lvl]
        n = len(rows)
        exact = sum(1 for r in rows if r["exact_match"])
        near  = sum(1 for r in rows if r["near_miss"] and not r["exact_match"])
        pct_exact = 100 * exact / n if n else 0
        pct_near  = 100 * near  / n if n else 0
        bar_e = "█" * int(pct_exact / 5)
        bar_n = "░" * int(pct_near  / 5)
        print(f"  {lvl:3}%    {pct_exact:5.1f}%  ({bar_e}{bar_n}) {pct_near:5.1f}% near   n={n}")

    print("=" * 70)

    # worst intents
    fail_counts: dict[str, int] = defaultdict(int)
    for lvl in levels:
        for r in results[lvl]:
            if not r["exact_match"] and not r["near_miss"]:
                fail_counts[r["expected"]] += 1
    if fail_counts:
        print("\nTop 10 intents with most misclassifications:")
        for intent, count in sorted(fail_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {count:4}x  {intent}")

    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate intent classification accuracy vs noise level")
    parser.add_argument("--samples", type=int, default=30, metavar="N",
                        help="Samples per noise level (default: 30)")
    parser.add_argument("--levels", type=int, nargs="+", default=[10, 20, 30, 40, 50, 60, 70, 80],
                        metavar="L", help="Noise levels to test (default: all 8)")
    parser.add_argument("--seed", type=int, default=99, help="Random seed for sampling")
    parser.add_argument("--out", type=str, default=None, help="Save raw results to JSON file")
    parser.add_argument("--model", type=str, default=None, help="Model override (default: CLAUDE_MODEL env var or haiku)")
    args = parser.parse_args()

    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        print("ERROR: CLAUDE_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    model = args.model or os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    client = Anthropic(api_key=api_key)

    noisy_path = Path(__file__).parent / "whatsapp_agent_dataset_noisy.json"
    if not noisy_path.exists():
        print(f"ERROR: {noisy_path} not found.")
        print("Run: python tests/data/generate_noise_dataset.py")
        sys.exit(1)

    print(f"Loading dataset from {noisy_path.name} ...")
    all_examples = json.loads(noisy_path.read_text(encoding="utf-8"))

    # Group by noise level
    by_level: dict[int, list[dict]] = defaultdict(list)
    for ex in all_examples:
        by_level[ex["noise_level_pct"]].append(ex)

    rng = random.Random(args.seed)
    total_calls = args.samples * len(args.levels)
    print(f"Model         : {model}")
    print(f"Samples/level : {args.samples}")
    print(f"Levels        : {args.levels}")
    print(f"Total API calls: {total_calls}")
    print()

    results: dict[int, list[dict]] = {}
    call_n = 0

    for lvl in sorted(args.levels):
        pool = by_level.get(lvl, [])
        if not pool:
            print(f"[{lvl}%] No examples found, skipping.")
            continue

        sample = rng.sample(pool, min(args.samples, len(pool)))
        level_results = []

        for ex in sample:
            call_n += 1
            predicted = classify_intent(client, model, ex["raw_input"])
            exact     = predicted == ex["expected_intent"]
            near      = _near_miss(predicted, ex["expected_intent"])

            level_results.append({
                "base_id":   ex["base_id"],
                "noise_pct": lvl,
                "message":   ex["raw_input"],
                "original":  ex["original_input"],
                "expected":  ex["expected_intent"],
                "predicted": predicted,
                "exact_match": exact,
                "near_miss": near,
            })

            status = "OK" if exact else ("~" if near else "X")
            pct_done = 100 * call_n / total_calls
            print(f"[{lvl}%] [{pct_done:4.0f}%] {status}  exp={ex['expected_intent'][:30]:<30}  got={predicted[:30]}")

        results[lvl] = level_results

    print_report(results, args.samples)

    if args.out:
        out_path = Path(args.out)
        flat = [row for rows in results.values() for row in rows]
        out_path.write_text(json.dumps(flat, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Raw results saved to {out_path}")


if __name__ == "__main__":
    main()
