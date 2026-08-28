# Phase 5: Operator Security & UX (M5) - Context

**Gathered:** 2026-08-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the shared-password dashboard login with Supabase Auth (email + password) plus TOTP MFA,
move to opaque server-side sessions, protect all dashboard mutations with CSRF and security
headers, and give the aunt an operator UI for handoffs, audit history, and conflict resolution.

Existing surfaces this phase builds on (do not rebuild from scratch):
- **Handoff mechanics come from Phase 3** (`handoffs` table, `sessions.paused` gate,
  HandoffService, keyword/media/policy triggers). Phase 5 builds the UI on top. Phase 3 is
  planned but NOT yet executed — plans must sequence against or verify that dependency.
- **Dead-letter visibility exists from Phase 4** (`/alerts` page, `GET /api/alerts`, retry
  endpoints). Phase 5 REWORKS this page (see decisions) rather than creating it.

</domain>

<decisions>
## Implementation Decisions

### Accounts & login (REQ-prod-auth-mfa, REQ-dash-login)
- **Two accounts**: the aunt (operator) + Khaled (admin). Admin can help remotely and owns recovery.
- **Real email addresses** as login identifiers — standard Supabase Auth flow, password-reset emails work.
- **TOTP enrollment is assisted**: Khaled sets it up with her (in person or on a call). The
  dashboard shows the QR only during an explicit enrollment step — not a self-serve forced flow.
- **Lost phone / MFA recovery**: admin removes her MFA factor (Supabase admin / script), she
  re-enrolls. No printed recovery codes.

### Sessions (REQ-prod-session-opaque)
- **30-day session lifetime**; sign in roughly monthly.
- **MFA remember-device for 30 days per device** — TOTP prompted only on new devices or after 30 days.
- **Multi-device allowed** — phone + laptop sessions coexist; logout on one doesn't kill the other.
- **No idle timeout.**
- **"Log out everywhere" button for both accounts** (kills all of that user's sessions).
- **Any credential change (password change, MFA reset) revokes ALL sessions** for that user.
- **Admin session view**: Khaled's account can list and revoke the aunt's active sessions from the UI
  (lost/stolen phone scenario).
- **New-device login sends a WhatsApp alert to Khaled (admin)** — the aunt is not bothered.

### Handoff & audit UI (success criterion 2)
- **New dedicated nav tab** for handoffs (e.g. محادثات) — becomes the 6th dashboard tab, wired into
  all templates like the alerts tab was.
- **Handoff detail view = reason + recent chat transcript** (from `chat_history`) so she has context
  before opening WhatsApp; include the wa.me link.
- **Single resolution action: "return to bot"** (أعد للبوت) — resolves the handoff and unpauses the
  session. She converses with the customer in WhatsApp itself; no dashboard reply box.
- **Resolved handoffs stay visible** as recent history (active on top, resolved below / behind a filter).
- **Live count badge** of active handoffs on the nav tab, refreshed with the dashboard's auto-refresh.
- **Conflicts = bot-vs-aunt overlap**: when she and the bot both act on the same customer/order
  (e.g. she changes a status while the bot is mid-conversation), the UI should detect the overlap
  and let her pick the winner — not just a silent last-write-wins.
- **Audit history covers ALL operator actions**: handoffs, order status changes, product edits,
  broadcasts, logins — one chronological who-did-what trail.
- **Audit history visible to both accounts** (shown in her UI too, not admin-only).

### Failure recovery UX (success criterion 4)
- **Rework the /alerts page** — don't keep the current technical presentation.
- **Action-oriented plain Arabic cards with customer names**: each failure reads as a call to
  action — "تحتاج انتباهك الآن — رسالة لم تصل إلى فلانة، تابعي المحادثة معها" — telling her what
  happened and what to do next (continue the conversation herself). Technical detail (job type,
  attempts, payload) collapsed behind a details toggle.
- **Proactive WhatsApp alerts on permanent failure, to BOTH**: the aunt gets customer-facing
  failures (a message to a customer didn't arrive); Khaled gets everything.
- **Retry controls: per-item retry + a bulk "retry all"** (post-outage recovery).

### Claude's Discretion
- All purely technical design: opaque session store mechanics, CSRF token mechanism, exact
  security-header set (CSP/HSTS/etc.), conflict-detection implementation, audit-log storage design.
- Alerts-page card visual design and whether retry or "take over yourself" is the primary action
  per failure type.
- Handoff tab naming, layout details, and transcript length shown.
- How "remember this device" is persisted/identified.

</decisions>

<specifics>
## Specific Ideas

- Alert phrasing, in the user's words: "need you attention now — a message didn't get to X, go
  continue the conversation." Failures are framed as urgent, human, next-step instructions with
  the customer's name — not job IDs.
- Keep the existing premium design system (green #006948, Material Symbols, glassmorphism navbar,
  Cairo font, Arabic RTL) for every new/reworked page.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-operator-security-ux*
*Context gathered: 2026-08-28*
