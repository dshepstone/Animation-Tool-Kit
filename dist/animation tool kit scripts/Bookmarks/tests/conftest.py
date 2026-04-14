import os
import sys
from pathlib import Path

# Make the src package importable in all test runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Use an offscreen Qt platform so Qt widget tests run headlessly in CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
