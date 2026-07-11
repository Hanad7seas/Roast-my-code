"""GitHub API helpers: fetch PR diffs and post comments."""

import os
from typing import Optional
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv()


def _get_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN is not set in your environment / .env file.")
    return Github(auth=Auth.Token(token))


def get_pr_diff(repo_name: str, pr_number: int) -> list[dict]:
    """Fetch a pull request and return a list of changed files.

    Each entry has:
        - filename   : str  — path inside the repo
        - patch      : str  — unified diff text (may be None for binary files)
        - content    : str  — full file content after the change (decoded UTF-8)
        - status     : str  — 'added' | 'modified' | 'removed' | 'renamed'
        - additions  : int
        - deletions  : int
    """
    gh = _get_client()
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    files = []
    for f in pr.get_files():
        content = ""
        if f.status != "removed":
            try:
                file_obj = repo.get_contents(f.filename, ref=pr.head.sha)
                raw = file_obj.decoded_content
                content = raw.decode("utf-8", errors="replace")
            except Exception:
                content = ""

        files.append(
            {
                "filename": f.filename,
                "patch": f.patch or "",
                "content": content,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
            }
        )
    return files


def post_pr_comment(
    repo_name: str,
    pr_number: int,
    markdown_body: str,
    dry_run: bool = False,
) -> Optional[str]:
    """Post a markdown comment on a pull request.

    Returns the comment URL, or None when dry_run is True.
    """
    if dry_run:
        return None

    gh = _get_client()
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    comment = pr.create_issue_comment(markdown_body)
    return comment.html_url
