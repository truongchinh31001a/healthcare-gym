"""Execute Phase 2 notebooks against the current measured research artifacts."""
from pathlib import Path
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ["06_bodym_dataset_exploration.ipynb", "07_body_image_preprocessing.ipynb",
             "07_body_feature_extraction.ipynb", "10_model_evaluation.ipynb"]

if __name__ == "__main__":
    for name in NOTEBOOKS:
        path = ROOT / "notebooks" / name
        notebook = nbformat.read(path, as_version=4)
        NotebookClient(notebook, timeout=180, kernel_name="bodym-research",
                       resources={"metadata": {"path": str(ROOT)}}).execute()
        nbformat.write(notebook, path)
        print(f"Executed {name}", flush=True)
