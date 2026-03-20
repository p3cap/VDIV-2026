from pathlib import Path
import sys


CPP_PATHFIND_DIR = Path(__file__).resolve().parent / "cpp_pathfind"

if CPP_PATHFIND_DIR.is_dir():
    cpp_pathfind_dir = str(CPP_PATHFIND_DIR)
    if cpp_pathfind_dir not in sys.path:
        sys.path.insert(0, cpp_pathfind_dir)

try:
    import cpp_path as cpp_mod
    CPP_AVAILABLE = True
except Exception:
    cpp_mod = None
    CPP_AVAILABLE = False
