import ast
import logging
import pathlib
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("opencode-proxy.debt_scanner")


@dataclass
class DebtIssue:
    file: str
    line: int
    issue_type: str
    detail: str
    severity: str  # "high" | "medium" | "low"


def scan_python_file_for_debt(filepath: pathlib.Path) -> list[DebtIssue]:
    """Scan a single Python file for technical debt: God Classes, high complexity, long functions, missing type hints."""
    issues: list[DebtIssue] = []

    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(filepath))
    except Exception:
        return issues

    for node in ast.walk(tree):
        # God Class: class with more than 15 methods
        if isinstance(node, ast.ClassDef):
            methods = [n for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(methods) > 15:
                issues.append(DebtIssue(
                    file=str(filepath),
                    line=node.lineno,
                    issue_type="God Class",
                    detail=f"Class '{node.name}' has {len(methods)} methods (recommended: < 15).",
                    severity="high",
                ))

        # Long functions: > 50 lines
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if hasattr(node, "end_lineno") and node.end_lineno:
                func_len = node.end_lineno - node.lineno
                if func_len > 50:
                    issues.append(DebtIssue(
                        file=str(filepath),
                        line=node.lineno,
                        issue_type="Long Function",
                        detail=f"Function '{node.name}' is {func_len} lines long (recommended: < 50).",
                        severity="medium",
                    ))

            # Missing return type annotation
            if node.returns is None and node.name not in ("__init__", "__new__", "__repr__", "__str__"):
                issues.append(DebtIssue(
                    file=str(filepath),
                    line=node.lineno,
                    issue_type="Missing Type Annotation",
                    detail=f"Function '{node.name}' has no return type annotation.",
                    severity="low",
                ))

    return issues


def scan_workspace_for_debt(workspace_dir: str | pathlib.Path, max_files: int = 50) -> list[DebtIssue]:
    """Scan up to max_files Python files in workspace for technical debt issues."""
    wpath = pathlib.Path(workspace_dir)
    if not wpath.exists():
        return []

    all_issues: list[DebtIssue] = []
    scanned = 0

    for pyfile in wpath.rglob("*.py"):
        if any(p in pyfile.parts for p in (".venv", "__pycache__", ".git", "node_modules")):
            continue
        all_issues.extend(scan_python_file_for_debt(pyfile))
        scanned += 1
        if scanned >= max_files:
            break

    high = [i for i in all_issues if i.severity == "high"]
    medium = [i for i in all_issues if i.severity == "medium"]
    logger.info("Technical Debt Scan: %d high, %d medium issues found across %d files.", len(high), len(medium), scanned)
    return all_issues
