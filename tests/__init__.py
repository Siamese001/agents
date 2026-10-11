
from pathlib import Path
_RG_TESTS = Path(__file__).resolve().parent.parent / 'resume_graph_engine' / 'tests'
if _RG_TESTS.is_dir() and str(_RG_TESTS) not in __path__:
    __path__.append(str(_RG_TESTS))
