from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = PROJECT_ROOT / "src" / "spawnbound" / "domain"


class ArchitectureTests(unittest.TestCase):
    def test_domain_does_not_import_rendering_frameworks(self) -> None:
        forbidden = ("pygame", "PPlay")
        violations: list[str] = []

        for source_file in DOMAIN_ROOT.rglob("*.py"):
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
            for node in ast.walk(tree):
                imported_modules: list[str] = []
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.append(node.module)

                for module in imported_modules:
                    if module.startswith(forbidden):
                        violations.append(f"{source_file.name}: {module}")

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
