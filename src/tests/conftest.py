import sys
from pathlib import Path

# Ajoute la racine du projet au PYTHONPATH (parent de src/)
# parents[0] = tests/, parents[1] = src/, parents[2] = racine projet
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
