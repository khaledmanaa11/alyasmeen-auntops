# Graph Report - .  (2026-06-14)

## Corpus Check
- Large corpus: 109 files · ~4,726,147 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 787 nodes · 1211 edges · 58 communities (41 shown, 17 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 46 edges (avg confidence: 0.62)
- Token cost: 170,383 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_WhatsApp Bot Brain & Sessions|WhatsApp Bot Brain & Sessions]]
- [[_COMMUNITY_API Gatekeeper & Rate Limiting|API Gatekeeper & Rate Limiting]]
- [[_COMMUNITY_Product Retriever & DB Client|Product Retriever & DB Client]]
- [[_COMMUNITY_App Bootstrap & Orders API Tests|App Bootstrap & Orders API Tests]]
- [[_COMMUNITY_Intent Eval & Broadcast AI|Intent Eval & Broadcast AI]]
- [[_COMMUNITY_AI Service & Architecture Decisions|AI Service & Architecture Decisions]]
- [[_COMMUNITY_Database Layer Tests|Database Layer Tests]]
- [[_COMMUNITY_AI Service Tests|AI Service Tests]]
- [[_COMMUNITY_Config & Config Tests|Config & Config Tests]]
- [[_COMMUNITY_WhatsApp Bot Tests|WhatsApp Bot Tests]]
- [[_COMMUNITY_Product Lookup & Retriever Tests|Product Lookup & Retriever Tests]]
- [[_COMMUNITY_Noise Dataset Generator|Noise Dataset Generator]]
- [[_COMMUNITY_Constants Tests|Constants Tests]]
- [[_COMMUNITY_Multi-Agent Pipeline|Multi-Agent Pipeline]]
- [[_COMMUNITY_Bot Flow Integration Tests|Bot Flow Integration Tests]]
- [[_COMMUNITY_Frontend Pipeline|Frontend Pipeline]]
- [[_COMMUNITY_Project Docs & Catalog Tools|Project Docs & Catalog Tools]]
- [[_COMMUNITY_PDF Invoice Generator|PDF Invoice Generator]]
- [[_COMMUNITY_Retry Queue Tests|Retry Queue Tests]]
- [[_COMMUNITY_Monthly Report Tests|Monthly Report Tests]]
- [[_COMMUNITY_Web Dashboard UI Router|Web Dashboard UI Router]]
- [[_COMMUNITY_Products API Tests|Products API Tests]]
- [[_COMMUNITY_WhatsApp Meta Tests|WhatsApp Meta Tests]]
- [[_COMMUNITY_Broadcast Improve JS Client|Broadcast Improve JS Client]]
- [[_COMMUNITY_WhatsApp Meta Sender|WhatsApp Meta Sender]]
- [[_COMMUNITY_Follow-up Tests|Follow-up Tests]]
- [[_COMMUNITY_Monthly Report & Webhook|Monthly Report & Webhook]]
- [[_COMMUNITY_Mock WhatsApp Dev Sender|Mock WhatsApp Dev Sender]]
- [[_COMMUNITY_Follow-up Service|Follow-up Service]]
- [[_COMMUNITY_WhatsApp Dev Tests|WhatsApp Dev Tests]]
- [[_COMMUNITY_UI Page Route Tests|UI Page Route Tests]]
- [[_COMMUNITY_Monthly Report Builder Tests|Monthly Report Builder Tests]]
- [[_COMMUNITY_Product Creation Tests|Product Creation Tests]]
- [[_COMMUNITY_Retry Action Dispatch|Retry Action Dispatch]]
- [[_COMMUNITY_Broadcast API Tests|Broadcast API Tests]]
- [[_COMMUNITY_PDF Retry Action Tests|PDF Retry Action Tests]]
- [[_COMMUNITY_Webhook Verify Tests|Webhook Verify Tests]]
- [[_COMMUNITY_Tech Stack & Dependencies|Tech Stack & Dependencies]]
- [[_COMMUNITY_Product Toggle Tests|Product Toggle Tests]]
- [[_COMMUNITY_Pytest Fixtures|Pytest Fixtures]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 56|Community 56]]

## God Nodes (most connected - your core abstractions)
1. `Config` - 41 edges
2. `query()` - 40 edges
3. `execute()` - 29 edges
4. `Random` - 18 edges
5. `_phone()` - 18 edges
6. `webhook_post()` - 16 edges
7. `_is_authenticated()` - 15 edges
8. `execute_returning()` - 14 edges
9. `Request` - 14 edges
10. `run_pipeline()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Catalog editor HTML tool` --semantically_similar_to--> `Supabase (PostgreSQL over HTTPS RPC)`  [INFERRED] [semantically similar]
  catalog_editor.html → .planning/codebase/INTEGRATIONS.md
- `Path` --uses--> `Config`  [INFERRED]
  agents/frontend_pipeline.py → app/services/config.py
- `AsyncAnthropic` --uses--> `Config`  [INFERRED]
  agents/frontend_pipeline.py → app/services/config.py
- `Path` --uses--> `Config`  [INFERRED]
  agents/pipeline.py → app/services/config.py
- `AsyncAnthropic` --uses--> `Config`  [INFERRED]
  agents/pipeline.py → app/services/config.py

## Import Cycles
- 1-file cycle: `tests/data/eval_intent.py -> tests/data/eval_intent.py`

## Hyperedges (group relationships)
- **AI knowledge base injected into Claude context** — knowledge_about_store, knowledge_ingredients_faq, knowledge_returns_policy, knowledge_shipping_policy, knowledge_skin_advice, knowledge_store_info, concept_claude_api [INFERRED 0.85]
- **Inbound WhatsApp message handling flow** — concept_session_state_machine, concept_agentic_tool_executor, concept_whatsapp_sender_swap, concept_db_adapter [INFERRED 0.85]
- **Codebase analysis documents (map-codebase output)** — codebase_architecture, codebase_structure, codebase_stack, codebase_conventions, codebase_integrations, codebase_concerns, codebase_testing [EXTRACTED 1.00]
- **Prompt engineering & data optimization sprint (catalog injection + XML prompt + knowledge base + aliases)** — full_catalog_injection, docs_prompts_system_prompt, knowledge_base, aliases_column [EXTRACTED 0.95]
- **Agentic tool-use loop spanning AI service, callback, router and retriever** — ai_service_concept, tool_executor_callback, whatsapp_router_concept, retriever_concept [EXTRACTED 0.85]
- **Five dashboard templates sharing the premium RTL design system** — templates_broadcast, templates_dashboard, templates_orders, templates_products, premium_design_system [EXTRACTED 0.95]

## Communities (58 total, 17 thin omitted)

### Community 0 - "WhatsApp Bot Brain & Sessions"
Cohesion: 0.07
Nodes (42): Search the product catalog by keyword and/or category.      Performs a substring, search_products(), Any, execute(), Run INSERT / UPDATE / DELETE.  Returns nothing., append_history(), clear_session(), get_customer_name() (+34 more)

### Community 1 - "API Gatekeeper & Rate Limiting"
Cohesion: 0.07
Nodes (25): Any, Path, ApiGatekeeper, _load_rate_config(), gatekeeper.py — Centralized external API call manager for ALYASMEEN AuntOps.  Al, Centralized external API call manager.      Enforces rate limits, handles retrie, Load rate limit config and initialise per-service buckets.          Args:, Return the rate-limit bucket for a service, creating a default if unknown. (+17 more)

### Community 2 - "Product Retriever & DB Client"
Cohesion: 0.09
Nodes (43): invalidate_catalog(), _load_catalog(), Product search module — loads active products from Supabase and provides keyword, Call this after any product create/update/delete so the bot picks up changes., Load active products from the Supabase products table.      Queries all rows whe, Any, Request, Client (+35 more)

### Community 3 - "App Bootstrap & Orders API Tests"
Cohesion: 0.05
Nodes (17): _all_exception_handler(), Request, Exception, auth_client(), mock_order(), test_orders_api.py — Integration tests for the orders API.  Tests the order stat, Return a client with a valid session cookie injected directly.      Computing th, Patch db.query and db.execute so no real Supabase call is made. (+9 more)

### Community 4 - "Intent Eval & Broadcast AI"
Cohesion: 0.07
Nodes (37): _catalog(), Return the cached product catalog, loading it from Supabase on first call., Anthropic, BaseModel, classify_intent(), main(), _near_miss(), print_report() (+29 more)

### Community 5 - "AI Service & Architecture Decisions"
Cohesion: 0.08
Nodes (37): ai_service.py — single AI file, products.aliases column (bilingual matching), AI broadcast message improvement feature, broadcast_improve.js client, database.py — Supabase HTTPS client, Architecture & Planning Document (PLAN.md), ADR-002 Claude Haiku as AI model, ADR-003 FastAPI over Flask or Django (+29 more)

### Community 6 - "Database Layer Tests"
Cohesion: 0.06
Nodes (7): test_database.py — Unit tests for app/db/database.py  Tests the SQL escaping and, Tests for the public query/execute/execute_returning functions with mock client., Tests for _escape() — converts Python values to safe SQL literals., Tests for _build() — substitutes %s placeholders with escaped values., TestBuild, TestEscape, TestQueryAndExecute

### Community 7 - "AI Service Tests"
Cohesion: 0.09
Nodes (11): _build_messages(), _is_arabic(), Build the messages list for Claude API (no system role in messages list)., _make_mock_anthropic(), test_ai_service.py — Unit tests for app/services/ai_service.py  Tests prompt bui, When customer_name is provided the system prompt should include it., Return a fake Anthropic class whose messages.create returns reply_text., TestAiAvailable (+3 more)

### Community 8 - "Config & Config Tests"
Cohesion: 0.09
Nodes (12): _bool(), _load_json_config(), config.py — Central configuration for ALYASMEEN AuntOps. All environment variabl, Convert an environment variable string to a boolean.      Returns True for the s, Load a JSON config file relative to the project root. Returns {} on error., test_config.py — Unit tests for app/services/config.py  Verifies that Config loa, Tests for the _bool() helper that converts env var strings to bool., Tests that Config reads environment variables at module load time. (+4 more)

### Community 9 - "WhatsApp Bot Tests"
Cohesion: 0.12
Nodes (8): _phone(), test_whatsapp.py — Unit tests for WhatsApp bot command handling.  Tests hard com, TestAddressFlow, TestCartContents, TestHardCommands, TestMenuAndSelection, TestOrderConfirmFlow, TestOrderTracking

### Community 10 - "Product Lookup & Retriever Tests"
Cohesion: 0.09
Nodes (11): describe_product(), _normalize(), Normalize Unicode text for case-insensitive matching.      Decomposes the string, Find a product by SKU or exact name.      Compares the normalized input against, test_retriever.py — Unit tests for app/ai/retriever.py  Tests product catalog ca, Reset the cached catalog before each test., reset_catalog(), TestDescribeProduct (+3 more)

### Community 11 - "Noise Dataset Generator"
Cohesion: 0.12
Nodes (22): arabic_keyboard_typo(), corrupt(), delete_char(), delete_space(), drop_alef(), duplicate_char(), flip_digit(), generate() (+14 more)

### Community 12 - "Constants Tests"
Cohesion: 0.08
Nodes (7): test_constants.py — Unit tests for app/shared/constants.py  Verifies all constan, TestArabicStatusLabels, TestFulfillmentTypes, TestHardCommands, TestNumericConstants, TestOrderStatuses, TestVersion

### Community 13 - "Multi-Agent Pipeline"
Cohesion: 0.14
Nodes (23): _load_context(), main(), AsyncAnthropic, Path, pipeline.py — ALYASMEEN AuntOps multi-agent pipeline.  Runs 5 agents in sequence, Developer: produces full file contents from the PM brief. Streams output., QA: checks the Developer's code against 8 rules. Returns PASS or FAIL + issues., DevOps: produces a deployment checklist for the approved code. (+15 more)

### Community 14 - "Bot Flow Integration Tests"
Cohesion: 0.13
Nodes (12): _phone(), test_bot_flow.py — Integration tests for the full WhatsApp bot conversation flow, When AUNT_PHONE is set, aunt should receive notification on confirm., When AUNT_PHONE is not set, no notification is sent to aunt., Messages that don't match any hard command fall through to AI., Full flow: menu → add product → pickup → confirm → get order ID., Full flow: menu → add → delivery → address → confirm → order ID., TestAIFallback (+4 more)

### Community 15 - "Frontend Pipeline"
Cohesion: 0.16
Nodes (18): _load_backend_output(), _load_existing_templates(), main(), AsyncAnthropic, Path, frontend_pipeline.py — ALYASMEEN AuntOps frontend-only pipeline.  Runs 2 agents:, Visual QA: checks the Frontend Dev's code against 10 UI/UX rules., Run the frontend-only 2-agent pipeline. (+10 more)

### Community 16 - "Project Docs & Catalog Tools"
Cohesion: 0.14
Nodes (20): Catalog editor HTML tool, Catalog product-entry template, CLAUDE.md project brief, Architecture (layered modular monolith), Concerns & Technical Debt, Code Conventions, External Integrations, Testing (+12 more)

### Community 17 - "PDF Invoice Generator"
Cohesion: 0.18
Nodes (8): generate_invoice_pdf(), _h(), Hebrew PDF Invoice Generator — replaces page_wave invoicing.  Generates a standa, Apply BiDi algorithm so fpdf2 renders Hebrew text right-to-left., Generate a Hebrew PDF invoice (Israeli חשבונית format) and return it as bytes., test_pdf_invoice.py — Unit tests for app/services/pdf_invoice.py  Tests that gen, TestBidiHelper, TestGenerateInvoicePdf

### Community 18 - "Retry Queue Tests"
Cohesion: 0.12
Nodes (6): mock_whatsapp_sender(), test_retry.py — Unit tests for retry_queue.py and retry_actions.py  Tests enqueu, Patch send_text in whatsapp_dev so no console output during tests., TestEnqueue, TestExecuteAction, TestProcessRetries

### Community 19 - "Monthly Report Tests"
Cohesion: 0.15
Nodes (9): _previous_month(), mock_db(), mock_whatsapp(), test_monthly_report.py — Unit tests for app/services/monthly_report.py  Tests re, Patch send_text so no real WhatsApp call is made., Patch query/execute in monthly_report so no real DB call is made., TestArabicMonths, TestPreviousMonth (+1 more)

### Community 20 - "Web Dashboard UI Router"
Cohesion: 0.27
Nodes (11): Request, broadcast_page(), dashboard_page(), _is_authenticated(), login_page(), login_submit(), _NoCache, orders_page() (+3 more)

### Community 21 - "Products API Tests"
Cohesion: 0.14
Nodes (4): test_ui_api.py — Integration tests for the products and broadcast API.  Tests pr, TestDeleteProduct, TestProductsListAPI, TestUpdateProduct

### Community 22 - "WhatsApp Meta Tests"
Cohesion: 0.14
Nodes (5): test_whatsapp_meta.py — Unit tests for app/services/whatsapp_meta.py  Tests the, TestSendDocumentBytesMocked, TestSendDocumentMocked, TestSendTextMockedRequests, TestVerifyGetSignature

### Community 23 - "Broadcast Improve JS Client"
Cohesion: 0.36
Nodes (8): applyPanelDirection(), closeModal(), hideSpinner(), openModal(), requestImprovement(), resetModalEditMode(), showSpinner(), showToast()

### Community 24 - "WhatsApp Meta Sender"
Cohesion: 0.22
Nodes (7): Print document link to console instead of sending via Meta API (mock).      Args, send_document(), WhatsApp Meta Cloud API sender — real production implementation. Sends text mess, Send a document by URL via the Meta Cloud API.      Falls back to the mock sende, Verify a Meta webhook GET request and optionally verify a POST signature.      F, send_document(), verify_get()

### Community 25 - "Follow-up Tests"
Cohesion: 0.20
Nodes (3): test_followup.py — Unit tests for app/services/followup.py  Tests record_deliver, TestRecordDelivery, TestSendFollowups

### Community 26 - "Monthly Report & Webhook"
Cohesion: 0.28
Nodes (8): Request, date, webhook_get(), Config, monthly_report.py — Monthly business summary sent to the aunt.  Runs on the 1st, Save full monthly stats to monthly_snapshots so the dashboard can show history., save_snapshot(), send_monthly_report()

### Community 27 - "Mock WhatsApp Dev Sender"
Cohesion: 0.22
Nodes (7): Mock WhatsApp sender for local development — prints messages to console instead, Print a text message to console instead of sending via Meta API (mock).      Arg, Mock interactive button message — prints to console and returns dict with button, Accept any webhook verification request in dev mode and echo the challenge., send_buttons(), send_text(), verify_get()

### Community 28 - "Follow-up Service"
Cohesion: 0.29
Nodes (7): followup.py — Post-purchase follow-up service.  Runs on a schedule (every 6 ho, Called from appsheet.py when a delivery is confirmed.     Inserts a row into fo, Finds all deliveries that happened 3+ days ago and haven't been followed up., record_delivery(), send_followups(), Send a text message via the Meta Cloud API.      Falls back to the mock sender i, send_text()

### Community 29 - "WhatsApp Dev Tests"
Cohesion: 0.29
Nodes (5): Print document info to console instead of uploading and sending via Meta API (mo, send_document_bytes(), Send an interactive button message via the Meta Cloud API.      Args:         to, send_buttons(), TestWhatsappDev

### Community 33 - "Retry Action Dispatch"
Cohesion: 0.40
Nodes (5): execute_action(), retry_actions.py — Dispatch logic for individual retry actions. Extracted from r, Execute one retry action.  Raises on any failure so the caller can record it., Upload PDF bytes to the Meta media API, then send as a WhatsApp document., send_document_bytes()

### Community 37 - "Tech Stack & Dependencies"
Cohesion: 0.67
Nodes (3): Technology Stack, requirements.txt (pip deps), runtime.txt (python-3.11.9)

## Knowledge Gaps
- **25 isolated node(s):** `Request`, `Exception`, `Any`, `Path`, `External Integrations` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Config` connect `Monthly Report & Webhook` to `Product Creation Tests`, `WhatsApp Bot Brain & Sessions`, `Product Retriever & DB Client`, `App Bootstrap & Orders API Tests`, `Broadcast API Tests`, `Intent Eval & Broadcast AI`, `Product Toggle Tests`, `Retry Action Dispatch`, `Config & Config Tests`, `Noise Dataset Generator`, `Multi-Agent Pipeline`, `Frontend Pipeline`, `Web Dashboard UI Router`, `Products API Tests`, `WhatsApp Meta Sender`, `Follow-up Service`, `UI Page Route Tests`?**
  _High betweenness centrality (0.283) - this node is a cross-community bridge._
- **Why does `query()` connect `Product Retriever & DB Client` to `WhatsApp Bot Brain & Sessions`, `Retry Action Dispatch`, `Monthly Report & Webhook`, `Follow-up Service`, `Monthly Report Builder Tests`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `Random` connect `Noise Dataset Generator` to `WhatsApp Bot Tests`, `Intent Eval & Broadcast AI`, `Bot Flow Integration Tests`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `Config` (e.g. with `AsyncAnthropic` and `Path`) actually correct?**
  _`Config` has 25 INFERRED edges - model-reasoned connections that need verification._
- **What connects `frontend_pipeline.py — ALYASMEEN AuntOps frontend-only pipeline.  Runs 2 agents:`, `Collect a brief inventory of existing templates so Frontend Dev can match styles`, `Load a previous backend pipeline output file as context for the Frontend Dev.` to the rest of the system?**
  _182 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `WhatsApp Bot Brain & Sessions` be split into smaller, more focused modules?**
  _Cohesion score 0.07393483709273183 - nodes in this community are weakly interconnected._
- **Should `API Gatekeeper & Rate Limiting` be split into smaller, more focused modules?**
  _Cohesion score 0.0653061224489796 - nodes in this community are weakly interconnected._