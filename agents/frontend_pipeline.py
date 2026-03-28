"""frontend_pipeline.py — ALYASMEEN AuntOps frontend-only pipeline.

Runs 2 agents: Frontend Developer → Visual QA.
Visual QA can send code back to Frontend Dev up to MAX_VQA_RETRIES times on FAIL.
Final output is saved to agents/output/YYYY-MM-DD_HH-MM_fe_<slug>.md

Usage:
    # Pure frontend change (redesign, new UI component)
    python -m agents.frontend_pipeline "redesign the orders page for mobile"

    # After a backend pipeline run — pass its output as context
    python -m agents.frontend_pipeline "broadcast improve UI" --backend agents/output/2026-03-27_...md
"""

import argparse
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic

# Project root is one level up from this file (auntops_fixed/)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Add project root to path so app.services.config is importable
sys.path.insert(0, str(_PROJECT_ROOT))

# Force UTF-8 stdout so Arabic characters don't crash on Windows cp125x terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services.config import Config  # noqa: E402
from agents.prompts import FRONTEND_DEV_SYSTEM, VISUAL_QA_SYSTEM  # noqa: E402

# ── Models ────────────────────────────────────────────────────────────────────
_FE_DEV_MODEL  = "claude-sonnet-4-6"
_VQA_MODEL     = "claude-haiku-4-5-20251001"

# Visual QA retry budget (not counting the first attempt) — keep low to control Sonnet costs
MAX_VQA_RETRIES = 1


# ── Context loading ───────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_existing_templates() -> str:
    """Collect a brief inventory of existing templates so Frontend Dev can match styles."""
    templates_dir = _PROJECT_ROOT / "app" / "templates"
    if not templates_dir.exists():
        return ""
    names = [p.name for p in sorted(templates_dir.glob("*.html"))]
    return "Existing templates: " + ", ".join(names) if names else ""


def _load_backend_output(path: str) -> str:
    """Load a previous backend pipeline output file as context for the Frontend Dev."""
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = _PROJECT_ROOT / path
    content = _read(resolved)
    if not content:
        print(f"[WARNING] --backend file not found or empty: {resolved}")
    return content


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower()[:60]
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "frontend"


def _section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


# ── Agent runners ─────────────────────────────────────────────────────────────

async def _run_frontend_dev(
    client: anthropic.AsyncAnthropic,
    design_brief: str,
    backend_context: str,
    existing_templates: str,
    vqa_feedback: str = "",
) -> str:
    """Frontend Developer: produces HTML templates + JS + CSS. Streams output."""

    # Build system prompt — append backend output if provided
    system = FRONTEND_DEV_SYSTEM
    if existing_templates:
        system += f"\n\n<existing_templates>\n{existing_templates}\n</existing_templates>"
    if backend_context:
        system += (
            "\n\n<backend_output>\n"
            "The following backend code was already approved. Match its API endpoints, "
            "HTTP methods, and JSON field names exactly in your JavaScript.\n\n"
            f"{backend_context}\n</backend_output>"
        )

    # Build user message
    user_parts = [f"<design_brief>\n{design_brief}\n</design_brief>"]
    if vqa_feedback:
        user_parts.append(
            f"\n<visual_qa_feedback>\n{vqa_feedback}\n</visual_qa_feedback>"
            "\n\nPlease fix every issue raised by Visual QA and resubmit all affected files completely."
        )

    parts: list[str] = []
    async with client.messages.stream(
        model=_FE_DEV_MODEL,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
    ) as stream:
        async for chunk in stream.text_stream:
            print(chunk, end="", flush=True)
            parts.append(chunk)

    print()
    return "".join(parts)


async def _run_visual_qa(
    client: anthropic.AsyncAnthropic,
    design_brief: str,
    fe_code: str,
    backend_context: str,
) -> str:
    """Visual QA: checks the Frontend Dev's code against 10 UI/UX rules."""

    system = VISUAL_QA_SYSTEM
    if backend_context:
        system += (
            "\n\n<backend_output>\n"
            "Use this to verify that JS API calls match the approved backend endpoints.\n\n"
            f"{backend_context}\n</backend_output>"
        )

    response = await client.messages.create(
        model=_VQA_MODEL,
        max_tokens=1024,
        system=system,
        messages=[
            {
                "role": "user",
                "content": (
                    f"<design_brief>\n{design_brief}\n</design_brief>"
                    f"\n\n<frontend_code>\n{fe_code}\n</frontend_code>"
                ),
            }
        ],
    )
    return response.content[0].text


# ── Pipeline orchestrator ─────────────────────────────────────────────────────

async def run_frontend_pipeline(
    design_brief: str,
    backend_output_path: str | None = None,
) -> None:
    """Run the frontend-only 2-agent pipeline."""
    client = anthropic.AsyncAnthropic(api_key=Config.CLAUDE_API_KEY)

    # Load optional context
    backend_context = _load_backend_output(backend_output_path) if backend_output_path else ""
    existing_templates = _load_existing_templates()

    print(f"\n{'=' * 60}")
    print("  ALYASMEEN AuntOps — Frontend Pipeline")
    print(f"{'=' * 60}")
    print(f"  Brief:   {design_brief}")
    if backend_output_path:
        print(f"  Backend: {backend_output_path}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── 1. Frontend Developer (first pass) ────────────────────────────────────
    _section("1 / 2 — Frontend Developer  [streaming]")
    fe_code = await _run_frontend_dev(
        client, design_brief, backend_context, existing_templates
    )

    # ── 2. Visual QA with retry loop ──────────────────────────────────────────
    vqa_result = ""
    vqa_passed = False

    for attempt in range(MAX_VQA_RETRIES + 1):
        _section(f"2 / 2 — Visual QA  (attempt {attempt + 1} of {MAX_VQA_RETRIES + 1})")
        vqa_result = await _run_visual_qa(client, design_brief, fe_code, backend_context)
        print(vqa_result)

        first_line = vqa_result.strip().splitlines()[0].strip().upper()
        if first_line.startswith("PASS"):
            print("\n[Visual QA PASSED]")
            vqa_passed = True
            break

        if attempt < MAX_VQA_RETRIES:
            print(f"\n[Visual QA FAILED — returning to Frontend Dev (retry {attempt + 1}/{MAX_VQA_RETRIES})]")
            _section(f"1 / 2 — Frontend Developer  (fix #{attempt + 1})  [streaming]")
            fe_code = await _run_frontend_dev(
                client, design_brief, backend_context, existing_templates, vqa_feedback=vqa_result
            )
        else:
            print(f"\n[Visual QA FAILED after {MAX_VQA_RETRIES} retries — proceeding with last code]")

    # ── Save output ───────────────────────────────────────────────────────────
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    slug = _slugify(design_brief)
    output_path = output_dir / f"{timestamp}_fe_{slug}.md"

    vqa_status = "PASS" if vqa_passed else f"FAIL (after {MAX_VQA_RETRIES} retries)"

    backend_section = ""
    if backend_output_path:
        backend_section = f"\n**Backend context:** `{backend_output_path}`\n"

    output_md = f"""# Frontend Pipeline Output — {design_brief}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Visual QA Status:** {vqa_status}
{backend_section}
---

## Frontend Developer Code

{fe_code}

---

## Visual QA Result

{vqa_result}
"""

    output_path.write_text(output_md, encoding="utf-8")
    print(f"\n{'=' * 60}")
    print(f"  Output saved -> {output_path.relative_to(_PROJECT_ROOT)}")
    print(f"{'=' * 60}\n")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ALYASMEEN AuntOps — Frontend Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python -m agents.frontend_pipeline "redesign orders page for mobile"\n'
            '  python -m agents.frontend_pipeline "broadcast improve UI" '
            "--backend agents/output/2026-03-27_16-20_...md"
        ),
    )
    parser.add_argument("brief", nargs="+", help="Design brief / feature description")
    parser.add_argument(
        "--backend",
        metavar="PATH",
        default=None,
        help="Path to a backend pipeline output .md file (optional)",
    )
    args = parser.parse_args()

    design_brief = " ".join(args.brief)
    asyncio.run(run_frontend_pipeline(design_brief, backend_output_path=args.backend))


if __name__ == "__main__":
    main()
