# Phase 3: Agent Dependability & Safety - Research

**Researched:** 2026-06-15
**Domain:** AI Safety, Policy Enforcement, Human-in-the-Loop (HITL)
**Confidence:** HIGH

## Summary

Phase 3 transforms the ALYASMEEN bot from a standard LLM agent into a **Constrained Agent**. This is achieved by surrounding the "Probabilistic Core" (Claude) with a "Deterministic Shell" (Policy Gate) and providing clear exit ramps (Human Handoff) when the AI reaches its limits.

**Primary recommendation:** Implement a `PolicyGate` in `app/services/processor.py` that intercepts all tool calls and validates them against the current database state (e.g., order status) before execution.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-03-01 | Deterministic Policy Gate | Implement `PolicyEngine` to validate tool calls (e.g. status check before cancellation). |
| REQ-03-02 | Human Handoff Triggers | Patterns for intent (angry, refund), uncertainty, and unsupported media (voice/images). |
| REQ-03-03 | Handoff Implementation | Logic to update `handoffs`, `sessions.paused`, and notify Aunt. |
| REQ-03-04 | AI Evaluation | Test harness using `whatsapp_agent_dataset.json` for accuracy/latency/cost. |
| REQ-03-05 | Error Fallbacks | Deterministic responses when AI service is down or tool calls are malformed. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tool Call Validation | API / Backend | — | Must happen at the execution boundary to be authoritative. |
| Handoff Detection | API / Backend | — | Real-time analysis of incoming user messages and AI intent. |
| Handoff State Management| Database | API / Backend | `handoffs` table tracks active interventions; `sessions.paused` gates bot response. |
| AI Evaluation Harness | Local / Dev | CI/CD | Offline script to measure accuracy/cost using existing datasets. |
| Fallback Responses | API / Backend | — | Hard-coded strings used when AI service is unavailable or errors out. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | 0.25.0+ | LLM Interface | Official SDK for Claude 3.5 Sonnet / 3 Haiku. |
| pydantic | 2.0+ | Data Validation | For structured tool arguments and policy schemas. |
| structlog | 24.1.0+ | Logging | Essential for auditing tool calls and policy denials. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| pytest | 8.0+ | Testing | Running the AI evaluation script. |
| pandas | 2.0+ | Data Analysis | (Optional) For generating evaluation reports. |

**Installation:**
```bash
pip install pydantic structlog
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| anthropic | pypi | 1 yr | 2M/mo | github.com/anthropics/anthropic-sdk-python | [OK] | Approved |
| pydantic | pypi | 6 yrs | 100M/mo | github.com/pydantic/pydantic | [OK] | Approved |
| structlog | pypi | 11 yrs | 15M/mo | github.com/hynek/structlog | [OK] | Approved |

## Architecture Patterns

### Deterministic Policy Gate (The Shell Pattern)
The `tool_executor` closure in `processor.py` will be upgraded to a `PolicyEngine`.

```python
# Conceptual implementation for app/services/policy.py
class PolicyEngine:
    def validate(self, name: str, args: dict, context: dict) -> bool:
        if name == "add_to_cart":
            # Rule: No price overrides (schema-enforced, but good to check)
            if "price" in args: return False
        
        if name == "cancel_order": # (if added later)
            # Rule: No cancellations if status is not 'to_do'
            order = context.get("latest_order")
            if order and order["status"] != "to_do":
                return False
        
        return True
```

### Human Handoff Flow
1. **Detection:** Message contains `handoff_triggers` OR Claude returns `tool_use: handoff`.
2. **State Change:** 
    - Insert into `handoffs` (status='active').
    - Update `sessions` set `paused = true`.
3. **Notification:** Aunt receives WhatsApp alert with deep-link to order/chat.
4. **Resolution:** Aunt resolves handoff via Dashboard; `sessions.paused` set to `false`.

### Recommended Project Structure
```
app/
├── services/
│   ├── policy.py        # NEW: Deterministic rules for tool calls
│   ├── handoff.py      # NEW: Logic for human intervention
│   └── processor.py     # UPDATED: Integration of policy and handoff
scripts/
└── eval_agent.py        # NEW: Performance & accuracy test harness
```

## AI Evaluation (Arabic/English)

Using `tests/data/whatsapp_agent_dataset.json`, we will measure:

| Metric | Target (Release Threshold) | Measurement Method |
|--------|----------------------------|--------------------|
| **Intent Accuracy** | 90% | `actual_intent == expected_intent` |
| **Tool Precision** | 95% | No unauthorized or malformed tool calls. |
| **Arabic Nuance** | 85% | Correct handling of Levantine/Hebrew loanwords (mezuman, bit). |
| **Latency** | < 3s (P95) | End-to-end response time. |
| **Cost** | < $0.01 / msg | Token count using Haiku. |

### Release Thresholds
- **Critical Path:** 100% (Add to cart, Show menu, Confirm order).
- **FAQ/Info:** 80% (Store hours, location, ingredients).
- **Edge Cases:** 70% (Angry customers, complex cancellations).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentiment Analysis | Custom keyword list | Claude 3.5 (Agentic) | Keywords fail on "مش عاجبني" vs "عاجبني" (negation). |
| Intent Classification | Regex/Rules | Tool-calling (Schema) | LLMs handle colloquial variations much better than static rules. |
| Validation Logic | Inline `if` in processor | Pydantic Models | Centralizes schema and validation rules. |

## Common Pitfalls

### Pitfall 1: Ghost Cancellations
**What goes wrong:** Claude tells the user "I've cancelled your order," but because there is no `cancel_order` tool, the DB remains unchanged.
**How to avoid:** Explicitly tell Claude in the system prompt that it *cannot* cancel orders itself and must trigger a human handoff for such requests.

### Pitfall 2: Infinite Tool Loops
**What goes wrong:** Claude calls `add_to_cart` -> error -> calls `add_to_cart` again.
**How to avoid:** Limit the agentic loop to 2 turns max (already implemented in `generate_reply`).

### Pitfall 3: Stale Policy Context
**What goes wrong:** Policy checks `latest_order` status but uses a cached value from 10 minutes ago.
**How to avoid:** Ensure the `tool_executor` context fetches fresh data from DB for every validation check.

## Code Examples

### Handoff Detection Pattern
```python
HANDOFF_KEYWORDS = ["بدي احكي مع حنان", "كلميني حنان", "human", "agent", "موضوع خاص"]

def should_handoff(text: str, sentiment: str) -> bool:
    if any(k in text for k in HANDOFF_KEYWORDS):
        return True
    if sentiment == "angry":
        return True
    return False
```

### Safe Tool Executor Wrap
```python
def _make_tool_executor(phone: str, st: dict, cart: list) -> Callable[[str, dict], str]:
    def executor(name: str, args: dict) -> str:
        # 1. Deterministic Policy Gate
        if not policy_engine.is_allowed(name, args, phone):
            return "عذراً، لا يمكن تنفيذ هذا الطلب آلياً. سأقوم بتحويلك لخدمة العملاء."
        
        # 2. Original Implementation
        # ... (standard tool logic)
    return executor
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | pytest.ini |
| Quick run command | `pytest tests/unit/test_policy.py` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-03-01 | Policy Gate Validation | unit | `pytest tests/unit/test_policy.py` | ❌ Wave 0 |
| REQ-03-02 | Handoff Trigger Detection | unit | `pytest tests/unit/test_handoff.py` | ❌ Wave 0 |
| REQ-03-04 | AI Evaluation script | script | `python scripts/eval_agent.py` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/unit/test_policy.py` — covers REQ-03-01
- [ ] `tests/unit/test_handoff.py` — covers REQ-03-02
- [ ] `scripts/eval_agent.py` — covers REQ-03-04

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Pydantic validation on all tool arguments. |
| V10 Malicious Code | yes | No `eval()` or dynamic shell execution from LLM strings. |
| V13 API Security | yes | Tool calls are internal-only; no direct user exposure. |

### Known Threat Patterns for AI Agents

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt Injection | Tampering | System prompt shielding + Deterministic Policy Gate. |
| Tool Exhaustion | Denial of Service | Token limits + Max 2-turn agentic loop. |
| Order Spoofing | Repudiation | Mandatory `confirm` keyword (non-AI path). |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `handoffs` table is ready for use | Handoff Implementation | Migration 20260614... baseline shows it exists. |
| A2 | `sessions` table needs `paused` column | Handoff Implementation | Current schema lacks it; will need migration. |
| A3 | Haiku 3.5 is the target model | Evaluation | Budget assumes Haiku; Sonnet would triple costs. |

## Open Questions

1. **Voice Note Strategy:** Should we use OpenAI Whisper to transcribe?
   - *Recommendation:* Descope transcription for Phase 3. Detect voice note and trigger immediate handoff with "I can't hear voice notes yet, a human will check this."
2. **Cancellation Flow:** Should we actually build a `cancel_order` tool or keep it human-only?
   - *Recommendation:* Keep human-only for safety until Phase 4.

## Sources

### Primary (HIGH confidence)
- `app/services/processor.py` - Current tool execution logic.
- `supabase/migrations/20260614000001_durable_messaging.sql` - Handoffs table schema.
- `tests/data/whatsapp_agent_dataset.json` - Evaluation dataset.

### Secondary (MEDIUM confidence)
- Anthropic Tool Use Documentation - Pattern for multi-turn tool calling.
