"""Execute measured Phase 4 notebooks in the existing research kernel."""
from pathlib import Path
import argparse
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ["14_temporal_alignment_and_quality.ipynb", "15_body_progress_analysis.ipynb", "16_progress_dashboard_and_planner_context.ipynb"]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=NOTEBOOKS)
    args = parser.parse_args()
    for name in args.only or NOTEBOOKS:
        path = ROOT / "notebooks" / name
        notebook = nbformat.read(path, as_version=4)
        NotebookClient(notebook, timeout=180, kernel_name="bodym-research", resources={"metadata": {"path": str(ROOT)}}).execute()
        nbformat.write(notebook, path)
        print(f"Executed {name}", flush=True)
