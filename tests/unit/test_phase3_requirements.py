"""
test_phase3_requirements.py — Requirements-traceability tests for Phase 3
(agent-dependability-safety).

Three of Phase 3's nine requirements — REQ-bot-aunt-notification,
REQ-sched-followup, REQ-sched-retry-queue — were satisfied structurally by
Phase 4's outbox/gatekeeper rewrite rather than by anything Phase 3 itself
built. 03-RESEARCH.md confirmed each against the code once, in August 2026.
"Confirmed by reading the code once" is not the same as "cannot silently
regress" — there was no test asserting the aunt's new-order alert goes
through the durable outbox, and retry_queue.py's retirement was recorded only
in a migration comment. This file converts those verifications into
executable, regression-tested assertions, and also pins success criterion 4
("automated to_do order changes work reliably while later statuses block
agent mutation") end-to-end: at the tool-surface layer, the policy-scope
layer, and — because that boundary is currently maintained by nothing but
habit — the source-code layer.

The point of this whole file: "already true" must not be allowed to quietly
become "was true once".

Follows tests/unit/test_processor.py's/test_processor_policy.py's
conventions: calls processor.handle_message() directly (no HTTP layer), with
the DB and WhatsApp sender faked via conftest.py's autouse mock_db fixture
(fake_db, sent_messages). No flush_outbox() is used where the point of the
assertion is durability itself — see TestAuntNotificationIsDurable's first
test, which deliberately asserts on the outbox row BEFORE anything is sent.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import random
from pathlib import Path

import pytest

import app.services.processor as processor
from app.services import ai_service, policy

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "app"

FAKE_CATALOG = [
    {"id": 1, "name": "كريم اليدين", "list_price": 25.0, "description_sale": "كريم مرطب للأيدي"},
    {"id": 2, "name": "لوشن الجسم", "list_price": 40.0, "description_sale": "لوشن طبيعي"},
    {"id": 3, "name": "شمعة العود", "list_price": 35.0, "description_sale": "شمعة عطرية"},
]


def _phone() -> str:
    return f"97259{random.randint(1000000, 9999999)}"


def _add_hand_cream_and_confirm(phone: str) -> None:
    """Drives the deterministic hard-command path (no AI call needed) to a
    confirmed pickup order: menu -> pick #1 (كريم اليدين, 25.0₪) -> pickup
    -> confirm. Mirrors tests/unit/test_processor.py's own confirm-flow
    tests exactly, kept local here so this file's confirm-flow tests don't
    depend on that file's fixtures."""
    processor.handle_message(phone, "menu", "Test")
    processor.handle_message(phone, "1", "Test")
    processor.handle_message(phone, "pickup", "Test")
    processor.handle_message(phone, "confirm", "Test")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rpc_call_enclosing_functions(source: str, rpc_arg_name: str) -> list[str]:
    """Return, for every `rpc(<rpc_arg_name>, ...)` call found in `source`,
    the name of the innermost enclosing function ("<module>" if the call
    sits at module level, outside any function).

    Source-level parsing (not a plain string grep) so a call is correctly
    attributed to the function that actually contains it, even across
    multiple functions in the same file.
    """
    tree = ast.parse(source)
    found: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "rpc"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == rpc_arg_name
            ):
                found.append(self.stack[-1] if self.stack else "<module>")
            self.generic_visit(node)

    _Visitor().visit(tree)
    return found


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    monkeypatch.setattr(processor, "catalog", lambda: FAKE_CATALOG)


# ---------------------------------------------------------------------------
# REQ-bot-aunt-notification — the new-order alert is durable, not fire-and-forget
# ---------------------------------------------------------------------------

class TestAuntNotificationIsDurable:
    """The aunt's new-order alert must be a durable outbox_jobs row (queued,
    retried, and observable independent of whether the WhatsApp send itself
    ever succeeds) — not a bare try/except send that silently drops on
    failure. CLAUDE.md used to describe the old bare-try/except design; that
    description is now stale (see Task 3 of this plan) and this test is the
    reason it's safe to say so."""

    def test_confirm_queues_an_aunt_notification_through_the_outbox(self, fake_db, monkeypatch):
        monkeypatch.setattr(processor.Config, "AUNT_PHONE", "972590000001")

        phone = _phone()
        _add_hand_cream_and_confirm(phone)

        # Deliberately asserted BEFORE any flush_outbox()/process_outbox_jobs()
        # call: the point is that the alert already exists as a durable row
        # the instant confirm() returns, independent of whether the WhatsApp
        # API send ever actually succeeds.
        aunt_jobs = [j for j in fake_db.outbox_jobs if j["phone"] == "972590000001"]
        assert len(aunt_jobs) == 1
        assert aunt_jobs[0]["kind"] == "whatsapp_message"
        assert aunt_jobs[0]["status"] == "pending"

    def test_aunt_notification_contains_order_number_and_total(self, fake_db, monkeypatch):
        monkeypatch.setattr(processor.Config, "AUNT_PHONE", "972590000001")

        phone = _phone()
        _add_hand_cream_and_confirm(phone)

        aunt_job = next(j for j in fake_db.outbox_jobs if j["phone"] == "972590000001")
        text = aunt_job["payload"]["text"]
        order_id = fake_db.orders[0]["id"]
        assert f"ORD-{order_id:04d}" in text
        assert "25" in text  # كريم اليدين's list_price (25.0)

    def test_customer_confirmation_is_not_lost_if_the_aunt_alert_fails(self, fake_db, monkeypatch):
        """The customer's own confirmation is queued (and therefore already
        durably written) before the aunt's alert is even attempted — a
        failure sending the aunt's alert must never cost the customer their
        own order confirmation."""
        monkeypatch.setattr(processor.Config, "AUNT_PHONE", "972590000001")

        real_queue_text = processor.queue_text

        def _queue_text_aunt_fails(to, text):
            if to == "972590000001":
                raise RuntimeError("outbox insert failed for aunt")
            return real_queue_text(to, text)

        monkeypatch.setattr(processor, "queue_text", _queue_text_aunt_fails)

        phone = _phone()
        _add_hand_cream_and_confirm(phone)

        customer_jobs = [j for j in fake_db.outbox_jobs if j["phone"] == phone]
        assert any("ORD-" in j["payload"]["text"] for j in customer_jobs), (
            "the customer's own confirmation must survive even when the "
            "aunt's alert fails to enqueue"
        )


# ---------------------------------------------------------------------------
# REQ-sched-followup — follow-ups go through the durable outbox
# ---------------------------------------------------------------------------

class TestFollowupsAreDurable:
    """Post-delivery follow-ups (app/services/followup.py, scheduled every
    6 hours) must enqueue through the same durable outbox every other
    customer-facing send uses — never a direct WhatsApp API call — and the
    scheduler job that drives them must actually be registered."""

    def test_followup_enqueues_instead_of_sending_directly(self, fake_db, monkeypatch):
        import app.services.followup as fu

        pending = [{"id": 1, "phone": "972591111111", "order_id": "10"}]
        monkeypatch.setattr(fu, "query", lambda sql, params=(): pending)
        monkeypatch.setattr(fu, "execute", lambda sql, params=(): None)

        real_queue_text = fu.queue_text
        queue_calls: list[tuple[str, str]] = []

        def _spy_queue_text(to, msg):
            queue_calls.append((to, msg))
            return real_queue_text(to, msg)

        monkeypatch.setattr(fu, "queue_text", _spy_queue_text)

        def _send_text_must_not_be_called(*args, **kwargs):
            raise AssertionError(
                "followup.send_followups must never call send_text directly "
                "— it must go through queue_text/outbox_jobs (REQ-sched-followup)"
            )

        # processor.send_text is the only real sender fu.queue_text's own
        # execute() call could ever reach transitively; asserting it's never
        # invoked here proves the enqueue-only contract, not just that
        # *something* called queue_text.
        monkeypatch.setattr(processor, "send_text", _send_text_must_not_be_called)

        result = fu.send_followups()

        assert result == 1
        assert queue_calls == [("972591111111", fu.FOLLOWUP_MESSAGE)]
        assert len(fake_db.outbox_jobs) == 1
        assert fake_db.outbox_jobs[0]["phone"] == "972591111111"
        assert fake_db.outbox_jobs[0]["kind"] == "whatsapp_message"

    def test_followup_job_is_registered_in_the_worker(self):
        """Structural check only (does not start a real BlockingScheduler):
        app.worker.start_worker() must actually register the follow-up job,
        or REQ-sched-followup silently stops firing in production even
        though followup.py itself is correct."""
        import app.worker as worker

        source = inspect.getsource(worker.start_worker)
        assert "send_followups" in source
        assert 'id="followup"' in source


# ---------------------------------------------------------------------------
# REQ-sched-retry-queue — retired in favour of the outbox poller
# ---------------------------------------------------------------------------

class TestRetryQueueIsRetired:
    """retry_queue.py/retry_actions.py were deleted in Phase 4
    (supabase/migrations/20260825000003_retire_retry_queue.sql), and the
    15-minute retry_queue scheduler job was removed from app/worker.py — the
    outbox poller's bounded per-job attempts + notify_permanent_failure() is
    the retry mechanism REQ-sched-retry-queue now maps to. These tests pin
    that the retirement actually happened and stays that way."""

    def test_no_retry_queue_module_exists(self):
        assert importlib.util.find_spec("app.services.retry_queue") is None
        assert importlib.util.find_spec("app.services.retry_actions") is None

    def test_no_retry_queue_job_in_the_worker(self):
        worker_source = _read(APP_ROOT / "worker.py")
        assert "retry" not in worker_source.lower()

    def test_outbox_poller_is_the_retry_mechanism(self, fake_db, monkeypatch):
        """Full bounded-retry-then-alert behavior is already covered in
        depth by tests/unit/test_processor.py::TestOutboxBoundedRetry and
        TestPermanentFailureAlerts::test_final_attempt_failure_queues_alerts_to_aunt_and_admin
        — this test is a requirements-traceability anchor for REQ-sched-
        retry-queue specifically, not a re-derivation of that coverage."""
        monkeypatch.setattr(processor.Config, "AUNT_PHONE", "972590000001")
        monkeypatch.setattr(processor.Config, "ADMIN_PHONE", "972590000002")

        def _always_fail(*args, **kwargs):
            raise RuntimeError("meta api down")

        monkeypatch.setattr(processor, "send_text", _always_fail)

        phone = _phone()
        processor.queue_text(phone, "hello")
        job = fake_db.outbox_jobs[0]
        max_attempts = job["max_attempts"]

        for _ in range(max_attempts + 1):
            processor.process_outbox_jobs()

        assert job["status"] == "failed"
        assert job["attempts"] == max_attempts

        alerted = sorted(j["phone"] for j in fake_db.outbox_jobs if j["phone"] != phone)
        assert alerted == sorted(["972590000001", "972590000002"])


# ---------------------------------------------------------------------------
# Success criterion 4 — the agent cannot mutate an order past to_do, at
# every layer: the tool surface, the policy scope map, and the source code.
# ---------------------------------------------------------------------------

class TestAgentCannotMutateOrders:
    """"Automated to_do order changes work reliably while later statuses
    block agent mutation" (success criterion 4) is true today because no
    code path lets the AI touch orders.status at all — not because anything
    currently checks an order's status before allowing a tool call. That is
    an architectural invariant maintained by nothing but habit unless it is
    pinned by a test. This class pins it at three independent layers so a
    future sixth tool, or a refactor that moves an RPC call, cannot silently
    reopen the hole."""

    def test_ai_tool_surface_has_no_order_mutating_tool(self):
        """Mirrors tests/unit/test_ai_service.py::test_no_tool_can_mutate_order_status
        — kept here too, duplicated deliberately, because this is the file a
        future reader opens to answer "how do I know the agent can't cancel
        an order?" end-to-end, without also having to find that other file.

        Checked by exact name / exact property-key membership (not a bare
        substring search): get_order_status is a legitimate READ-only tool
        (policy.TOOL_SCOPES["get_order_status"] == "read") whose own NAME
        contains "status" — a substring match on tool names would wrongly
        flag it. The invariant that actually matters is that no tool can be
        handed a `status`/`cancel`/`refund`/`delete` ARGUMENT, and no tool is
        literally named to imply order mutation.
        """
        forbidden_names = {
            "cancel_order", "update_status", "set_status", "update_order_status",
            "delete_order", "refund_order", "refund",
        }
        banned_props = {"status", "cancel", "refund", "delete"}

        for tool in ai_service._TOOLS:
            assert tool["name"] not in forbidden_names, tool["name"]
            props = (tool.get("input_schema", {}) or {}).get("properties", {}) or {}
            overlap = set(props) & banned_props
            assert not overlap, (tool["name"], overlap)

    def test_policy_tool_scopes_cover_every_ai_tool(self):
        """The duplicate of 03-02's guard (tests/unit/test_policy.py), kept
        here for the same "one file to check the whole invariant" reason as
        the test above. If a tool is ever added to ai_service._TOOLS without
        a matching entry in policy.TOOL_SCOPES, policy.validate()'s
        unknown_tool rule denies it by default — but this test catches the
        mismatch explicitly rather than relying on that default-deny alone.
        """
        assert {t["name"] for t in ai_service._TOOLS} == set(policy.TOOL_SCOPES)

    def test_order_status_writes_come_only_from_the_operator_api(self):
        """Source-level architectural-boundary guard, in two parts. Unusual
        for a test suite, but it is the only way to pin a boundary that is
        currently held up by convention alone. If either boundary
        legitimately needs to change (a new operator endpoint moves, or a
        second legitimate order-creation path is added on purpose), update
        THIS test and ALYASMEEN/wiki/agent-safety.md's order-mutation
        boundary section in the same change — do not just delete the
        assertion.
        """
        # --- Part 1: status-progression boundary -------------------------
        # Every literal "UPDATE orders SET status" in the app/ tree must
        # live in app/routers/ui_api.py (the operator-authenticated
        # dashboard API) — never in processor.py, ai_service.py, or
        # policy.py (or anywhere else the bot/AI code lives).
        ui_api_path = APP_ROOT / "routers" / "ui_api.py"
        offenders = []
        for py_file in APP_ROOT.rglob("*.py"):
            if py_file == ui_api_path:
                continue
            if "UPDATE orders SET status" in _read(py_file):
                offenders.append(str(py_file.relative_to(REPO_ROOT)))
        assert offenders == [], (
            "Only app/routers/ui_api.py may progress an order's status. "
            f"Found the literal SQL elsewhere too: {offenders}"
        )
        # Sanity check: the boundary must actually exist somewhere, so this
        # isn't vacuously true because ui_api.py got renamed.
        assert "UPDATE orders SET status" in _read(ui_api_path)

        # --- Part 2: order-creation boundary ------------------------------
        # create_order_atomic is legitimately called from processor.py's
        # _handle_confirm (the sole path that creates an order, always
        # landing it in to_do — see policy.py's TOOL_SCOPES comment) but
        # must be called from NOWHERE else inside processor.py, and not at
        # all from ai_service.py or policy.py. This is deliberately NOT "the
        # RPC never appears in processor.py" — order CREATION through the
        # hard-coded confirm command is fine and expected; only STATUS
        # PROGRESSION and any OTHER creation path are forbidden.
        processor_source = _read(APP_ROOT / "services" / "processor.py")
        enclosing = _rpc_call_enclosing_functions(processor_source, "create_order_atomic")
        assert enclosing == ["_handle_confirm"], (
            "create_order_atomic must be called only from processor._handle_confirm "
            f"— found it called from: {enclosing}"
        )

        # AST-based (not a plain string search): policy.py's own module
        # docstring and comments legitimately DISCUSS create_order_atomic
        # (explaining why "order" scope has no members) without ever calling
        # it — a substring check would false-positive on that prose.
        ai_service_source = _read(APP_ROOT / "services" / "ai_service.py")
        policy_source = _read(APP_ROOT / "services" / "policy.py")
        assert _rpc_call_enclosing_functions(ai_service_source, "create_order_atomic") == []
        assert _rpc_call_enclosing_functions(policy_source, "create_order_atomic") == []

    def test_confirm_creates_orders_only_in_to_do(self, fake_db):
        phone = _phone()
        _add_hand_cream_and_confirm(phone)

        assert len(fake_db.orders) == 1
        assert fake_db.orders[0]["status"] == "to_do"
