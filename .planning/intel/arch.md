---
updated_at: "2026-06-14T00:00:00Z"
---

## Architecture Overview

The project is currently a **Modular Monolith** using FastAPI and Supabase. It is in the middle of a transition to a **Production-Ready Architecture** characterized by a split into two operational roles:
1. **Web Process**: Handles HTTP ingress (webhooks, dashboard UI, and JSON APIs).
2. **Worker Process**: Manages durable background tasks (AI processing via Anthropic, Meta API calls, invoice generation, and scheduled jobs).

The system relies on **Supabase PostgreSQL** as the system of record and transaction boundary, utilizing a **Durable Inbox/Outbox pattern** to ensure reliability and idempotency.

## Key Components

| Component | Path | Responsibility |
|-----------|------|---------------|
| Webhook Ingress | `app/routers/whatsapp.py` | Signature verification, event persistence (Inbox), and immediate 200 response. |
| AI Service | `app/services/ai_service.py` | Anthropic Claude integration, tool-use logic, and catalog grounding. |
| UI/Dashboard | `app/routers/ui.py` | Server-rendered (Jinja2) operator interface for orders and product management. |
| DB Layer | `app/db/database.py` | Supabase client and query execution. |
| Scheduler | `app/main.py` | APScheduler-based jobs for follow-ups and reports. |
| PDF Generator | `app/services/pdf_invoice.py` | Generation of Arabic PDF invoices using `fpdf2`. |

## Data Flow

**Meta Webhook** -> **FastAPI Web** -> **PostgreSQL (Inbox)** -> **Worker Process** -> **AI/Policy Gate** -> **PostgreSQL (Domain + Outbox)** -> **Meta Send API**

## Conventions

- **Durable Persistence**: All inbound events and outbound effects are persisted before/during processing.
- **Agentic Tool-Use**: AI proposes actions; deterministic application policy authorizes them.
- **Arabic-First**: The bot communicates primarily in Arabic ("Aunt ALYASMEEN" persona).
- **Supabase as Record**: Uses PostgreSQL for ACID transactions and state management.

## Current State: Paused Research

The project is in a **Paused Research** state as of 2026-06-14 (last active research date). 
- Initial ingestion is complete.
- Core research files for STACK, ARCHITECTURE, FEATURES, and PITFALLS are present in `.planning/research/`.
- ROADMAP.md and STATE.md are pending creation.
- Further research tasks are required before moving to the roadmap phase.
