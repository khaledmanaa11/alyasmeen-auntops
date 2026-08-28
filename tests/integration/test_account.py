"""test_account.py — Integration tests for the /account page and its routes
(app/routers/auth_routes.py's MFA-enrollment, session-management, and
password-reset additions from 05-09).

Auth identity is injected via the operator_client / admin_client fixtures
(tests/conftest.py — a FastAPI dependency override, same pattern as
test_orders_api.py / test_ui_api.py / test_alerts_api.py / test_operator_api.py).
The Supabase-backed auth_service / sessions surfaces are additionally
monkeypatched wholesale at the names bound into app.routers.auth_routes —
the same pattern test_auth_flow.py uses for the login/MFA-challenge routes,
so these tests never touch the real Supabase project. audit.log_action() is
faked the same way here (rather than relying solely on tests/conftest.py's
autouse audit-safety patch) so tests can assert exactly what was logged.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

from app.services.auth import AuthError  # noqa: E402
from app.shared.constants import PENDING_LOGIN_COOKIE_NAME  # noqa: E402

# FAKE_OPERATOR / FAKE_ADMIN from tests/conftest.py — values hardcoded here
# rather than imported, matching test_orders_api.py's existing convention.
FAKE_OPERATOR_EMAIL = "aunt@example.test"
FAKE_OPERATOR_USER_ID = "00000000-0000-0000-0000-000000000001"
FAKE_OPERATOR_SESSION_ID = "11111111-1111-1111-1111-111111111111"


class FakeAuthService:
    """Stands in for app.services.auth, patched onto auth_routes.auth_service."""

    def __init__(
        self,
        sign_in_error=None,
        enroll_totp_result=None,
        verify_enrollment_error=None,
    ):
        self.sign_in_error = sign_in_error
        self.enroll_totp_result = enroll_totp_result or {
            "factor_id": "factor-1",
            "qr_code": "data:image/svg+xml;utf-8,<svg/>",
            "secret": "JBSWY3DPEHPK3PXP",
        }
        self.verify_enrollment_error = verify_enrollment_error
        self.sign_in_calls: list[tuple[str, str]] = []

    def sign_in(self, email, password):
        self.sign_in_calls.append((email, password))
        if self.sign_in_error is not None:
            raise self.sign_in_error

        class _Result:
            access_token = "aal1-access"
            refresh_token = "aal1-refresh"

        return _Result()

    def enroll_totp(self, access_token, refresh_token):  # noqa: ARG002
        return self.enroll_totp_result

    def verify_enrollment(self, access_token, refresh_token, factor_id, code):  # noqa: ARG002
        if self.verify_enrollment_error is not None:
            raise self.verify_enrollment_error

    def admin_list_factors(self, user_id):  # noqa: ARG002
        return []


class FakeSessions:
    """Stands in for app.services.sessions, patched onto auth_routes.sessions."""

    def __init__(self, sessions_for_user=None):
        self._pending: dict[str, dict] = {}
        self._pending_seq = 0
        self._sessions_for_user = sessions_for_user if sessions_for_user is not None else []
        self.revoke_all_calls: list[tuple] = []
        self.revoke_session_calls: list[str] = []
        self.remembered_devices: list[tuple] = []

    def create_pending_login(self, user_id, email, is_admin, factor_id, access_token, refresh_token):
        self._pending_seq += 1
        token = f"pending-token-{self._pending_seq}"
        self._pending[token] = {
            "user_id": user_id,
            "email": email,
            "is_admin": is_admin,
            "factor_id": factor_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        return token

    def consume_pending_login(self, raw_token):
        return self._pending.pop(raw_token, None) if raw_token else None

    def mint_token(self):
        return "device-token-raw"

    def remember_device(self, user_id, raw_device_token, label=None):
        self.remembered_devices.append((user_id, raw_device_token, label))
        return ("device-id-new", True)

    def revoke_all_for_user(self, user_id, except_session_id=None):
        self.revoke_all_calls.append((user_id, except_session_id))

    def list_sessions_for_user(self, user_id):  # noqa: ARG002
        return self._sessions_for_user

    def revoke_session(self, session_id):
        self.revoke_session_calls.append(session_id)

    def list_active_sessions(self):
        return self._sessions_for_user


class FakeAudit:
    """Stands in for app.services.audit, patched onto auth_routes.audit."""

    def __init__(self):
        self.calls: list[tuple] = []

    def log_action(self, actor, action, details=None):
        self.calls.append((actor, action, details))


def _patch_auth_routes(monkeypatch, auth_service=None, sessions=None, audit=None):
    import app.routers.auth_routes as auth_routes

    if auth_service is not None:
        monkeypatch.setattr(auth_routes, "auth_service", auth_service)
    if sessions is not None:
        monkeypatch.setattr(auth_routes, "sessions", sessions)
    if audit is not None:
        monkeypatch.setattr(auth_routes, "audit", audit)


# ---------------------------------------------------------------------------
# GET /account
# ---------------------------------------------------------------------------

class TestAccountPage:
    def test_returns_200_with_all_four_card_headings(self, operator_client, monkeypatch):
        _patch_auth_routes(
            monkeypatch,
            auth_service=FakeAuthService(),
            sessions=FakeSessions(),
            audit=FakeAudit(),
        )

        r = operator_client.get("/account")

        assert r.status_code == 200
        for heading in ("حسابي", "التحقق بخطوتين", "الأجهزة المتصلة", "جلسات المشغّلين"):
            assert heading in r.text


# ---------------------------------------------------------------------------
# POST /account/mfa/enroll
# ---------------------------------------------------------------------------

class TestMfaEnrollStart:
    def test_wrong_password_returns_401_and_creates_no_pending_row(
        self, operator_client, monkeypatch
    ):
        fake_auth = FakeAuthService(
            sign_in_error=AuthError("invalid credentials", code="invalid_credentials")
        )
        fake_sessions = FakeSessions()
        _patch_auth_routes(monkeypatch, auth_service=fake_auth, sessions=fake_sessions)

        r = operator_client.post("/account/mfa/enroll", data={"password": "wrong"})

        assert r.status_code == 401
        assert "كلمة المرور غير صحيحة" in r.json()["detail"]
        assert fake_sessions._pending == {}


# ---------------------------------------------------------------------------
# POST /account/mfa/enroll/verify
# ---------------------------------------------------------------------------

class TestMfaEnrollVerify:
    def test_good_code_revokes_other_sessions_and_logs_mfa_enrolled(
        self, operator_client, monkeypatch
    ):
        fake_auth = FakeAuthService()  # verify_enrollment succeeds by default
        fake_sessions = FakeSessions()
        fake_audit = FakeAudit()
        _patch_auth_routes(
            monkeypatch, auth_service=fake_auth, sessions=fake_sessions, audit=fake_audit
        )

        pending_token = fake_sessions.create_pending_login(
            FAKE_OPERATOR_USER_ID, FAKE_OPERATOR_EMAIL, False, "factor-1", "aal1-access", "aal1-refresh"
        )
        operator_client.cookies.set(PENDING_LOGIN_COOKIE_NAME, pending_token)

        r = operator_client.post("/account/mfa/enroll/verify", json={"code": "123456"})

        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert fake_sessions.revoke_all_calls == [
            (FAKE_OPERATOR_USER_ID, FAKE_OPERATOR_SESSION_ID)
        ]
        assert ("mfa_enrolled" in [c[1] for c in fake_audit.calls])

    def test_bad_code_returns_400_and_never_revokes(self, operator_client, monkeypatch):
        fake_auth = FakeAuthService(
            verify_enrollment_error=AuthError(
                "mfa_verification_failed", code="mfa_verification_failed"
            )
        )
        fake_sessions = FakeSessions()
        fake_audit = FakeAudit()
        _patch_auth_routes(
            monkeypatch, auth_service=fake_auth, sessions=fake_sessions, audit=fake_audit
        )

        pending_token = fake_sessions.create_pending_login(
            FAKE_OPERATOR_USER_ID, FAKE_OPERATOR_EMAIL, False, "factor-1", "aal1-access", "aal1-refresh"
        )
        operator_client.cookies.set(PENDING_LOGIN_COOKIE_NAME, pending_token)

        r = operator_client.post("/account/mfa/enroll/verify", json={"code": "000000"})

        assert r.status_code == 400
        assert fake_sessions.revoke_all_calls == []
        assert "mfa_enrolled" not in [c[1] for c in fake_audit.calls]


# ---------------------------------------------------------------------------
# POST /api/account/sessions/{id}/revoke
# ---------------------------------------------------------------------------

class TestAccountSessionRevoke:
    def test_session_belonging_to_another_user_is_not_revoked(
        self, operator_client, monkeypatch
    ):
        # This operator's own session list does NOT include "other-users-session" —
        # simulates guessing/reusing another operator's session id.
        fake_sessions = FakeSessions(
            sessions_for_user=[{"id": FAKE_OPERATOR_SESSION_ID, "email": FAKE_OPERATOR_EMAIL}]
        )
        _patch_auth_routes(monkeypatch, sessions=fake_sessions, audit=FakeAudit())

        r = operator_client.post("/api/account/sessions/other-users-session/revoke")

        assert r.status_code in (403, 404)
        assert fake_sessions.revoke_session_calls == []


# ---------------------------------------------------------------------------
# GET /api/admin/sessions
# ---------------------------------------------------------------------------

class TestAdminSessions:
    # Deliberately two separate tests, not one test taking both
    # operator_client and admin_client: both fixtures mutate the SAME
    # app.dependency_overrides dict on the shared app object, so whichever
    # fixture's setup runs last would silently clobber the other's
    # overrides before the test body ever executes.
    def test_non_admin_gets_403(self, operator_client, monkeypatch):
        fake_sessions = FakeSessions(sessions_for_user=[])
        _patch_auth_routes(monkeypatch, sessions=fake_sessions)

        r = operator_client.get("/api/admin/sessions")
        assert r.status_code == 403

    def test_admin_gets_200(self, admin_client, monkeypatch):
        fake_sessions = FakeSessions(sessions_for_user=[])
        _patch_auth_routes(monkeypatch, sessions=fake_sessions)

        r = admin_client.get("/api/admin/sessions")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/account/logout-all
# ---------------------------------------------------------------------------

class TestAccountLogoutAllJson:
    def test_revokes_every_session_with_no_exception_argument(
        self, operator_client, monkeypatch
    ):
        fake_sessions = FakeSessions()
        fake_audit = FakeAudit()
        _patch_auth_routes(monkeypatch, sessions=fake_sessions, audit=fake_audit)

        r = operator_client.post("/api/account/logout-all")

        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert fake_sessions.revoke_all_calls == [(FAKE_OPERATOR_USER_ID, None)]
        assert "logout_all" in [c[1] for c in fake_audit.calls]
