# roast-my-code 🔥

An adversarial AI agent that reviews GitHub Pull Requests by:
1. **Fetching the diff** from any public or private repo
2. **Generating bug hypotheses** using Claude (edge cases, race conditions, logic bugs, etc.)
3. **Writing and running sandboxed pytest tests** that try to *trigger* each suspected bug
4. **Posting a Markdown report** back to the PR with confirmed bugs, false alarms, and notes

> Not a linter. It actually tries to break your code.

---

## Architecture

```
GitHub PR
    │
    ▼
github_client.py  ──  get_pr_diff()
    │                  returns list of {filename, patch, content}
    ▼
agent.py          ──  analyze_diff()
    │                  Claude reads the diff → JSON list of hypotheses
    │                  {file, line_range, concern, severity, suggested_test}
    ▼
sandbox.py        ──  run_hypothesis()
    │                  Claude writes a pytest → runs in isolated tempdir
    │                  returns {passed, test_code, output}
    ▼
agent.py          ──  review_pr()
    │                  collects all results → builds Markdown report
    ▼
github_client.py  ──  post_pr_comment()
                       posts the report as a PR comment
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/your-username/roast-my-code.git
cd roast-my-code
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your tokens
```

You need:
- **`GITHUB_TOKEN`** — [create one here](https://github.com/settings/tokens/new)
  - Required scopes: `repo` (for private repos) or just `public_repo` for public repos
  - Also needs `write:discussion` or `issues:write` to post comments
- **`ANTHROPIC_API_KEY`** — [get one here](https://console.anthropic.com)

### 3. Verify the setup

```bash
# Test GitHub connectivity on a real public PR
python test_fetch.py --repo pallets/flask --pr 5600
```

---

## Usage

```bash
# Full run — analyze and post comment to GitHub
python main.py --repo owner/repo --pr 42

# Dry run — print the report, don't post anything
python main.py --repo owner/repo --pr 42 --dry-run
```

### Example output (console)

```
══════════════ roast-my-code — pallets/flask PR #42 ══════════════
✓ Fetched 3 changed file(s).

Analyzing diff with Claude…
✓ Found 4 potential issue(s).

 Hypotheses from Claude
┌───┬──────────────┬───────┬──────────┬────────────────────────────────────────────┐
│ # │ File         │ Lines │ Severity │ Concern                                    │
├───┼──────────────┼───────┼──────────┼────────────────────────────────────────────┤
│ 1 │ auth.py      │ 42-55 │ HIGH     │ Token comparison not constant-time (timing │
│   │              │       │          │ side-channel)                              │
│ 2 │ utils.py     │ 12-18 │ MEDIUM   │ Division by zero when list is empty        │
│ 3 │ models.py    │ 88    │ LOW      │ Missing __repr__ could mask debug issues   │
└───┴──────────────┴───────┴──────────┴────────────────────────────────────────────┘

Running sandboxed tests for 2 hypothesis(es)…

  Hypothesis 1/2: FAIL — bug confirmed   (auth.py lines 42-55)
  Hypothesis 2/2: PASS — false alarm     (utils.py lines 12-18)

✓ Comment posted: https://github.com/owner/repo/pull/42#issuecomment-...
```

---

## Tips

- Always use `--dry-run` while iterating so you don't spam real PRs
- Test on small repos first — large diffs get expensive with Claude
- The sandbox runs in a throwaway `tempdir` — it never touches your local files
- If a file isn't pure Python, Claude may still flag logic issues from the diff alone (the sandbox just won't be able to run the test)

---

## Project Structure

```
roast-my-code/
├── main.py           # CLI entry point
├── github_client.py  # GitHub API: fetch diff, post comment
├── agent.py          # Claude-powered analysis + full review loop
├── sandbox.py        # Test generation + sandboxed pytest execution
├── test_fetch.py     # Manual smoke-test for GitHub connectivity
├── requirements.txt
├── .env.example
└── README.md
```

---

## Screenshot / Demo

<!-- Add your gif here after recording a demo run -->
![demo placeholder](https://via.placeholder.com/800x400?text=demo+gif+coming+soon)

---

## License

MIT
