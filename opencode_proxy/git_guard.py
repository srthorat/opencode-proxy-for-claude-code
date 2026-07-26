import logging
import os
import pathlib
import subprocess
from typing import Tuple

logger = logging.getLogger("opencode-proxy.git_guard")


def create_isolated_worktree(repo_dir: str | pathlib.Path, branch_name: str = "opencode-proxy-temp") -> Tuple[bool, str]:
    """Create a temporary git worktree to isolate major refactoring tasks from main working branch."""
    repo_path = pathlib.Path(repo_dir)
    if not (repo_path / ".git").exists():
        return False, str(repo_path)

    worktree_path = repo_path / ".git" / "opencode_worktrees" / branch_name
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cmd = ["git", "worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"]
        res = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, check=False)
        if res.returncode == 0:
            logger.info("Created isolated git worktree at %s", worktree_path)
            return True, str(worktree_path)
        else:
            logger.warning("Worktree creation notice: %s", res.stderr.strip())
            return False, str(repo_path)
    except Exception as exc:
        logger.warning("Failed git worktree isolation: %s", exc)
        return False, str(repo_path)


def cleanup_isolated_worktree(repo_dir: str | pathlib.Path, branch_name: str = "opencode-proxy-temp", merge_success: bool = False) -> bool:
    """Remove temporary git worktree, optionally merging back on success or reverting cleanly on failure."""
    repo_path = pathlib.Path(repo_dir)
    worktree_path = repo_path / ".git" / "opencode_worktrees" / branch_name

    if not worktree_path.exists():
        return True

    try:
        if merge_success:
            subprocess.run(["git", "merge", branch_name], cwd=str(repo_path), capture_output=True, check=False)

        subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=str(repo_path), capture_output=True, check=False)
        subprocess.run(["git", "branch", "-D", branch_name], cwd=str(repo_path), capture_output=True, check=False)
        logger.info("Cleaned up git worktree: %s", branch_name)
        return True
    except Exception as exc:
        logger.warning("Failed git worktree cleanup: %s", exc)
        return False
