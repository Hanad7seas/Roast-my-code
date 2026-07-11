"""Quick smoke-test: fetch a real public PR and print the diff summary.

Usage:
    python test_fetch.py
    python test_fetch.py --repo pallets/flask --pr 5600
"""

import argparse
from github_client import get_pr_diff

DEFAULT_REPO = "pallets/flask"
DEFAULT_PR = 5600


def main():
    parser = argparse.ArgumentParser(description="Test PR diff fetching")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo")
    parser.add_argument("--pr", type=int, default=DEFAULT_PR, help="PR number")
    args = parser.parse_args()

    print(f"\nFetching PR #{args.pr} from {args.repo} ...\n")
    files = get_pr_diff(args.repo, args.pr)

    print(f"Found {len(files)} changed file(s):\n")
    for f in files:
        patch_lines = len(f["patch"].splitlines()) if f["patch"] else 0
        print(
            f"  [{f['status'].upper():8}] {f['filename']}"
            f"  (+{f['additions']} / -{f['deletions']}, {patch_lines} patch lines)"
        )

    if files:
        print(f"\n--- patch preview for first file: {files[0]['filename']} ---")
        preview = "\n".join(files[0]["patch"].splitlines()[:30])
        print(preview or "(no patch text)")


if __name__ == "__main__":
    main()
