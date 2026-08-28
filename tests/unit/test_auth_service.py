"""
test_auth_service.py — Unit tests for app/services/auth.py

Monkeypatches app.services.auth._anon_client/_admin_client to return fake Supabase
client stand-ins (nested SimpleNamespace/plain objects mirroring the installed
supabase_auth 2.28.3 client's shape) so no test ever hits the network. Covers the
AAL/MFA-required decision in sign_in() — the single highest-value regression test in this
phase, since skipping it is exactly how TOTP becomes decorative — plus is_admin, error
wrapping, admin factor management, TOTP enrollment/verification, and password reset.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Fake Supabase client builders
# ---------------------------------------------------------------------------

def _make_factor(factor_id: str, factor_type: str = "totp", status: str = "verified"):
    return SimpleNamespace(id=factor_id, factor_type=factor_type, status=status, friendly_name="test")


def _make_user(user_id: str = "user-1", email: str = "aunt@example.com", app_metadata=...):
    if app_metadata is ...:
        app_metadata = {}
    return SimpleNamespace(id=user_id, email=email, app_metadata=app_metadata)


def _make_session(access_token: str = "at-1", refresh_token: str = "rt-1", user=None):
    return SimpleNamespace(access_token=access_token, refresh_token=refresh_token, user=user)


class ProviderError(Exception):
    """Stand-in for supabase_auth's AuthApiError — carries a `.code` attribute."""

    def __init__(self, message="Invalid login credentials", code="invalid_credentials"):
        super().__init__(message)
        self.code = code


class FakeMFA:
    """Stands in for client.auth.mfa (the non-admin MFA surface)."""

    def __init__(self, totp_factors=None, aal_current="aal1", aal_next="aal1"):
        self._totp_factors = totp_factors or []
        self._aal_current = aal_current
        self._aal_next = aal_next
        self.challenge_and_verify_calls: list[dict] = []
        self.enroll_calls: list[dict] = []

    def get_authenticator_assurance_level(self):
        return SimpleNamespace(current_level=self._aal_current, next_level=self._aal_next)

    def list_factors(self):
        return SimpleNamespace(all=list(self._totp_factors), totp=list(self._totp_factors), phone=[])

    def challenge_and_verify(self, params):
        self.challenge_and_verify_calls.append(params)
        return SimpleNamespace(
            access_token="new-at",
            refresh_token="new-rt",
            user=_make_user(user_id="user-1"),
        )

    def enroll(self, params):
        self.enroll_calls.append(params)
        return SimpleNamespace(
            id="factor-new",
            totp=SimpleNamespace(qr_code="data:image/svg+xml;utf-8,<svg/>", secret="SECRET"),
        )


class FakeAuthNamespace:
    """Stands in for client.auth on the anon (non-admin) client."""

    def __init__(self, sign_in_result=None, sign_in_error=None, mfa: FakeMFA | None = None):
        self._sign_in_result = sign_in_result
        self._sign_in_error = sign_in_error
        self.mfa = mfa or FakeMFA()
        self.set_session_calls: list[tuple] = []
        self.reset_password_calls: list[tuple] = []

    def sign_in_with_password(self, credentials):
        if self._sign_in_error is not None:
            raise self._sign_in_error
        return self._sign_in_result

    def set_session(self, access_token, refresh_token):
        self.set_session_calls.append((access_token, refresh_token))
        return SimpleNamespace(user=_make_user(user_id="user-1"))

    def reset_password_for_email(self, email, options):
        self.reset_password_calls.append((email, options))


class FakeAdminMFA:
    """Stands in for client.auth.admin.mfa (service_role-only)."""

    def __init__(self, factors=None):
        self._factors = factors or []
        self.deleted: list[dict] = []

    def list_factors(self, params):
        return list(self._factors)

    def delete_factor(self, params):
        self.deleted.append(params)
        return SimpleNamespace(id=params["id"])


class FakeAdminSurface:
    """Stands in for client.auth.admin (service_role-only)."""

    def __init__(self, factors=None, users=None, created_user_id="new-user-id"):
        self.mfa = FakeAdminMFA(factors=factors)
        self._users = users or []
        self._created_user_id = created_user_id
        self.create_user_calls: list[dict] = []

    def create_user(self, attributes):
        self.create_user_calls.append(attributes)
        return SimpleNamespace(user=SimpleNamespace(id=self._created_user_id))

    def list_users(self):
        return list(self._users)


class FakeAdminAuthNamespace:
    """Stands in for client.auth on the admin (service_role) client."""

    def __init__(self, admin: FakeAdminSurface | None = None):
        self.admin = admin or FakeAdminSurface()


class FakeClient:
    def __init__(self, auth_namespace):
        self.auth = auth_namespace


# ---------------------------------------------------------------------------
# sign_in()
# ---------------------------------------------------------------------------

class TestSignIn:
    def test_no_factors_means_mfa_not_required(self, monkeypatch):
        import app.services.auth as auth

        user = _make_user()
        session = _make_session(user=user)
        client = FakeClient(FakeAuthNamespace(
            sign_in_result=SimpleNamespace(session=session, user=user),
            mfa=FakeMFA(totp_factors=[], aal_current="aal1", aal_next="aal1"),
        ))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        result = auth.sign_in("aunt@example.com", "correct-password")

        assert result.mfa_required is False
        assert result.factor_id is None
        assert result.user_id == "user-1"
        assert result.access_token == "at-1"
        assert result.refresh_token == "rt-1"

    def test_verified_totp_factor_at_aal1_requires_mfa(self, monkeypatch):
        """Regression test: this is what stops MFA from silently becoming decorative."""
        import app.services.auth as auth

        user = _make_user()
        session = _make_session(user=user)
        factor = _make_factor("factor-abc")
        client = FakeClient(FakeAuthNamespace(
            sign_in_result=SimpleNamespace(session=session, user=user),
            mfa=FakeMFA(totp_factors=[factor], aal_current="aal1", aal_next="aal2"),
        ))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        result = auth.sign_in("aunt@example.com", "correct-password")

        assert result.mfa_required is True
        assert result.factor_id == "factor-abc"

    def test_verified_totp_but_already_aal2_does_not_require_mfa(self, monkeypatch):
        import app.services.auth as auth

        user = _make_user()
        session = _make_session(user=user)
        factor = _make_factor("factor-abc")
        client = FakeClient(FakeAuthNamespace(
            sign_in_result=SimpleNamespace(session=session, user=user),
            mfa=FakeMFA(totp_factors=[factor], aal_current="aal2", aal_next="aal2"),
        ))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        result = auth.sign_in("aunt@example.com", "correct-password")

        assert result.mfa_required is False
        assert result.factor_id is None

    def test_admin_role_sets_is_admin_true(self, monkeypatch):
        import app.services.auth as auth

        user = _make_user(app_metadata={"role": "admin"})
        session = _make_session(user=user)
        client = FakeClient(FakeAuthNamespace(
            sign_in_result=SimpleNamespace(session=session, user=user),
        ))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        result = auth.sign_in("khaled@example.com", "correct-password")

        assert result.is_admin is True

    def test_missing_app_metadata_role_defaults_to_not_admin(self, monkeypatch):
        import app.services.auth as auth

        user = _make_user(app_metadata={})
        session = _make_session(user=user)
        client = FakeClient(FakeAuthNamespace(
            sign_in_result=SimpleNamespace(session=session, user=user),
        ))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        result = auth.sign_in("aunt@example.com", "correct-password")

        assert result.is_admin is False

    def test_none_app_metadata_defaults_to_not_admin(self, monkeypatch):
        import app.services.auth as auth

        user = SimpleNamespace(id="user-1", email="aunt@example.com", app_metadata=None)
        session = _make_session(user=user)
        client = FakeClient(FakeAuthNamespace(
            sign_in_result=SimpleNamespace(session=session, user=user),
        ))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        result = auth.sign_in("aunt@example.com", "correct-password")

        assert result.is_admin is False

    def test_provider_error_surfaces_as_auth_error(self, monkeypatch):
        import app.services.auth as auth

        client = FakeClient(FakeAuthNamespace(
            sign_in_error=ProviderError("Invalid login credentials", code="invalid_credentials"),
        ))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        with pytest.raises(auth.AuthError) as exc_info:
            auth.sign_in("aunt@example.com", "wrong-password")

        assert not isinstance(exc_info.value, ProviderError)
        assert exc_info.value.code == "invalid_credentials"


# ---------------------------------------------------------------------------
# verify_totp()
# ---------------------------------------------------------------------------

class TestVerifyTotp:
    def test_rehydrates_session_and_returns_verified_user_id(self, monkeypatch):
        import app.services.auth as auth

        mfa = FakeMFA()
        client = FakeClient(FakeAuthNamespace(mfa=mfa))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        user_id = auth.verify_totp("at-1", "rt-1", "factor-abc", "123456")

        assert user_id == "user-1"
        assert mfa.challenge_and_verify_calls == [{"factor_id": "factor-abc", "code": "123456"}]
        assert client.auth.set_session_calls == [("at-1", "rt-1")]


# ---------------------------------------------------------------------------
# enroll_totp() / verify_enrollment()
# ---------------------------------------------------------------------------

class TestEnrollTotp:
    def test_returns_factor_id_qr_code_and_secret_unmodified(self, monkeypatch):
        import app.services.auth as auth

        client = FakeClient(FakeAuthNamespace())
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        result = auth.enroll_totp("at-1", "rt-1")

        assert result == {
            "factor_id": "factor-new",
            "qr_code": "data:image/svg+xml;utf-8,<svg/>",
            "secret": "SECRET",
        }


class TestVerifyEnrollment:
    def test_challenges_and_verifies_the_new_factor(self, monkeypatch):
        import app.services.auth as auth

        mfa = FakeMFA()
        client = FakeClient(FakeAuthNamespace(mfa=mfa))
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        auth.verify_enrollment("at-1", "rt-1", "factor-new", "654321")

        assert mfa.challenge_and_verify_calls == [{"factor_id": "factor-new", "code": "654321"}]


# ---------------------------------------------------------------------------
# admin_list_factors() / admin_delete_all_factors()
# ---------------------------------------------------------------------------

class TestAdminListFactors:
    def test_returns_factor_dicts_verified_and_unverified(self, monkeypatch):
        import app.services.auth as auth

        factors = [_make_factor("f1", status="unverified"), _make_factor("f2")]
        client = FakeClient(FakeAdminAuthNamespace(admin=FakeAdminSurface(factors=factors)))
        monkeypatch.setattr(auth, "_admin_client", lambda: client)

        result = auth.admin_list_factors("user-1")

        assert result == [
            {"id": "f1", "factor_type": "totp", "status": "unverified", "friendly_name": "test"},
            {"id": "f2", "factor_type": "totp", "status": "verified", "friendly_name": "test"},
        ]


class TestAdminDeleteAllFactors:
    def test_deletes_each_listed_factor_and_returns_count(self, monkeypatch):
        import app.services.auth as auth

        factors = [_make_factor("f1"), _make_factor("f2"), _make_factor("f3")]
        admin = FakeAdminSurface(factors=factors)
        client = FakeClient(FakeAdminAuthNamespace(admin=admin))
        monkeypatch.setattr(auth, "_admin_client", lambda: client)

        deleted = auth.admin_delete_all_factors("user-1")

        assert deleted == 3
        assert len(admin.mfa.deleted) == 3
        assert {call["id"] for call in admin.mfa.deleted} == {"f1", "f2", "f3"}
        assert all(call["user_id"] == "user-1" for call in admin.mfa.deleted)

    def test_no_factors_deletes_nothing(self, monkeypatch):
        import app.services.auth as auth

        admin = FakeAdminSurface(factors=[])
        client = FakeClient(FakeAdminAuthNamespace(admin=admin))
        monkeypatch.setattr(auth, "_admin_client", lambda: client)

        deleted = auth.admin_delete_all_factors("user-1")

        assert deleted == 0
        assert admin.mfa.deleted == []


# ---------------------------------------------------------------------------
# admin_create_user() / admin_list_users()
# ---------------------------------------------------------------------------

class TestAdminCreateUser:
    def test_creates_with_email_confirmed_and_role_metadata(self, monkeypatch):
        import app.services.auth as auth

        admin = FakeAdminSurface(created_user_id="new-user-id")
        client = FakeClient(FakeAdminAuthNamespace(admin=admin))
        monkeypatch.setattr(auth, "_admin_client", lambda: client)

        user_id = auth.admin_create_user("aunt@example.com", "temp-pw", "aunt")

        assert user_id == "new-user-id"
        assert admin.create_user_calls == [{
            "email": "aunt@example.com",
            "password": "temp-pw",
            "email_confirm": True,
            "app_metadata": {"role": "aunt"},
        }]


class TestAdminListUsers:
    def test_returns_email_role_and_factor_count(self, monkeypatch):
        import app.services.auth as auth

        users = [
            SimpleNamespace(
                id="u1", email="aunt@example.com",
                app_metadata={"role": "aunt"}, factors=[_make_factor("f1")],
            ),
            SimpleNamespace(id="u2", email="khaled@example.com", app_metadata={"role": "admin"}, factors=None),
        ]
        client = FakeClient(FakeAdminAuthNamespace(admin=FakeAdminSurface(users=users)))
        monkeypatch.setattr(auth, "_admin_client", lambda: client)

        result = auth.admin_list_users()

        assert result == [
            {"id": "u1", "email": "aunt@example.com", "role": "aunt", "factor_count": 1},
            {"id": "u2", "email": "khaled@example.com", "role": "admin", "factor_count": 0},
        ]


# ---------------------------------------------------------------------------
# send_password_reset()
# ---------------------------------------------------------------------------

class TestSendPasswordReset:
    def test_calls_reset_password_with_redirect_to(self, monkeypatch):
        import app.services.auth as auth

        client = FakeClient(FakeAuthNamespace())
        monkeypatch.setattr(auth, "_anon_client", lambda: client)

        auth.send_password_reset("aunt@example.com")

        assert len(client.auth.reset_password_calls) == 1
        email, options = client.auth.reset_password_calls[0]
        assert email == "aunt@example.com"
        assert options["redirect_to"].endswith("/login/reset")
