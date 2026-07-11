"""Entry point for roast-my-code.

Usage:
    python main.py --repo owner/repo --pr 42
    python main.py --repo owner/repo --pr 42 --dry-run
"""

import argparse
import sys

from rich.console import Console

from agent import review_pr
from github_client import post_pr_comment

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="roast-my-code",
        description="Adversarial AI code reviewer for GitHub Pull Requests",
    )
    parser.add_argument(
        "--repo",
        required=True,
        metavar="OWNER/REPO",
        help="GitHub repository (e.g. pallets/flask)",
    )
    parser.add_argument(
        "--pr",
        required=True,
        type=int,
        metavar="NUMBER",
        help="Pull request number",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report instead of posting it to GitHub",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        report = review_pr(args.repo, args.pr)
    except Exception as exc:
        console.print(f"[bold red]Error during analysis:[/bold red] {exc}")
        sys.exit(1)

    if args.dry_run:
        console.rule("[yellow]DRY RUN — report not posted[/yellow]")
        console.print(report)
    else:
        console.print("\n[bold blue]Posting comment to GitHub…[/bold blue]")
        try:
            url = post_pr_comment(args.repo, args.pr, report)
            console.print(f"[green]✓ Comment posted:[/green] {url}")
        except Exception as exc:
            console.print(f"[bold red]Failed to post comment:[/bold red] {exc}")
            console.print("[dim]Report content:[/dim]")
            console.print(report)
            sys.exit(1)


if __name__ == "__main__":
    main()
