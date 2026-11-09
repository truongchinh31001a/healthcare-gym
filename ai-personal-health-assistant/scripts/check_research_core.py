"""Audit the packaged snapshot; optionally check its original research checkout."""
from pathlib import Path
import hashlib, json
root = Path(__file__).resolve().parents[1]
package = root / "packages/health-core"
manifest = json.loads((package / "source-manifest.json").read_text(encoding="utf-8"))
for relative, expected in manifest["packaged_sha256"].items():
    source = package / relative
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"Packaged snapshot changed: {relative}")
checked = 0
for relative, expected in manifest["research_source_sha256"].items():
    source = root.parent / relative
    if source.is_file():
        checked += 1
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Research source changed: {relative}; review and update the snapshot explicitly")
print(f"Verified {len(manifest['packaged_sha256'])} packaged files and {checked} available research sources")
