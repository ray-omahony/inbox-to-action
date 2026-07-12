"""Make src/ importable from the tests without installing the package.

pytest imports this file automatically before any test module. For a
single-script project this one path insert beats packaging ceremony
(pyproject.toml, editable installs) we don't otherwise need.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
