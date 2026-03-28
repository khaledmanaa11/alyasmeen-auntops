"""pipeline.py — ALYASMEEN AuntOps multi-agent pipeline.

Runs 5 agents in sequence:
    Product Manager -> Developer -> QA (retry x2) -> Test Dev -> DevOps

Developer outputs backend Python only (no tests, no frontend).
Test Dev writes pytest files after QA passes.
Final output is saved to agents/output/YYYY-MM-DD_HH-MM_<slug>.md.

Usage:
    python -m agents.pipeline "your feature request here"
"""

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic

# Force UTF-8 stdout so Arabic/box-drawing characters don't crash on Windows cp125x terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Project root is one level up from this file (auntops_fixed/)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Add project root to path so app.services.config is importable
sys.path.insert(0, str(_PROJECT_ROOT))

from app.services.config import Config  # noqa: E402 — must come after sys.path insert
from agents.prompts import DEV_SYSTEM, DEVOPS_SYSTEM, PM_SYSTEM, QA_SYSTEM, TEST_DEV_SYSTEM  # noqa: E402

# ── Models ────────────────────────────────────────────────────────────────────
_PM_MODEL      = "claude-haiku-4-5-20251001"
_DEV_MODEL     = "claude-sonnet-4-6"
_QA_MODEL      = "claude-haiku-4-5-20251001"
_TEST_MODEL    = "claude-haiku-4-5-20251001"
_DEVOPS_MODEL  = "claude-haiku-4-5-20251001"

# QA retry budget (not counting the first attempt) — keep low to control Sonnet costs
MAX_QA_RETRIES = 1


# ── Context loading ───────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    """Read a file; return empty string if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_context() -> dict[str, str]:
    """Load all static context files referenced by the agents."""
    docs = _PROJECT_ROOT / "docs"
    return {
        "claude_md":    _read(_PROJECT_ROOT / "CLAUDE.md"),
        "prd_md":       _read(docs / "PRD.md"),
        "todo_md":      _read(docs / "TODO.md"),
        "requirements": _read(_PROJECT_ROOT / "requirements.txt"),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Convert a feature request string into a safe filename slug."""
    text = text.lower()[:60]
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "pipeline"


def _section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


# ── Agent runners ─────────────────────────────────────────────────────────────

async def _run_pm(
    client: anthropic.AsyncAnthropic,
    feature_request: str,
    ctx: dict[str, str],
) -> str:
    """Product Manager: turns a plain feature request into a structured brief."""
    response = await client.messages.create(
        model=_PM_MODEL,
        max_tokens=1024,
        system=PM_SYSTEM + f"\n\n<prd>\n{ctx['prd_md']}\n</prd>",
        messages=[
            {"role": "user", "content": f"Feature request: {feature_request}"},
        ],
    )
    return response.content[0].text


async def _run_developer(
    client: anthropic.AsyncAnthropic,
    pm_brief: str,
    ctx: dict[str, str],
    qa_feedback: str = "",
) -> str:
    """Developer: produces full file contents from the PM brief. Streams output."""
    user_parts = [f"<pm_brief>\n{pm_brief}\n</pm_brief>"]
    if qa_feedback:
        user_parts.append(
            f"\n<qa_feedback>\n{qa_feedback}\n</qa_feedback>"
            "\n\nPlease fix every issue raised by QA above and resubmit all affected files."
        )

    parts: list[str] = []
    async with client.messages.stream(
        model=_DEV_MODEL,
        max_tokens=8192,
        system=DEV_SYSTEM + f"\n\n<claude_md>\n{ctx['claude_md']}\n</claude_md>",
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
    ) as stream:
        async for chunk in stream.text_stream:
            print(chunk, end="", flush=True)
            parts.append(chunk)

    print()  # final newline after stream ends
    return "".join(parts)


async def _run_qa(
    client: anthropic.AsyncAnthropic,
    pm_brief: str,
    dev_code: str,
    ctx: dict[str, str],
) -> str:
    """QA: checks the Developer's code against 8 rules. Returns PASS or FAIL + issues."""
    response = await client.messages.create(
        model=_QA_MODEL,
        max_tokens=1024,
        system=QA_SYSTEM + f"\n\n<claude_md>\n{ctx['claude_md']}\n</claude_md>",
        messages=[
            {
                "role": "user",
                "content": (
                    f"<pm_brief>\n{pm_brief}\n</pm_brief>"
                    f"\n\n<developer_code>\n{dev_code}\n</developer_code>"
                ),
            }
        ],
    )
    return response.content[0].text


async def _run_devops(
    client: anthropic.AsyncAnthropic,
    approved_code: str,
    ctx: dict[str, str],
) -> str:
    """DevOps: produces a deployment checklist for the approved code."""
    response = await client.messages.create(
        model=_DEVOPS_MODEL,
        max_tokens=1024,
        system=(
            DEVOPS_SYSTEM
            + f"\n\n<todo_md>\n{ctx['todo_md']}\n</todo_md>"
            + f"\n\n<requirements_txt>\n{ctx['requirements']}\n</requirements_txt>"
        ),
        messages=[
            {"role": "user", "content": f"<approved_code>\n{approved_code}\n</approved_code>"},
        ],
    )
    return response.content[0].text


async def _run_test_dev(
    client: anthropic.AsyncAnthropic,
    pm_brief: str,
    dev_code: str,
) -> str:
    """Test Dev: writes pytest files for the approved backend code. Streams output."""
    parts: list[str] = []
    async with client.messages.stream(
        model=_TEST_MODEL,
        max_tokens=4096,
        system=TEST_DEV_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"<pm_brief>\n{pm_brief}\n</pm_brief>"
                    f"\n\n<approved_backend_code>\n{dev_code}\n</approved_backend_code>"
                ),
            }
        ],
    ) as stream:
        async for chunk in stream.text_stream:
            print(chunk, end="", flush=True)
            parts.append(chunk)
    print()
    return "".join(parts)


# ── Pipeline orchestrator ─────────────────────────────────────────────────────

async def run_pipeline(feature_request: str) -> None:
    """Run the full 4-agent pipeline for the given feature request."""
    # AsyncAnthropic picks up the API key from Config (loaded from .env via dotenv)
    client = anthropic.AsyncAnthropic(api_key=Config.CLAUDE_API_KEY)
    ctx = _load_context()

    print(f"\n{'=' * 60}")
    print("  ALYASMEEN AuntOps — Multi-Agent Pipeline")
    print(f"{'=' * 60}")
    print(f"  Feature: {feature_request}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── 1. Product Manager ────────────────────────────────────────────────────
    _section("1 / 5 — Product Manager")
    pm_brief = await _run_pm(client, feature_request, ctx)
    print(pm_brief)

    # ── 2. Developer (first pass) ─────────────────────────────────────────────
    _section("2 / 5 — Developer  [streaming]")
    dev_code = await _run_developer(client, pm_brief, ctx)

    # ── 3. QA with retry loop ─────────────────────────────────────────────────
    qa_result = ""
    qa_passed = False

    for attempt in range(MAX_QA_RETRIES + 1):
        _section(f"3 / 5 — QA  (attempt {attempt + 1} of {MAX_QA_RETRIES + 1})")
        qa_result = await _run_qa(client, pm_brief, dev_code, ctx)
        print(qa_result)

        first_line = qa_result.strip().splitlines()[0].strip().upper()
        if first_line.startswith("PASS"):
            print("\n[QA PASSED]")
            qa_passed = True
            break

        if attempt < MAX_QA_RETRIES:
            print(f"\n[QA FAILED — returning to Developer (retry {attempt + 1}/{MAX_QA_RETRIES})]")
            _section(f"2 / 5 — Developer  (fix #{attempt + 1})  [streaming]")
            dev_code = await _run_developer(client, pm_brief, ctx, qa_feedback=qa_result)
        else:
            print(f"\n[QA FAILED after {MAX_QA_RETRIES} retries — proceeding with last code]")

    # ── 4. Test Dev ───────────────────────────────────────────────────────────
    _section("4 / 5 — Test Developer  [streaming]")
    test_code = await _run_test_dev(client, pm_brief, dev_code)

    # ── 5. DevOps ─────────────────────────────────────────────────────────────
    _section("5 / 5 — DevOps")
    devops_output = await _run_devops(client, dev_code, ctx)
    print(devops_output)

    # ── Save output ───────────────────────────────────────────────────────────
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    slug = _slugify(feature_request)
    output_path = output_dir / f"{timestamp}_{slug}.md"

    qa_status = "PASS" if qa_passed else f"FAIL (after {MAX_QA_RETRIES} retries)"

    output_md = f"""# Pipeline Output — {feature_request}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**QA Status:** {qa_status}

---

## 1. Product Manager Brief

{pm_brief}

---

## 2. Developer Code

{dev_code}

---

## 3. QA Result

{qa_result}

---

## 4. Test Code

{test_code}

---

## 5. DevOps Checklist

{devops_output}
"""

    output_path.write_text(output_md, encoding="utf-8")
    print(f"\n{'=' * 60}")
    print(f"  Output saved -> {output_path.relative_to(_PROJECT_ROOT)}")
    print(f"{'=' * 60}\n")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m agents.pipeline \"your feature request here\"")
        sys.exit(1)

    feature_request = " ".join(sys.argv[1:])
    asyncio.run(run_pipeline(feature_request))


if __name__ == "__main__":
    main()
