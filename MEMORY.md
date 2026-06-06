# Project Memory — Khaled's Notes

This file is my persistent memory across sessions.
Each session's notes are saved here with a date stamp.
Ask me "what's my memory?" at the start of any session and I'll read it back.

---

<!-- Sessions are added below, newest first -->

---

## Session: 2026-06-06 — Evaluation Dataset Plan

**Topic:** Building a 40K–60K evaluation dataset for the ALYASMEEN WhatsApp ordering bot before going to real production.

**Key decisions made:**
- Target dialect: Israeli Arabic ("Hebraic" variety) — Levantine Arabic base with heavy Hebrew loanwords. NOT West Bank/Gaza Arabic. Specifically targeting Galilee (Nazareth, Sakhnin) and Triangle (Umm al-Fahm, Taibeh) speakers.
- Dataset size target: 50,000 conversations (40K–60K range)
- Dataset format: JSONL, one conversation per line, JSON schema with dialog_id, metadata (region, age_group, hebrew_switching_level, intent), and turns array (turn_id, speaker, message, intent, entities, slots_filled/missing, hebrew_tokens, gold_response)

**Dialect notes (critical for data quality):**
- Hebrew words customers WILL use in ordering context: b'seder (okay), mishloa'h (delivery), mehir (price), hanaha (discount), Bit/Paybox (payment apps), kartis ashrai (credit card)
- Addresses will often have Hebrew street names (rehov, ir)
- Triangle region has heavier Hebrew mixing than Galilee
- Code-switching: customers write Hebrew words in Arabic script, Hebrew script, or mix both
- Younger speakers (15–35) code-switch much more than older ones

**14 intents to cover:** browse_products, product_inquiry, add_to_cart, view_cart, clear_cart, set_fulfillment, provide_address, confirm_order, check_order_status, complaint, payment_inquiry, cancel_order, faq, off_topic

**Dataset distribution strategy:**
- 60% Happy Path (standard ordering flows)
- 25% Error Recovery (wrong product name, incomplete address, empty cart confirm, etc.)
- 10% Edge Cases (heavy Hebrew mixing, misspellings, complex multi-product orders)
- 5% Adversarial (prompt injection, offensive, off-topic, gibberish)

**Evaluation metrics chosen (NOT BLEU — it's bad for dialogue):**
- Task Completion Rate ≥ 85% (primary)
- Intent Accuracy ≥ 90%
- Slot F1 ≥ 88%
- Entity Match Rate ≥ 80%
- Human eval on 5 dimensions (1–5 scale, 2 raters, Kappa > 0.80)
- LLM-as-judge (Claude) for scalable automated scoring

**Generation pipeline:**
1. Phase 1: 1,000 manually written seed conversations (native Israeli Arab Arabic speakers)
2. Phase 2: LLM expansion (Claude/GPT-4o) × 30 = 30,000+ synthetic
3. Phase 3: Auto QC (JSON validation, dedup, LLM-judge ≥ 3/5) + human spot-check 10%
4. Phase 4: Real traffic augmentation once any test users exist

**Tools:** Label Studio (annotation UI), DVC + Git LFS (versioning), sentence-transformers (dedup), Claude API (generation + judge)

**Next steps to discuss:**
- Where to store the dataset (local files vs. Supabase vs. HuggingFace)
- Whether to build a test harness that runs the bot against the eval set automatically
- Who writes the 1,000 seed conversations — Khaled? native speaker annotators?
- Budget estimate for LLM generation of 50K conversations
