import os
import sys
from pathlib import Path

# Make the src package importable in all test runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Use an offscreen Qt platform so Qt widget tests run headlessly in CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The integration tests need a live Maya session (maya.cmds). Outside Maya
# they used to raise ImportError during collection and abort the whole run;
# skip collecting them instead so `pytest` works in CI and on a workstation.
try:
    import maya.cmds  # noqa: F401
except ImportError:
    collect_ignore_glob = ["integration/*"]
