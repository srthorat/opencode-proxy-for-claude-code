"""
opencode-proxy ast_repair
──────────────────────────
AST Dependency Auto-Repair Engine: Auto-detects missing module imports
or undefined symbol references in AI code outputs and injects missing imports.
"""
import ast
import logging
from typing import Tuple

logger = logging.getLogger("opencode-proxy.ast_repair")


def auto_repair_missing_imports(code_str: str) -> Tuple[str, bool]:
    """Inspect Python code for undefined NameErrors and auto-inject standard imports."""
    if not code_str or not isinstance(code_str, str) or "def " not in code_str:
        return code_str, False

    missing_modules: set[str] = set()

    # Common standard library symbol mappings
    SYMBOL_MAP = {
        "json": "import json",
        "sys": "import sys",
        "os": "import os",
        "re": "import re",
        "time": "import time",
        "pathlib": "import pathlib",
        "Path": "from pathlib import Path",
        "asyncio": "import asyncio",
        "logging": "import logging",
        "Any": "from typing import Any",
        "Dict": "from typing import Dict",
        "List": "from typing import List",
        "Tuple": "from typing import Tuple",
        "Optional": "from typing import Optional",
    }

    try:
        tree = ast.parse(code_str)
        defined_names: set[str] = set()
        used_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)

        for sym, import_stmt in SYMBOL_MAP.items():
            if sym in used_names and sym not in defined_names:
                missing_modules.add(import_stmt)

        if missing_modules:
            imports_block = "\n".join(sorted(missing_modules))
            repaired_code = f"{imports_block}\n\n{code_str}"
            logger.info("AST Auto-Repair: Auto-injected missing import statements: %s", missing_modules)
            return repaired_code, True

    except Exception as exc:
        logger.debug("AST Auto-Repair inspection error: %s", exc)

    return code_str, False
