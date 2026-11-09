"""Compatibility entry point. Defaults to a dry run; use --apply for deletion."""
import runpy, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
runpy.run_module("app.maintenance", run_name="__main__")
