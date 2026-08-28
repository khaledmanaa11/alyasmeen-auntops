"""
manage_operators.py — One-off CLI to create the two dashboard operator accounts (the aunt
+ Khaled/admin), list them, and perform admin-driven recovery for a lost phone or a
forgotten password.

Usage:
    python scripts/manage_operators.py create --email aunt@example.com --role aunt
    python scripts/manage_operators.py create --email khaled@example.com --role admin --password "..."
    python scripts/manage_operators.py list
    python scripts/manage_operators.py reset-mfa --email aunt@example.com
    python scripts/manage_operators.py reset-password --email aunt@example.com

Rules followed:
- Every Supabase Auth call goes through app.services.auth (never imports supabase directly)
- Loads secrets via app.services.config (never hardcodes secrets)
- Refuses to run against an unconfigured project (missing SUPABASE_KEY) with a clear message
"""
import argparse
import secrets
import sys
from pathlib import Path

# Force UTF-8 output so Arabic + emoji print correctly on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make `app.*` importable when running from project root or scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.auth as auth  # noqa: E402
from app.services.config import Config  # noqa: E402


def _require_configured() -> None:
    """Refuse to run any subcommand without a service_role key — every subcommand below
    hits the admin surface, which requires it."""
    if not Config.SUPABASE_KEY:
        print("❌ SUPABASE_KEY is not set — this script needs the service_role key to")
        print("   manage operator accounts. Set it in your environment/.env and retry.")
        sys.exit(1)


def _find_user_by_email(email: str) -> dict | None:
    for user in auth.admin_list_users():
        if user["email"] and user["email"].lower() == email.lower():
            return user
    return None


def cmd_create(args: argparse.Namespace) -> None:
    password = args.password or secrets.token_urlsafe(16)
    try:
        user_id = auth.admin_create_user(args.email, password, args.role)
    except auth.AuthError as exc:
        print(f"❌ Failed to create {args.email}: {exc} (code={exc.code})")
        sys.exit(1)
    print(f"✅ Created {args.role} account: {args.email}")
    print(f"   user_id: {user_id}")
    if not args.password:
        print(f"   Temporary password (shown once — she must change it): {password}")
    print("   Remind the operator to sign in and change this password soon.")
    print("   Next: enroll TOTP together at /account (assisted enrollment — see")
    print("   docs/OPERATOR_ACCOUNTS.md).")


def cmd_list(_args: argparse.Namespace) -> None:
    try:
        users = auth.admin_list_users()
    except auth.AuthError as exc:
        print(f"❌ Failed to list users: {exc} (code={exc.code})")
        sys.exit(1)
    if not users:
        print("No operator accounts exist yet. Use `create` to add one.")
        return
    print(f"{'email':35} {'user_id':38} {'role':8} factors")
    for u in users:
        email = u["email"] or "(no email)"
        role = u["role"] or "(none)"
        print(f"{email:35} {u['id']:38} {role:8} {u['factor_count']}")


def cmd_reset_mfa(args: argparse.Namespace) -> None:
    user = _find_user_by_email(args.email)
    if user is None:
        print(f"❌ No account found for {args.email}")
        sys.exit(1)
    try:
        deleted = auth.admin_delete_all_factors(user["id"])
    except auth.AuthError as exc:
        print(f"❌ Failed to reset MFA for {args.email}: {exc} (code={exc.code})")
        sys.exit(1)
    print(f"✅ Removed {deleted} MFA factor(s) for {args.email}")
    print("   Next steps (out-of-band lost-phone escape hatch — see docs/OPERATOR_ACCOUNTS.md):")
    print("   1. Revoke ALL of this operator's dashboard sessions (the in-app 'log out")
    print("      everywhere' flow does this automatically once 05-09 ships an in-app")
    print("      MFA-reset path; done via this script, do it manually until then).")
    print("   2. Sit with the operator and re-enroll TOTP together at /account.")


def cmd_reset_password(args: argparse.Namespace) -> None:
    try:
        auth.send_password_reset(args.email)
    except auth.AuthError as exc:
        print(f"❌ Failed to send password reset to {args.email}: {exc} (code={exc.code})")
        sys.exit(1)
    print(f"✅ Password reset email sent to {args.email}")
    print("   Note: Supabase's built-in email provider is capped at 2 emails/hour")
    print("   project-wide — don't repeat this more than a couple of times per hour.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage ALYASMEEN AuntOps dashboard operator accounts"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create an operator account")
    p_create.add_argument("--email", required=True)
    p_create.add_argument("--role", required=True, choices=["aunt", "admin"])
    p_create.add_argument(
        "--password", default=None, help="Omit to auto-generate a temporary password"
    )
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="List all operator accounts")
    p_list.set_defaults(func=cmd_list)

    p_reset_mfa = sub.add_parser(
        "reset-mfa", help="Delete all MFA factors for an operator (lost-phone recovery)"
    )
    p_reset_mfa.add_argument("--email", required=True)
    p_reset_mfa.set_defaults(func=cmd_reset_mfa)

    p_reset_pw = sub.add_parser(
        "reset-password", help="Send a password-reset email to an operator"
    )
    p_reset_pw.add_argument("--email", required=True)
    p_reset_pw.set_defaults(func=cmd_reset_password)

    args = parser.parse_args()
    _require_configured()
    args.func(args)


if __name__ == "__main__":
    main()
