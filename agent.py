"""Core agent logic: diff analysis (Claude) and full PR review loop."""

import json
import os
import re
import textwrap
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from github_client import get_pr_diff
from sandbox import run_hypothesis

load_dotenv()

console = Console()

CLAUDE_MODEL = "claude-opus-4-5"

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior software engineer performing an adversarial code review.
    Your job is to find real, exploitable bugs — not style issues or nitpicks.

    Look specifically for:
    - Edge cases and boundary conditions (off-by-one, empty inputs, None/null)
    - Unhandled exceptions and missing error paths
    - Race conditions and concurrency hazards
    - Logic bugs (wrong operator, incorrect condition, swapped arguments)
    - Security issues (injection, path traversal, insecure defaults)
    - Resource leaks (file handles, DB connections, threads not joined)

    Respond ONLY with a valid JSON array. Each element must be an object with
    exactly these keys:
    {
        "file":           "<filename>",
        "line_range":     "<e.g. 42-55>",
        "concern":        "<clear one-sentence description of the bug>",
        "severity":       "<low | medium | high | critical>",
        "suggested_test": "<description of a pytest test that would expose this bug>"
    }

    If you find no issues, return an empty array: []
    Do NOT include markdown fences, commentary, or any text outside the JSON.
""")


def _build_diff_message(files: list[dict]) -> str:
    parts = []
    for f in files:
        parts.append(f"### File: {f['filename']}  (status: {f['status']})")
        if f["patch"]:
            parts.append("#### Diff (unified patch):")
            parts.append(f"```diff\n{f['patch']}\n```")
        if f["content"]:
            lang = f["filename"].rsplit(".", 1)[-1] if "." in f["filename"] else "text"
            parts.append("#### Full file content after change:")
            parts.append(f"```{lang}\n{f['content']}\n```")
        parts.append("")
    return "\n".join(parts)


def analyze_diff(files: list[dict]) -> list[dict]:
    """Send the diff to Claude and return a list of hypothesis dicts."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    diff_message = _build_diff_message(files)

    with console.status("[bold cyan]Sending diff to Claude for analysis…"):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Analyze the following pull request diff and return your "
                        "findings as a JSON array.\n\n" + diff_message
                    ),
                }
            ],
        )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fences if Claude adds them
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\n?```$", "", raw, flags=re.MULTILINE)

    hypotheses: list[dict] = json.loads(raw)
    return hypotheses


def _print_hypotheses(hypotheses: list[dict]) -> None:
    if not hypotheses:
        console.print("[green]No issues found by static analysis.[/green]")
        return

    table = Table(title="Hypotheses from Claude", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("File", style="cyan")
    table.add_column("Lines", style="magenta")
    table.add_column("Severity", style="bold")
    table.add_column("Concern")

    severity_colors = {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}

    for i, h in enumerate(hypotheses, 1):
        sev = h.get("severity", "low").lower()
        color = severity_colors.get(sev, "white")
        table.add_row(
            str(i),
            h.get("file", "?"),
            h.get("line_range", "?"),
            f"[{color}]{sev.upper()}[/{color}]",
            h.get("concern", ""),
        )
    console.print(table)


def _build_markdown_report(
    repo_name: str,
    pr_number: int,
    hypotheses: list[dict],
    test_results: list[dict],
) -> str:
    confirmed = [r for r in test_results if not r["passed"]]
    false_alarms = [r for r in test_results if r["passed"]]
    untested = [
        h for h in hypotheses
        if h.get("severity", "low").lower() in ("low",)
    ]

    lines = [
        "## 🤖 roast-my-code — Automated PR Review",
        f"",
        f"**Repo:** `{repo_name}` &nbsp;|&nbsp; **PR:** #{pr_number} &nbsp;|&nbsp; "
        f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        f"### Summary",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Hypotheses generated | {len(hypotheses)} |",
        f"| Hypotheses tested | {len(test_results)} |",
        f"| **Confirmed bugs** (failing tests) | **{len(confirmed)}** |",
        f"| False alarms (tests passed) | {len(false_alarms)} |",
        f"| Low-severity (not tested) | {len(untested)} |",
        "",
    ]

    if confirmed:
        lines += ["---", "", "### 🔴 Confirmed Bugs", ""]
        for r in confirmed:
            h = r["hypothesis"]
            lines += [
                f"#### `{h['file']}` — lines {h['line_range']}",
                f"> **{h['severity'].upper()}** — {h['concern']}",
                "",
                "<details><summary>Generated test (FAILING)</summary>",
                "",
                "```python",
                r["test_code"],
                "```",
                "",
                "<details><summary>pytest output</summary>",
                "",
                "```",
                r["output"][:2000],
                "```",
                "",
                "</details>",
                "</details>",
                "",
            ]

    if false_alarms:
        lines += ["---", "", "### 🟡 False Alarms (tests passed — likely safe)", ""]
        for r in false_alarms:
            h = r["hypothesis"]
            lines += [
                f"- **`{h['file']}`** lines {h['line_range']}: {h['concern']}",
            ]
        lines.append("")

    if untested:
        lines += ["---", "", "### 🔵 Low-Severity Notes (not tested)", ""]
        for h in untested:
            lines += [
                f"- **`{h['file']}`** lines {h['line_range']}: {h['concern']}",
            ]
        lines.append("")

    lines += [
        "---",
        "",
        "<sub>Generated by [roast-my-code](https://github.com/your-username/roast-my-code) "
        "— diff → hypothesis → sandboxed pytest → report</sub>",
    ]

    return "\n".join(lines)


def review_pr(repo_name: str, pr_number: int) -> str:
    """Full agent loop: fetch → analyze → test → report. Returns Markdown string."""

    console.rule(f"[bold cyan]roast-my-code[/bold cyan] — {repo_name} PR #{pr_number}")

    # Step 1: fetch diff
    with console.status("[bold blue]Fetching PR diff from GitHub…"):
        files = get_pr_diff(repo_name, pr_number)
    console.print(f"[green]✓[/green] Fetched {len(files)} changed file(s).")

    # Step 2: analyze
    console.print("\n[bold]Analyzing diff with Claude…[/bold]")
    hypotheses = analyze_diff(files)
    console.print(f"[green]✓[/green] Found {len(hypotheses)} potential issue(s).\n")
    _print_hypotheses(hypotheses)

    # Step 3: test medium/high/critical hypotheses
    TESTABLE_SEVERITIES = {"medium", "high", "critical"}
    to_test = [h for h in hypotheses if h.get("severity", "low").lower() in TESTABLE_SEVERITIES]

    # Build a quick filename → content map for the sandbox
    file_map = {f["filename"]: f["content"] for f in files}

    test_results = []
    if to_test:
        console.print(f"\n[bold]Running sandboxed tests for {len(to_test)} hypothesis(es)…[/bold]\n")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("", total=len(to_test))
            for i, hypothesis in enumerate(to_test, 1):
                fname = hypothesis.get("file", "")
                progress.update(
                    task,
                    description=(
                        f"Testing hypothesis {i}/{len(to_test)}: "
                        f"[cyan]{fname}[/cyan] lines {hypothesis.get('line_range','?')}"
                    ),
                )
                code = file_map.get(fname, "")
                result = run_hypothesis(hypothesis, code)
                test_results.append(result)

                status = "[red]FAIL — bug confirmed[/red]" if not result["passed"] else "[green]PASS — false alarm[/green]"
                console.print(f"  Hypothesis {i}/{len(to_test)}: {status}")
                progress.advance(task)
    else:
        console.print("[dim]No medium+ severity hypotheses to test.[/dim]")

    # Step 4: build report
    report = _build_markdown_report(repo_name, pr_number, hypotheses, test_results)

    console.print("\n")
    console.print(Panel(report[:3000] + ("…" if len(report) > 3000 else ""), title="[bold]Final Report Preview[/bold]"))

    return report
