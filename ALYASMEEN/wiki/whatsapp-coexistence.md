# WhatsApp Coexistence — Migration Plan (Aunt's Number)

**Summary**: Plan and impact analysis for moving the bot onto the aunt's real WhatsApp Business number using Meta's Coexistence feature ("API Solutions for Business App Users") — she keeps the WhatsApp Business app on her phone while the Cloud API (this bot) runs on the same number.

**Sources**: app/routers/whatsapp.py, app/services/transport.py, app/services/worker_tasks.py, app/services/outbox.py, app/services/monthly_report.py, config/rate_limits.json, .planning/STATE.md, Meta developer docs + BSP docs (web research, 2026-07-02 — time-sensitive)

**Graph**: [[graph-overview]] — communities "WhatsApp Bot Brain & Sessions", "WhatsApp Meta Sender"

**Last updated**: 2026-07-02

---

## What coexistence changes for THIS project

Today the architecture assumes the bot **is** the number: every inbound message gets an
automated reply (source: app/services/worker_tasks.py `_handle_message` — it always ends in
`send_text`/`send_buttons`), and the aunt is an *external* recipient reached at `AUNT_PHONE`
(source: app/services/worker_tasks.py:314, app/services/monthly_report.py:144).

With coexistence, the aunt's phone and the bot share one number. Four assumptions break:

### 1. New webhook fields the parser silently drops

Coexistence subscribes the app to extra webhook fields beyond `messages`/`statuses`:

- `smb_message_echoes` — every message the aunt sends **from her phone app** is echoed to
  our webhook (time-sensitive: Meta docs, 2026).
- `smb_app_state_sync` — her existing contacts (and new ones) sync to the API.
- `history` — up to 6 months of past 1-on-1 chats are delivered in the minutes/hours after
  onboarding (large histories: up to ~6 h).

`parse_meta_envelope()` only extracts `value.messages` and `value.statuses`
(source: app/services/transport.py:36) — the new fields would be dropped without error.
They must become first-class typed events in `webhook_events` so the worker can dispatch on
them. The `history` flood especially must never be processed as live messages.

### 2. Bot ↔ aunt collision (the biggest product risk)

Customer messages arrive in the normal `messages` field regardless of coexistence, so the
bot will keep auto-replying to **every** customer message — including conversations the
aunt is actively handling from her phone. Result without mitigation: customer asks, aunt
answers manually, the bot *also* answers with AI. Mandatory before go-live:

- **Human-takeover pause**: on an `smb_message_echoes` event showing the aunt manually
  messaged customer X, set `bot_paused_until` on X's session (config-tunable, e.g. 12 h in
  `config/rate_limits.json`, never hardcoded). While paused: log inbound to `chat_history`,
  send nothing.
- **Echoes into memory**: store aunt echoes in `chat_history` as assistant turns so Claude
  has context when the bot resumes (source: chat_history is the AI memory —
  [[database-tables]]).
- Optional: control keywords the aunt sends from her own phone in a customer chat
  (e.g. `#بوت` = resume bot for this customer).

### 3. `AUNT_PHONE` notifications break

If the aunt's number becomes the business number, `AUNT_PHONE == WA_META_PHONE_ID`'s number
and the Cloud API cannot message itself — new-order alerts
(source: app/services/worker_tasks.py:314) and the monthly report
(source: app/services/monthly_report.py:144) go nowhere. Mitigations:

- Point `AUNT_PHONE` at a second number (her personal SIM or Khaled). Smallest change; keeps
  the dedicated notification thread.
- Note the mirrored inbox partially compensates: she sees every customer thread — including
  the bot's order confirmation — live in her app.
- Add a startup guard: if `AUNT_PHONE` equals the business number, log a loud warning and
  skip self-sends.

### 4. Welcome-blast to existing customers

`upsert_customer()` fires the "أهلاً وسهلاً" welcome on first DB insert
(source: app/services/worker_tasks.py:198). After cutover, *every long-time customer* is
"new" to our DB and gets the welcome mid-relationship. Fix: seed `customers` from the
`smb_app_state_sync` contact sync (bonus: real names), and/or gate auto-reply behind a
staged-rollout `BOT_MODE` env (listen → assist → full).

## What does NOT change

- **24-h window & templates**: business-initiated messages outside the window still need
  approved templates — Phase 09 (template integration) stays fully relevant
  (source: .planning/STATE.md).
- **Outbox throughput**: coexistence caps the number at **5 msg/s combined**; our outbox is
  configured at 30 req/min (source: config/rate_limits.json) — an order of magnitude under
  the cap. Broadcast page must stay behind the same throttle.
- **Voice calls**: ring on her phone app only — fine, that's the desired behavior.

## Onboarding path (the hard part — not code)

Coexistence **cannot** be enabled from the app or from the plain Cloud API signup. It
requires Meta's **Embedded Signup** flow with the "keep my WhatsApp Business app"
(coexistence) option, and the onboarding app must be an approved **Tech Provider / Solution
Partner** (time-sensitive: Meta docs 2026). Two routes:

| Route | Effort | Trade-off |
|-------|--------|-----------|
| **A. Onboard via a BSP that supports coexistence** (e.g. 360dialog and many others) | Days | Monthly fee; some proxy the API (token/endpoint changes in `whatsapp_meta.py` config, not code — sender URL is built from `WA_META_PHONE_ID` + `WA_META_TOKEN`) |
| **B. Become a Meta Tech Provider on our own app** | Weeks (business verification + Embedded Signup advanced access) | No middleman, keeps current direct Cloud API setup unchanged |

Prerequisites either way: WhatsApp Business app ≥ 2.24.17 on her phone; number active ≥ 7
days; supported country (coverage is now near-worldwide after the Nov 2025 / Apr 2026
expansions — **verify Palestine explicitly during signup**, time-sensitive). After
onboarding: don't uninstall the app, and open it at least once every **13 days** or
coexistence disconnects. Her native app **broadcast lists stop working** and **groups don't
sync** — broadcasts move to the dashboard broadcast page.

## Recommended phase plan

1. **Decision + onboarding spike** — pick route A vs B; verify Palestine availability;
   back up her chats; update app version.
2. **Parser & inbox hardening** — extend `parse_meta_envelope` for `smb_message_echoes`,
   `smb_app_state_sync`, `history` (typed events, worker dispatch by type; unknown fields
   logged and ignored).
3. **Human-takeover logic** — `bot_paused_until` on sessions, echoes → `chat_history`,
   pause window in `config/rate_limits.json`.
4. **Notification rewiring** — `AUNT_PHONE` becomes a second number + startup self-send
   guard.
5. **Seeding + staged rollout** — contacts sync → `customers`; `BOT_MODE=listen` first,
   flip to full after a quiet week.
6. **Go-live guardrails** — keep outbox ≤ 5 msg/s, brief the aunt (13-day rule, no native
   broadcast lists, don't uninstall).

## Opinion

Coexistence is the **right architecture for this exact business**: the aunt keeps the app
she already knows, keeps her personal relationships and voice calls, and gets a live
mirrored view of every bot conversation — which solves the oversight problem better than
push notifications ever did. The bot stops being a separate "robot number" customers don't
recognize and becomes an assistant inside her real number.

The two make-or-break items are **(a)** the onboarding route (Tech Provider/BSP — pure
process, zero code, longest lead time; start it first) and **(b)** the human-takeover pause
(**must ship before go-live** or customers get double replies from aunt + AI on day one).
Everything else is incremental on the existing inbox/outbox worker architecture, which is
well shaped for this — the ingest-and-ack webhook + typed `webhook_events` seam is exactly
where echo/history/contact events slot in.

Fits GSD as its own milestone (M2.5 or fold into M3 Agent) — it touches transport, worker,
sessions, and ops, so it deserves its own REQUIREMENTS/ROADMAP rather than riding on
Phase 09/10.

## Related pages

- [[whatsapp-meta-integration]]
- [[whatsapp-bot-brain]]
- [[scheduler-jobs]]
- [[database-tables]]
- [[design-decisions]]
