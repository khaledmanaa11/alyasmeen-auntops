"""
test_auth_flow.py — Integration tests for the operator login / TOTP MFA /
logout flow (app/routers/auth_routes.py).

Monkeypatches the module-level `auth_service` and `sessions` names bound
inside app.routers.auth_routes — NOT the real app.services.auth /
app.services.sessions modules — so these tests never touch Supabase or the
real operator_sessions store. This is exactly why auth_routes.py imports
them as `import ... as auth_service` / `import ... as sessions` rather than
`from ... import specific_function`: it lets a whole-module fake stand in
for both without the real DB/identity provider ever being reachable. Same
pattern as tests/conftest.py's FakeDB (patch the name actually bound at the
call site, not the source module).

The single highest-value assertion in this file: a mfa_required=True sign-in
with no trusted device must NEVER set the session cookie — the
anti-regression test for "a verified TOTP factor can be silently bypassed by
the password grant alone" (see app/services/auth.py's module docstring).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

from app.services.auth import AuthError, AuthResult  # noqa: E402
from app.shared.constants import (  # noqa: E402
    DEVICE_COOKIE_NAME,
    PENDING_LOGIN_COOKIE_NAME,
    SESSION_COOKIE_NAME,
)


class FakeAuthService:
    """Stands in for app.services.auth, patched onto auth_routes.auth_service."""

    def __init__(self, sign_in_result=None, sign_in_error=None, verify_totp_error=None):
        self.sign_in_result = sign_in_result
        self.sign_in_error = sign_in_error
        self.verify_totp_error = verify_totp_error
        self.sign_in_calls: list[tuple[str, str]] = []
        self.verify_totp_calls: list[tuple[str, str, str, str]] = []

    def sign_in(self, email, password):
        self.sign_in_calls.append((email, password))
        if self.sign_in_error is not None:
            raise self.sign_in_error
        return self.sign_in_result

    def verify_totp(self, access_token, refresh_token, factor_id, code):
        self.verify_totp_calls.append((access_token, refresh_token, factor_id, code))
        if self.verify_totp_error is not None:
            raise self.verify_totp_error
        return "verified-user-id"


class FakeSessions:
    """Stands in for app.services.sessions, patched onto auth_routes.sessions.

    A minimal in-memory pending_logins store — single-use, like the real
    thing (consume_pending_login pops the entry) — plus call trackers so
    tests can assert on exactly what auth_routes.py did.
    """

    def __init__(self, trusted_device=None):
        self._trusted_device = trusted_device
        self._pending: dict[str, dict] = {}
        self._pending_seq = 0
        self.created_sessions: list[tuple] = []
        self.remembered_devices: list[tuple] = []
        self.revoke_session_calls: list[str] = []
        self.revoke_all_calls: list[str] = []

    def find_trusted_device(self, user_id, raw_device_token):  # noqa: ARG002
        return self._trusted_device

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

    def create_session(self, user_id, email, is_admin, device_id=None, user_agent=None):  # noqa: ARG002
        self.created_sessions.append((user_id, email, is_admin, device_id))
        return "session-token-raw"

    def revoke_session(self, session_id):
        self.revoke_session_calls.append(session_id)

    def revoke_all_for_user(self, user_id):
        self.revoke_all_calls.append(user_id)


def _patch_auth_routes(monkeypatch, auth_service=None, sessions=None):
    import app.routers.auth_routes as auth_routes

    if auth_service is not None:
        monkeypatch.setattr(auth_routes, "auth_service", auth_service)
    if sessions is not None:
        monkeypatch.setattr(auth_routes, "sessions", sessions)


# ---------------------------------------------------------------------------
# POST /login — bad credentials
# ---------------------------------------------------------------------------

class TestLoginBadCredentials:
    def test_bad_credentials_returns_401_and_no_session_cookie(self, client, monkeypatch):
        fake_auth = FakeAuthService(
            sign_in_error=AuthError("invalid credentials", code="invalid_credentials")
        )
        _patch_auth_routes(monkeypatch, auth_service=fake_auth)

        r = client.post("/login", data={"email": "nope@example.test", "password": "wrong"})

        assert r.status_code == 401
        assert "البريد الإلكتروني أو كلمة المرور غير صحيحة" in r.text
        assert r.cookies.get(SESSION_COOKIE_NAME) is None


# ---------------------------------------------------------------------------
# POST /login — MFA required, no trusted device -> challenge page, no session
# ---------------------------------------------------------------------------

class TestLoginMfaRequired:
    def test_mfa_required_no_trusted_device_shows_challenge_never_sets_session(
        self, client, monkeypatch
    ):
        result = AuthResult(
            user_id="user-1",
            email="aunt@example.test",
            is_admin=False,
            mfa_required=True,
            factor_id="factor-1",
            access_token="aal1-access",
            refresh_token="aal1-refresh",
        )
        fake_auth = FakeAuthService(sign_in_result=result)
        fake_sessions = FakeSessions(trusted_device=None)
        _patch_auth_routes(monkeypatch, auth_service=fake_auth, sessions=fake_sessions)

        r = client.post("/login", data={"email": "aunt@example.test", "password": "correct"})

        assert r.status_code == 200
        assert 'name="code"' in r.text
        # The anti-regression assertion: MFA required means NO session yet.
        assert r.cookies.get(SESSION_COOKIE_NAME) is None
        assert r.cookies.get(PENDING_LOGIN_COOKIE_NAME) is not None

    def test_mfa_required_with_trusted_device_skips_challenge(self, client, monkeypatch):
        result = AuthResult(
            user_id="user-1",
            email="aunt@example.test",
            is_admin=False,
            mfa_required=True,
            factor_id="factor-1",
            access_token="aal1-access",
            refresh_token="aal1-refresh",
        )
        fake_auth = FakeAuthService(sign_in_result=result)
        fake_sessions = FakeSessions(trusted_device={"id": "device-99", "user_id": "user-1"})
        _patch_auth_routes(monkeypatch, auth_service=fake_auth, sessions=fake_sessions)

        r = client.post(
            "/login",
            data={"email": "aunt@example.test", "password": "correct"},
            follow_redirects=False,
        )

        assert r.status_code == 303
        assert r.headers["location"] == "/orders"
        assert r.cookies.get(SESSION_COOKIE_NAME) is not None
        assert len(fake_sessions.created_sessions) == 1
        assert fake_sessions.created_sessions[0][3] == "device-99"  # device_id threaded through


class TestLoginWithoutMfaEnrolled:
    def test_mfa_not_required_signs_in_directly(self, client, monkeypatch):
        """CONTEXT locks enrollment as assisted, not a forced self-serve wall:
        a not-yet-enrolled operator must still be able to sign in."""
        result = AuthResult(
            user_id="user-2",
            email="newop@example.test",
            is_admin=False,
            mfa_required=False,
            factor_id=None,
            access_token="aal1-access",
            refresh_token="aal1-refresh",
        )
        fake_auth = FakeAuthService(sign_in_result=result)
        fake_sessions = FakeSessions()
        _patch_auth_routes(monkeypatch, auth_service=fake_auth, sessions=fake_sessions)

        r = client.post(
            "/login",
            data={"email": "newop@example.test", "password": "correct"},
            follow_redirects=False,
        )

        assert r.status_code == 303
        assert r.headers["location"] == "/orders"
        assert r.cookies.get(SESSION_COOKIE_NAME) is not None
        assert len(fake_sessions.created_sessions) == 1


# ---------------------------------------------------------------------------
# POST /login/mfa
# ---------------------------------------------------------------------------

class TestLoginMfaSubmit:
    def test_wrong_code_returns_401_and_no_session_cookie(self, client, monkeypatch):
        fake_auth = FakeAuthService(
            verify_totp_error=AuthError("mfa_verification_failed", code="mfa_verification_failed")
        )
        fake_sessions = FakeSessions()
        _patch_auth_routes(monkeypatch, auth_service=fake_auth, sessions=fake_sessions)

        pending_token = fake_sessions.create_pending_login(
            "user-1", "aunt@example.test", False, "factor-1", "aal1-access", "aal1-refresh"
        )
        client.cookies.set(PENDING_LOGIN_COOKIE_NAME, pending_token)

        r = client.post("/login/mfa", data={"code": "000000"})

        assert r.status_code == 401
        assert "الرمز غير صحيح" in r.text
        assert r.cookies.get(SESSION_COOKIE_NAME) is None
        # A fresh pending cookie is re-issued so she gets another attempt.
        assert r.cookies.get(PENDING_LOGIN_COOKIE_NAME) is not None

    def test_correct_code_mints_session_and_device_cookie(self, client, monkeypatch):
        fake_auth = FakeAuthService()  # verify_totp succeeds by default
        fake_sessions = FakeSessions()
        _patch_auth_routes(monkeypatch, auth_service=fake_auth, sessions=fake_sessions)

        pending_token = fake_sessions.create_pending_login(
            "user-1", "aunt@example.test", False, "factor-1", "aal1-access", "aal1-refresh"
        )
        client.cookies.set(PENDING_LOGIN_COOKIE_NAME, pending_token)

        r = client.post("/login/mfa", data={"code": "123456"}, follow_redirects=False)

        assert r.status_code == 303
        assert r.headers["location"] == "/orders"
        assert r.cookies.get(SESSION_COOKIE_NAME) is not None
        assert r.cookies.get(DEVICE_COOKIE_NAME) is not None
        assert len(fake_sessions.remembered_devices) == 1
        assert len(fake_sessions.created_sessions) == 1


# ---------------------------------------------------------------------------
# GET /logout, POST /logout-all
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_revokes_only_this_session(self, client, monkeypatch):
        import app.routers.auth_deps as auth_deps
        from app.main import app
        from app.services.sessions import Operator

        fake_sessions = FakeSessions()
        _patch_auth_routes(monkeypatch, sessions=fake_sessions)

        op = Operator(user_id="user-1", email="aunt@example.test", is_admin=False, session_id="sess-1")
        app.dependency_overrides[auth_deps.optional_operator] = lambda: op
        try:
            r = client.get("/logout", follow_redirects=False)
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 303
        assert r.headers["location"] == "/login"
        assert fake_sessions.revoke_session_calls == ["sess-1"]
        assert fake_sessions.revoke_all_calls == []

    def test_logout_all_revokes_every_session_for_user(self, client, monkeypatch):
        import app.routers.auth_deps as auth_deps
        from app.main import app
        from app.services.sessions import Operator

        fake_sessions = FakeSessions()
        _patch_auth_routes(monkeypatch, sessions=fake_sessions)

        op = Operator(user_id="user-1", email="aunt@example.test", is_admin=False, session_id="sess-1")
        app.dependency_overrides[auth_deps.require_operator] = lambda: op
        try:
            r = client.post("/logout-all", follow_redirects=False)
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 303
        assert r.headers["location"] == "/login"
        assert fake_sessions.revoke_all_calls == ["user-1"]
        assert fake_sessions.revoke_session_calls == []
