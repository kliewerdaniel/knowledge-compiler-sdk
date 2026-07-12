import os
import sys

import pytest

# Make the repo root importable so `from compiler.core import ...` works.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from compiler.core import PassRegistry  # noqa: E402

PASSES_ROOT = os.path.join(ROOT, "compiler", "passes")


@pytest.fixture
def registry():
    return PassRegistry(PASSES_ROOT)


@pytest.fixture
def sample_corpus(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.md").write_text(
        "# Title One\n\nIntro. See [other](b.md).\n\n## 1. Methods\n\nParse Markdown.\n"
    )
    (d / "b.md").write_text(
        "# Title Two\n\nBackground.\n\n## 1. Background\n\nLLVM is infra.\n"
    )
    return str(d)
