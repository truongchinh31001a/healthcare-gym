"""Execute the four Module 01 notebooks using the isolated registered kernel."""
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ["01_ocr_dataset_exploration.ipynb", "02_inbody_preprocessing.ipynb",
             "03_ocr_baseline.ipynb", "04_inbody_information_extraction.ipynb"]


if __name__ == "__main__":
    for name in NOTEBOOKS:
        path = ROOT / "notebooks" / name
        notebook = nbformat.read(path, as_version=4)
        NotebookClient(notebook, timeout=180, kernel_name="inbody-ocr",
                       resources={"metadata": {"path": str(ROOT)}}).execute()
        nbformat.write(notebook, path)
        print(f"Executed {name}", flush=True)
