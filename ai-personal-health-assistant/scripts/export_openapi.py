"""Export the current API schema without connecting to the database."""
import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps/api"))
from app.main import app
target = root / "packages/contracts/openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(target)
