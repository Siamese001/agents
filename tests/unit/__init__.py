
from pathlib import Path
_RG_TESTS_UNIT = Path(__file__).resolve().parents[2] / 'resume_graph_engine' / 'tests' / 'unit'
if _RG_TESTS_UNIT.is_dir() and str(_RG_TESTS_UNIT) not in __path__:
    __path__.append(str(_RG_TESTS_UNIT))
