"""
Generate a noise-augmented dataset for ALYASMEEN bot robustness testing.

Strategy
--------
Take the 75 base examples, apply 8 noise levels (10%–80%), and produce
~700 variants per (base_id × noise_level) slot → ~420,000 combinations,
sampled down to TARGET_TOTAL (default 56,000 ≈ 75 × 8 × 93 rounded).

Each output record keeps the original expected_intent and entities so
you can run the bot and measure accuracy vs noise_level.

Noise operations (Arabic-specific)
------------------------------------
Characters affected = round(len(text) × noise_pct / 100)

At each noise level a mix of operations is applied:
  - delete_char          drop a random character
  - duplicate_char       repeat a random character (expressive elongation)
  - swap_adjacent        swap two adjacent characters
  - arabic_keyboard_typo replace with an adjacent Arabic keyboard key
  - drop_alef            remove ا/أ/إ/آ/ء → drop or replace with variant
  - taa_to_haa           ة → ه  (common WhatsApp shortcut)
  - insert_space         split a word mid-way
  - delete_space         merge two words
  - insert_char          inject a random Arabic character
  - replace_digit        swap Arabic-Indic ↔ Western digit

Output
------
tests/data/whatsapp_agent_dataset_noisy.json
  {
    "id":              int,          # globally unique
    "base_id":         int,          # original dataset id
    "noise_level_pct": int,          # 10 | 20 | … | 80
    "raw_input":       str,          # corrupted message
    "original_input":  str,          # original clean message
    "expected_intent": str,
    "language_profile":str,
    "entities":        dict,
    "edge_case_tags":  list,
    "noise_ops_applied": list[str]   # which operations were used
  }
"""

import json
import random
import math
import copy
import sys
from pathlib import Path

# ── constants ────────────────────────────────────────────────────────────────

NOISE_LEVELS = [10, 20, 30, 40, 50, 60, 70, 80]
TARGET_TOTAL = 56_000          # ~75 × 8 × 93
VARIANTS_PER_SLOT = math.ceil(TARGET_TOTAL / (75 * len(NOISE_LEVELS)))   # ≈ 93
SEED = 42

BASE_PATH = Path(__file__).parent / "whatsapp_agent_dataset.json"
OUT_PATH  = Path(__file__).parent / "whatsapp_agent_dataset_noisy.json"

# ── Arabic keyboard adjacency map (standard layout) ──────────────────────────
# Only includes the most common adjacency pairs on a standard Arabic QWERTY map.
KEYBOARD_NEIGHBORS: dict[str, list[str]] = {
    "ض": ["ص", "ق", "ع"],
    "ص": ["ض", "ث", "ع", "غ"],
    "ث": ["ص", "ق", "ف"],
    "ق": ["ض", "ث", "ف", "ظ"],
    "ف": ["ث", "ق", "غ", "ع"],
    "غ": ["ف", "ص", "ع", "ه"],
    "ع": ["غ", "ه", "خ"],
    "ه": ["ع", "خ", "ح"],
    "خ": ["ع", "ه", "ح", "ج"],
    "ح": ["خ", "ج"],
    "ج": ["خ", "ح", "د"],
    "ش": ["س", "ي", "ب"],
    "س": ["ش", "ي", "ن"],
    "ي": ["ش", "س", "ب", "ل"],
    "ب": ["ش", "ي", "ل", "ا"],
    "ل": ["ي", "ب", "ا", "ت"],
    "ا": ["ب", "ل", "ت"],
    "ت": ["ل", "ا", "ن"],
    "ن": ["س", "ت", "م"],
    "م": ["ن", "ك"],
    "ك": ["م", "د"],
    "د": ["ج", "ك", "ذ"],
    "ذ": ["د", "ز"],
    "ز": ["ذ", "ر", "و"],
    "ر": ["ز", "و"],
    "و": ["ر", "ز"],
    "ط": ["ظ", "ز"],
    "ظ": ["ط", "ق"],
    "إ": ["أ", "ا"],
    "أ": ["إ", "ا", "ء"],
    "ء": ["أ", "ئ"],
    "ئ": ["ء", "ي"],
    "ة": ["ه", "ت"],
}

ARABIC_CHARS = list("ابتثجحخدذرزسشصضطظعغفقكلمنهوي")
ALEF_VARIANTS = ["ا", "أ", "إ", "آ", "ء"]
DIGIT_MAP     = {"0": "٠", "1": "١", "2": "٢", "3": "٣", "4": "٤",
                 "5": "٥", "6": "٦", "7": "٧", "8": "٨", "9": "٩"}
DIGIT_MAP_R   = {v: k for k, v in DIGIT_MAP.items()}

# ── individual noise operations ───────────────────────────────────────────────

def delete_char(text: str, rng: random.Random) -> tuple[str, str]:
    if not text:
        return text, "delete_char_noop"
    i = rng.randint(0, len(text) - 1)
    return text[:i] + text[i + 1:], "delete_char"


def duplicate_char(text: str, rng: random.Random) -> tuple[str, str]:
    if not text:
        return text, "duplicate_char_noop"
    i = rng.randint(0, len(text) - 1)
    return text[:i] + text[i] * rng.randint(2, 4) + text[i + 1:], "duplicate_char"


def swap_adjacent(text: str, rng: random.Random) -> tuple[str, str]:
    if len(text) < 2:
        return text, "swap_adjacent_noop"
    i = rng.randint(0, len(text) - 2)
    lst = list(text)
    lst[i], lst[i + 1] = lst[i + 1], lst[i]
    return "".join(lst), "swap_adjacent"


def arabic_keyboard_typo(text: str, rng: random.Random) -> tuple[str, str]:
    candidates = [(i, c) for i, c in enumerate(text) if c in KEYBOARD_NEIGHBORS]
    if not candidates:
        return text, "keyboard_typo_noop"
    i, c = rng.choice(candidates)
    replacement = rng.choice(KEYBOARD_NEIGHBORS[c])
    return text[:i] + replacement + text[i + 1:], "arabic_keyboard_typo"


def drop_alef(text: str, rng: random.Random) -> tuple[str, str]:
    candidates = [(i, c) for i, c in enumerate(text) if c in ALEF_VARIANTS]
    if not candidates:
        return text, "drop_alef_noop"
    i, c = rng.choice(candidates)
    action = rng.choice(["drop", "swap"])
    if action == "drop":
        return text[:i] + text[i + 1:], "drop_alef"
    else:
        replacement = rng.choice([v for v in ALEF_VARIANTS if v != c])
        return text[:i] + replacement + text[i + 1:], "alef_variant_swap"


def taa_to_haa(text: str, rng: random.Random) -> tuple[str, str]:
    candidates = [i for i, c in enumerate(text) if c == "ة"]
    if not candidates:
        return text, "taa_to_haa_noop"
    i = rng.choice(candidates)
    return text[:i] + "ه" + text[i + 1:], "taa_to_haa"


def insert_space(text: str, rng: random.Random) -> tuple[str, str]:
    # split a word mid-way
    words = text.split()
    long_words = [(i, w) for i, w in enumerate(words) if len(w) >= 4]
    if not long_words:
        return text, "insert_space_noop"
    wi, word = rng.choice(long_words)
    split_at = rng.randint(2, len(word) - 2)
    words[wi] = word[:split_at] + " " + word[split_at:]
    return " ".join(words), "insert_space"


def delete_space(text: str, rng: random.Random) -> tuple[str, str]:
    spaces = [i for i, c in enumerate(text) if c == " "]
    if not spaces:
        return text, "delete_space_noop"
    i = rng.choice(spaces)
    return text[:i] + text[i + 1:], "delete_space"


def insert_random_char(text: str, rng: random.Random) -> tuple[str, str]:
    if not text:
        return text, "insert_char_noop"
    i = rng.randint(0, len(text))
    c = rng.choice(ARABIC_CHARS)
    return text[:i] + c + text[i:], "insert_char"


def flip_digit(text: str, rng: random.Random) -> tuple[str, str]:
    western = [i for i, c in enumerate(text) if c in DIGIT_MAP]
    indic   = [i for i, c in enumerate(text) if c in DIGIT_MAP_R]
    candidates = western + indic
    if not candidates:
        return text, "flip_digit_noop"
    i = rng.choice(candidates)
    c = text[i]
    replacement = DIGIT_MAP.get(c) or DIGIT_MAP_R.get(c, c)
    return text[:i] + replacement + text[i + 1:], "flip_digit"


ALL_OPS = [
    delete_char,
    duplicate_char,
    swap_adjacent,
    arabic_keyboard_typo,
    drop_alef,
    taa_to_haa,
    insert_space,
    delete_space,
    insert_random_char,
    flip_digit,
]

# weights: higher = more common in real WhatsApp messages
OP_WEIGHTS = [15, 10, 10, 12, 18, 12, 5, 8, 10, 5]

# ── core corruption function ──────────────────────────────────────────────────

def corrupt(text: str, noise_pct: int, rng: random.Random) -> tuple[str, list[str]]:
    """Apply noise_pct% worth of operations to text. Returns (corrupted, ops_used)."""
    n_ops = max(1, round(len(text) * noise_pct / 100))
    ops_used = []
    for _ in range(n_ops):
        op = rng.choices(ALL_OPS, weights=OP_WEIGHTS, k=1)[0]
        text, op_name = op(text, rng)
        if not op_name.endswith("_noop"):
            ops_used.append(op_name)
    return text, ops_used


# ── main generation ───────────────────────────────────────────────────────────

def generate(base_path: Path, out_path: Path, target: int, seed: int) -> None:
    rng = random.Random(seed)

    with open(base_path, encoding="utf-8") as f:
        base_examples = json.load(f)

    records = []
    global_id = 1

    slots = [(ex, lvl) for ex in base_examples for lvl in NOISE_LEVELS]
    variants_per_slot = math.ceil(target / len(slots))

    print(f"Base examples : {len(base_examples)}")
    print(f"Noise levels  : {NOISE_LEVELS}")
    print(f"Slots         : {len(slots)}")
    print(f"Variants/slot : {variants_per_slot}")
    print(f"Expected total: ~{len(slots) * variants_per_slot:,}")

    for ex, lvl in slots:
        for _ in range(variants_per_slot):
            corrupted, ops = corrupt(ex["raw_input"], lvl, rng)
            record = {
                "id":               global_id,
                "base_id":          ex["id"],
                "noise_level_pct":  lvl,
                "raw_input":        corrupted,
                "original_input":   ex["raw_input"],
                "expected_intent":  ex["expected_intent"],
                "language_profile": ex["language_profile"],
                "entities":         copy.deepcopy(ex["entities"]),
                "edge_case_tags":   list(ex["edge_case_tags"]) + [f"noise_{lvl}pct"],
                "noise_ops_applied": ops,
            }
            records.append(record)
            global_id += 1

    # trim to target if slightly over
    records = records[:target]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(records):,} records -> {out_path}")

    # quick stats
    by_level: dict[int, int] = {}
    for r in records:
        by_level[r["noise_level_pct"]] = by_level.get(r["noise_level_pct"], 0) + 1
    print("\nDistribution by noise level:")
    for lvl in sorted(by_level):
        print(f"  {lvl:3}% -> {by_level[lvl]:,} examples")


if __name__ == "__main__":
    target = int(sys.argv[1]) if len(sys.argv) > 1 else TARGET_TOTAL
    generate(BASE_PATH, OUT_PATH, target, SEED)
