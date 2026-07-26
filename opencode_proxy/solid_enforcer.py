import ast
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("opencode-proxy.solid_enforcer")


@dataclass
class SolidViolation:
    principle: str
    detail: str
    severity: str  # "high" | "medium" | "low"


def check_single_responsibility(tree: ast.AST) -> list[SolidViolation]:
    """SRP: Classes should have one reason to change — flag classes doing too many things."""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(methods) > 10:
                violations.append(SolidViolation(
                    principle="Single Responsibility Principle (SRP)",
                    detail=f"Class '{node.name}' has {len(methods)} methods. Consider splitting into focused classes.",
                    severity="medium",
                ))
    return violations


def check_dependency_inversion(tree: ast.AST) -> list[SolidViolation]:
    """DIP: Flag concrete class instantiation inside other classes (should depend on abstractions)."""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name) and child.func.id[0].isupper():
                        violations.append(SolidViolation(
                            principle="Dependency Inversion Principle (DIP)",
                            detail=f"Direct concrete instantiation of '{child.func.id}' inside '{node.name}'. Prefer dependency injection.",
                            severity="low",
                        ))
                        break
    return violations


def enforce_solid_on_code(code_str: str) -> list[SolidViolation]:
    """Run all SOLID principle checks on a Python code block."""
    if not code_str or not isinstance(code_str, str):
        return []
    try:
        tree = ast.parse(code_str)
    except Exception:
        return []

    violations: list[SolidViolation] = []
    violations.extend(check_single_responsibility(tree))
    violations.extend(check_dependency_inversion(tree))
    return violations


def format_solid_report(violations: list[SolidViolation]) -> str:
    if not violations:
        return "✔ SOLID Principles: No violations detected."
    lines = ["⚠ SOLID Principle Violations Detected:"]
    for v in violations:
        lines.append(f"  [{v.severity.upper()}] {v.principle}: {v.detail}")
    return "\n".join(lines)
