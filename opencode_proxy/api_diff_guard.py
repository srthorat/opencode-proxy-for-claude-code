import ast
import logging
import pathlib
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("opencode-proxy.api_diff_guard")


@dataclass
class BreakingChange:
    file: str
    symbol: str
    change_type: str  # "removed" | "signature_changed" | "type_changed"
    detail: str


def _extract_function_signatures(source: str) -> dict[str, str]:
    """Extract {function_name: signature_str} from Python source."""
    sigs: dict[str, str] = {}
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                ret = ast.unparse(node.returns) if node.returns else "None"
                sigs[node.name] = f"({', '.join(args)}) -> {ret}"
    except Exception:
        pass
    return sigs


def _get_git_file_content(repo_dir: pathlib.Path, filepath: pathlib.Path) -> str | None:
    """Fetch file content from HEAD using git show."""
    try:
        rel = filepath.relative_to(repo_dir)
        res = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return None


def check_api_breaking_changes(
    filepath: pathlib.Path,
    workspace_dir: str | pathlib.Path,
) -> list[BreakingChange]:
    """Compare current file function signatures against HEAD to detect breaking API changes."""
    wpath = pathlib.Path(workspace_dir)
    breaking: list[BreakingChange] = []

    if not filepath.exists() or filepath.suffix != ".py":
        return breaking

    head_content = _get_git_file_content(wpath, filepath)
    if head_content is None:
        return breaking  # New file — no baseline to compare

    current_content = filepath.read_text(encoding="utf-8", errors="ignore")
    head_sigs = _extract_function_signatures(head_content)
    current_sigs = _extract_function_signatures(current_content)

    for name, head_sig in head_sigs.items():
        if name not in current_sigs:
            breaking.append(BreakingChange(
                file=str(filepath),
                symbol=name,
                change_type="removed",
                detail=f"Public function '{name}' was REMOVED. This is a breaking API change.",
            ))
        elif current_sigs[name] != head_sig:
            breaking.append(BreakingChange(
                file=str(filepath),
                symbol=name,
                change_type="signature_changed",
                detail=f"Signature of '{name}' changed: {head_sig} → {current_sigs[name]}",
            ))

    if breaking:
        logger.warning("API Diff Guard: %d breaking change(s) detected in %s", len(breaking), filepath.name)
    return breaking
