"""Sandbox: generate a pytest unit test with Claude and run it in a temp directory."""

import os
import subprocess
import sys
import tempfile
import textwrap

import anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = "claude-opus-4-5"
TEST_TIMEOUT = 30  # seconds

TEST_GEN_SYSTEM = textwrap.dedent("""\
    You are an expert in Python testing. Your task is to write a single pytest test
    function that attempts to expose a suspected bug described by the user.

    Rules:
    - Output ONLY valid Python code. No markdown, no commentary outside the code.
    - The test file must be self-contained: import only the standard library or pytest.
    - Copy/paste or redefine any relevant functions from the provided source code
      directly inside the test file so it runs without installing anything.
    - The test should FAIL if the bug exists and PASS if the code is correct.
    - Use a single test function named `test_hypothesis`.
    - Keep it concise — 50 lines or fewer.
""")


def _generate_test_code(hypothesis: dict, source_code: str) -> str:
    """Ask Claude to write a pytest that targets the described hypothesis."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    user_msg = textwrap.dedent(f"""\
        Bug hypothesis:
        - File: {hypothesis.get('file', 'unknown')}
        - Lines: {hypothesis.get('line_range', '?')}
        - Concern: {hypothesis.get('concern', '')}
        - Suggested test: {hypothesis.get('suggested_test', '')}

        Source code of the file:
        ```python
        {source_code or '# (file content unavailable)'}
        ```

        Write a self-contained pytest file that will FAIL if the bug exists.
    """)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=TEST_GEN_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    return raw


def _run_pytest(test_path: str, work_dir: str) -> tuple[bool, str]:
    """Run pytest on test_path inside work_dir. Returns (passed, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short", "--no-header"],
        capture_output=True,
        text=True,
        cwd=work_dir,
        timeout=TEST_TIMEOUT,
    )
    output = result.stdout + result.stderr
    passed = result.returncode == 0
    return passed, output


def run_hypothesis(hypothesis: dict, source_code: str) -> dict:
    """Generate a test for the hypothesis, run it, return result dict.

    Returns:
        {
            "hypothesis": dict,
            "test_code":  str,
            "passed":     bool,   # True = no bug found, False = bug confirmed
            "output":     str,
        }
    """
    test_code = _generate_test_code(hypothesis, source_code)

    with tempfile.TemporaryDirectory(prefix="roast_sandbox_") as tmpdir:
        test_file = os.path.join(tmpdir, "test_hypothesis.py")
        with open(test_file, "w", encoding="utf-8") as fh:
            fh.write(test_code)

        try:
            passed, output = _run_pytest(test_file, tmpdir)
        except subprocess.TimeoutExpired:
            passed = False
            output = f"[TIMEOUT] pytest did not finish within {TEST_TIMEOUT}s."
        except Exception as exc:
            passed = False
            output = f"[ERROR] Could not run pytest: {exc}"

    return {
        "hypothesis": hypothesis,
        "test_code": test_code,
        "passed": passed,
        "output": output,
    }
