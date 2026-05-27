"""Make tests importable from project root (so `from utils.x import y` works)."""
from __future__ import annotations

import os
import sys

# Add poly-news-bot/ root to sys.path so tests can import the project modules.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)