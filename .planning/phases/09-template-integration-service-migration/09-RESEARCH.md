# Phase 09: Template Integration & Service Migration - Research

**Researched:** 2026-06-15
**Domain:** WhatsApp Meta Cloud API, Messaging Policy, Service Migration
**Confidence:** HIGH

## Summary

This phase addresses the critical risk of "out-of-window" messaging failures (Error 131047) by implementing Meta Cloud API Template support. Currently, the system sends free-form text for follow-ups and monthly reports, which fails if the recipient has not messaged the bot within the last 24 hours. We will implement `send_template` in `whatsapp_meta.py`, migrate `followup.py` and `monthly_report.py` to use the outbox with template payloads, and establish a documentation baseline for Meta assets.

**Primary recommendation:** Implement a generic `send_template` function that accepts a template name, language code, and an array of components, then update the worker to process `template` type jobs.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Template Dispatch | WhatsApp Meta Service | — | Direct interaction with Meta Graph API. |
| Job Sequencing | Outbox / Worker | — | Decouples report generation from delivery; handles retries. |
| 24h Window Enforcement| Service / Meta | — | Meta enforces this at the API level; we must respond by selecting templates. |
| Asset Documentation | Documentation | — | Centralizes Meta IDs and status for operator/maintainer. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| requests | 2.31.0+ | HTTP Client | Already used for Meta API calls in `whatsapp_meta.py`. |
| json | (stdlib) | Serialization | Required for complex Meta template payloads. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| python-dotenv | 1.0.x | Config | Already used to manage `WA_META_*` environment variables. |

**Installation:**
Already covered by `requirements.txt`.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| requests | npm/PyPI | 13 yrs | 300M/mo | github.com/psf/requests | [OK] | Approved |

## Architecture Patterns

### Pattern 1: Template Payload Schema
The `outbox_jobs` payload for templates should follow the Meta component structure but simplified for our use cases.

```json
{
  "type": "template",
  "template_name": "followup_v1",
  "language_code": "ar",
  "body_vars": ["Customer Name"]
}
```

### Pattern 2: Generic Template Sender
Instead of hardcoding every template, `send_template` should handle the assembly of the `components` array.

```python
# Conceptual implementation for app/services/whatsapp_meta.py
def send_template(to: str, template_name: str, language_code: str = "ar", body_vars: list[str] = None) -> dict:
    components = []
    if body_vars:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": v} for v in body_vars]
        })
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to.replace(" ", ""),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components
        }
    }
    # ... POST to Meta API
```

## Recommended Template Inventory

| Use Case | Template Name | Category | Variables |
|----------|---------------|----------|-----------|
| 3-day Follow-up | `order_followup` | UTILITY | `{{1}}`: Customer Name |
| Monthly Report | `monthly_summary`| UTILITY | `{{1}}`: Full Report Text |
| Order Ready | `order_ready` | UTILITY | `{{1}}`: Order Name |
| Delivery Update| `out_for_delivery`| UTILITY | `{{1}}`: Order Name, `{{2}}`: Driver Info |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 24h Window Check | Local timer logic | Meta API Error handling | Meta is the source of truth. If a send fails with 131047, we know the window is closed. |
| Message Formatting | Complex regex | Template placeholders | Meta ensures formatting consistency and policy compliance. |

## Common Pitfalls

### Pitfall 1: Error 131047 (Out of Window)
**What goes wrong:** Attempting to send a text/button message after 24h. Meta returns HTTP 400 with sub-code 131047.
**How to avoid:** Scheduled jobs (Follow-up, Monthly Report) MUST use templates by default, as they are almost certainly out-of-window.

### Pitfall 2: Template Rejection
**What goes wrong:** Meta rejects a template because it's "Marketing" but marked as "Utility".
**How to avoid:** Use "Utility" for transactional messages (status, follow-up) and keep them concise. Marketing should be reserved for true broadcasts.

### Pitfall 3: Variable Length Limits
**What goes wrong:** A variable (e.g., product list) exceeds the 1024 character limit.
**How to avoid:** Truncate or simplify dynamic lists in templates.

## Code Examples

### Meta Template JSON Payload
```json
{
  "messaging_product": "whatsapp",
  "to": "972591234567",
  "type": "template",
  "template": {
    "name": "order_followup",
    "language": {
      "code": "ar"
    },
    "components": [
      {
        "type": "body",
        "parameters": [
          {
            "type": "text",
            "text": "أحمد"
          }
        ]
      }
    ]
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `send_text` for everything | `send_template` for initiated messages | 2024 (Meta Policy) | Mandatory for business-initiated contact. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Meta Templates are approved in ~1h | Pitfalls | If approval takes days, feature rollout is delayed. |
| A2 | Single body variable fits the monthly report | Templates | If report > 1024 chars, it will fail. |
| A3 | `AUNT_PHONE` needs a template | Summary | If she messages the bot daily, text would work, but templates are safer. |

## Open Questions

1. **Should we implement "Template Fallback"?** If a text message fails with 131047, should the worker automatically try a template?
   - *Recommendation:* No, keep it deterministic. Code that knows it's sending an initiated message should explicitly choose a template.
2. **What if the template is not approved yet?**
   - *Recommendation:* Provide a way to test with `hello_world` (the default Meta template) in the onboarding docs.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Meta App Secret | HMAC Verification | ✓ | — | Skip check (not recommended) |
| WhatsApp Phone ID | Messaging | ✓ | — | Blocking |
| WhatsApp Token | Messaging | ✓ | — | Blocking |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Quick run command | `pytest tests/unit/test_whatsapp_meta.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| REQ-09-01 | `send_template` produces correct JSON | unit | `pytest tests/unit/test_whatsapp_meta.py` |
| REQ-09-02 | Follow-up service enqueues template | integration | `pytest tests/integration/test_followup_template.py` |
