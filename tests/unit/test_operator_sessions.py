"""
test_operator_sessions.py — Unit tests for app.services.sessions, the opaque
operator-session store backing operator_sessions / trusted_devices /
pending_logins (see supabase/migrations/20260828000000_operator_auth.sql).

Follows tests/unit/test_processor.py's style: query/execute/execute_returning
are monkeypatched AS BOUND INTO app.services.sessions (Python copies the
reference at `from x import y` time — see tests/conftest.py's module
docstring), backed by a small in-memory fake that routes on keyword-matching
the raw SQL text, mirroring tests/conftest.py's FakeDB pattern for the
WhatsApp-bot tables.
"""
from __future__ import annotations

import hashlib
import itertools
from datetime import datetime, timedelta, timezone

import pytest

import app.services.sessions as sessions


class FakeAuthTables:
    """In-memory stand-in for operator_sessions / trusted_devices /
    pending_logins. Good enough to exercise sessions.py's real SQL-shaping
    and expiry/revocation logic without a real database."""

    def __init__(self) -> None:
        self.operator_sessions: list[dict] = []
        self.trusted_devices: list[dict] = []
        self.pending_logins: list[dict] = []
        self._seq = itertools.count(1)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    # -- SELECT --------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        s = sql.upper()
        now = self._now()

        if "FROM OPERATOR_SESSIONS" in s:
            (token_hash,) = params
            for row in self.operator_sessions:
                if (
                    row["token_hash"] == token_hash
                    and row["revoked_at"] is None
                    and row["expires_at"] > now
                ):
                    return [dict(row)]
            return []

        if "FROM TRUSTED_DEVICES" in s:
            user_id, device_token_hash = params
            for row in self.trusted_devices:
                if (
                    row["user_id"] == user_id
                    and row["device_token_hash"] == device_token_hash
                    and row["mfa_verified_until"] is not None
                    and row["mfa_verified_until"] > now
                ):
                    return [dict(row)]
            return []

        if "FROM PENDING_LOGINS" in s:
            (token_hash,) = params
            for row in self.pending_logins:
                if row["token_hash"] == token_hash and row["expires_at"] > now:
                    return [dict(row)]
            return []

        return []

    # -- INSERT / UPDATE / DELETE (no RETURNING) ------------------------

    def execute(self, sql: str, params: tuple = ()) -> None:
        s = sql.upper()
        now = self._now()

        if "INSERT INTO OPERATOR_SESSIONS" in s:
            user_id, email, is_admin, token_hash, device_id, user_agent = params
            self.operator_sessions.append({
                "id": f"session-{next(self._seq)}",
                "user_id": user_id,
                "email": email,
                "is_admin": is_admin,
                "token_hash": token_hash,
                "device_id": device_id,
                "user_agent": user_agent,
                "created_at": now,
                "last_seen_at": now,
                "expires_at": now + timedelta(days=sessions.SESSION_TTL_DAYS),
                "revoked_at": None,
            })
            return

        if "UPDATE OPERATOR_SESSIONS" in s and "LAST_SEEN_AT" in s:
            (session_id,) = params
            for row in self.operator_sessions:
                if row["id"] == session_id:
                    row["last_seen_at"] = now
            return

        if "UPDATE OPERATOR_SESSIONS" in s and "REVOKED_AT" in s:
            if "USER_ID" in s:
                if len(params) == 2:
                    user_id, except_id = params
                    for row in self.operator_sessions:
                        if (
                            row["user_id"] == user_id
                            and row["revoked_at"] is None
                            and row["id"] != except_id
                        ):
                            row["revoked_at"] = now
                else:
                    (user_id,) = params
                    for row in self.operator_sessions:
                        if row["user_id"] == user_id and row["revoked_at"] is None:
                            row["revoked_at"] = now
            else:
                (session_id,) = params
                for row in self.operator_sessions:
                    if row["id"] == session_id and row["revoked_at"] is None:
                        row["revoked_at"] = now
            return

        if "INSERT INTO PENDING_LOGINS" in s:
            token_hash, user_id, email, is_admin, factor_id, access_token, refresh_token = params
            self.pending_logins.append({
                "id": f"pending-{next(self._seq)}",
                "token_hash": token_hash,
                "user_id": user_id,
                "email": email,
                "is_admin": is_admin,
                "factor_id": factor_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "created_at": now,
                "expires_at": now + timedelta(minutes=sessions.PENDING_LOGIN_TTL_MINUTES),
            })
            return

        if "DELETE FROM PENDING_LOGINS" in s:
            (token_hash,) = params
            self.pending_logins = [
                r for r in self.pending_logins if r["token_hash"] != token_hash
            ]
            return

        return

    # -- INSERT ... RETURNING -------------------------------------------

    def execute_returning(self, sql: str, params: tuple = ()) -> dict | None:
        s = sql.upper()
        now = self._now()

        if "INSERT INTO TRUSTED_DEVICES" in s:
            user_id, device_token_hash, label = params
            existing = next(
                (
                    r for r in self.trusted_devices
                    if r["user_id"] == user_id and r["device_token_hash"] == device_token_hash
                ),
                None,
            )
            if existing:
                existing["mfa_verified_until"] = now + timedelta(days=sessions.DEVICE_MFA_TTL_DAYS)
                existing["last_seen_at"] = now
                return {"id": existing["id"], "created": False}

            row = {
                "id": f"device-{next(self._seq)}",
                "user_id": user_id,
                "device_token_hash": device_token_hash,
                "label": label,
                "mfa_verified_until": now + timedelta(days=sessions.DEVICE_MFA_TTL_DAYS),
                "created_at": now,
                "last_seen_at": now,
            }
            self.trusted_devices.append(row)
            return {"id": row["id"], "created": True}

        return None


@pytest.fixture()
def fake_tables(monkeypatch) -> FakeAuthTables:
    """Patch query/execute/execute_returning as bound into
    app.services.sessions with an in-memory fake, per conftest.py's
    documented pattern for this codebase."""
    fake = FakeAuthTables()
    monkeypatch.setattr(sessions, "query", fake.query)
    monkeypatch.setattr(sessions, "execute", fake.execute)
    monkeypatch.setattr(sessions, "execute_returning", fake.execute_returning)
    return fake


# ---------------------------------------------------------------------------
# 1. create_session never stores the raw token
# ---------------------------------------------------------------------------

def test_create_session_stores_only_the_hash_not_the_raw_token(fake_tables):
    raw = sessions.create_session("u1", "aunt@alyasmeen.org", is_admin=False)

    assert len(fake_tables.operator_sessions) == 1
    stored_hash = fake_tables.operator_sessions[0]["token_hash"]
    assert stored_hash != raw
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == stored_hash


# ---------------------------------------------------------------------------
# 2. lookup_session — hit and every miss path
# ---------------------------------------------------------------------------

class TestLookupSession:
    def test_returns_operator_for_a_live_session(self, fake_tables):
        raw = sessions.create_session("u1", "aunt@alyasmeen.org", is_admin=False)

        op = sessions.lookup_session(raw)

        assert op is not None
        assert op.user_id == "u1"
        assert op.email == "aunt@alyasmeen.org"
        assert op.is_admin is False

    def test_returns_none_for_an_unknown_token(self, fake_tables):
        sessions.create_session("u1", "aunt@alyasmeen.org", is_admin=False)

        assert sessions.lookup_session("not-a-real-token") is None

    def test_returns_none_for_a_revoked_session(self, fake_tables):
        raw = sessions.create_session("u1", "aunt@alyasmeen.org", is_admin=False)
        session_id = fake_tables.operator_sessions[0]["id"]

        sessions.revoke_session(session_id)

        assert sessions.lookup_session(raw) is None

    def test_returns_none_for_an_empty_token(self, fake_tables):
        assert sessions.lookup_session("") is None
        assert sessions.lookup_session(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 3 & 4. revoke_all_for_user — multi-account isolation + exclusion
# ---------------------------------------------------------------------------

class TestRevokeAllForUser:
    def test_scoped_to_one_user_never_touches_another(self, fake_tables):
        raw1 = sessions.create_session("u1", "aunt@alyasmeen.org", is_admin=False)
        raw2 = sessions.create_session("u2", "khaled@alyasmeen.org", is_admin=True)

        sessions.revoke_all_for_user("u1")

        assert sessions.lookup_session(raw1) is None
        assert sessions.lookup_session(raw2) is not None

    def test_can_spare_the_current_session_via_except_session_id(self, fake_tables):
        raw_current = sessions.create_session("u1", "aunt@alyasmeen.org", is_admin=False)
        current_id = fake_tables.operator_sessions[0]["id"]
        raw_other = sessions.create_session("u1", "aunt@alyasmeen.org", is_admin=False, user_agent="phone")

        sessions.revoke_all_for_user("u1", except_session_id=current_id)

        assert sessions.lookup_session(raw_current) is not None
        assert sessions.lookup_session(raw_other) is None


# ---------------------------------------------------------------------------
# 5. find_trusted_device — expired trust window
# ---------------------------------------------------------------------------

def test_find_trusted_device_returns_none_when_trust_window_has_passed(fake_tables):
    device_token = "device-raw-token"
    device_hash = hashlib.sha256(device_token.encode("utf-8")).hexdigest()
    fake_tables.trusted_devices.append({
        "id": "device-1",
        "user_id": "u1",
        "device_token_hash": device_hash,
        "label": "old phone",
        "mfa_verified_until": datetime.now(timezone.utc) - timedelta(days=1),  # expired yesterday
        "created_at": datetime.now(timezone.utc) - timedelta(days=31),
        "last_seen_at": datetime.now(timezone.utc) - timedelta(days=31),
    })

    assert sessions.find_trusted_device("u1", device_token) is None


def test_find_trusted_device_returns_the_row_within_the_trust_window(fake_tables):
    device_token = "device-raw-token"
    device_id, created = sessions.remember_device("u1", device_token, label="laptop")
    assert created is True

    found = sessions.find_trusted_device("u1", device_token)

    assert found is not None
    assert found["id"] == device_id


# ---------------------------------------------------------------------------
# 6. remember_device — created flag only True on first insert
# ---------------------------------------------------------------------------

def test_remember_device_created_flag_only_true_on_first_call(fake_tables):
    device_token = "same-device-token"

    device_id_1, created_1 = sessions.remember_device("u1", device_token)
    device_id_2, created_2 = sessions.remember_device("u1", device_token)

    assert created_1 is True
    assert created_2 is False
    assert device_id_1 == device_id_2
    assert len(fake_tables.trusted_devices) == 1


# ---------------------------------------------------------------------------
# 7. consume_pending_login — single use
# ---------------------------------------------------------------------------

def test_consume_pending_login_is_single_use(fake_tables):
    raw = sessions.create_pending_login(
        user_id="u1",
        email="aunt@alyasmeen.org",
        is_admin=False,
        factor_id="factor-1",
        access_token="access-token",
        refresh_token="refresh-token",
    )

    first = sessions.consume_pending_login(raw)
    second = sessions.consume_pending_login(raw)

    assert first is not None
    assert first["user_id"] == "u1"
    assert first["factor_id"] == "factor-1"
    assert second is None
