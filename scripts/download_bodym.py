"""Download and verify the public BodyM S3 bucket; no dependencies required."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path, PurePosixPath
import re
import time
import threading
from urllib.parse import quote, urlencode, urlsplit
import xml.etree.ElementTree as ET


BASE_URL = "https://amazon-bodym.s3.us-west-2.amazonaws.com"
DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / "data/raw/bodym"
NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
CONNECTIONS = threading.local()


def fetch(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != urlsplit(BASE_URL).netloc:
        raise ValueError(f"Unexpected download URL: {url}")
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    for attempt in range(5):
        try:
            connection = getattr(CONNECTIONS, "connection", None)
            if connection is None:
                connection = http.client.HTTPSConnection(parsed.netloc, timeout=60)
                CONNECTIONS.connection = connection
            connection.request("GET", target)
            response = connection.getresponse()
            data = response.read()
            if response.status != 200:
                raise OSError(f"HTTP {response.status}: {url}")
            return data
        except (OSError, http.client.HTTPException):
            connection = getattr(CONNECTIONS, "connection", None)
            if connection:
                connection.close()
            CONNECTIONS.connection = None
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def list_objects():
    objects = []
    token = None
    while True:
        query = {"list-type": "2"}
        if token:
            query["continuation-token"] = token
        root = ET.fromstring(fetch(BASE_URL + "/?" + urlencode(query)))
        for item in root.findall("s3:Contents", NS):
            key = item.findtext("s3:Key", namespaces=NS)
            if key.endswith("/"):
                continue
            path = PurePosixPath(key)
            if path.is_absolute() or ".." in path.parts or "\\" in key or ":" in key:
                raise ValueError(f"Unsafe object key: {key!r}")
            objects.append({
                "key": key,
                "size": int(item.findtext("s3:Size", namespaces=NS)),
                "etag": item.findtext("s3:ETag", namespaces=NS).strip('"'),
            })
        print(f"Listed {len(objects):,} files", flush=True)
        if root.findtext("s3:IsTruncated", namespaces=NS) != "true":
            return objects
        token = root.findtext("s3:NextContinuationToken", namespaces=NS)
        if not token:
            raise RuntimeError("S3 listing is truncated without a continuation token")


def valid_file(path, item):
    if not path.is_file() or path.stat().st_size != item["size"]:
        return False
    # Single-part S3 ETags in this dataset are MD5 hashes.
    if not re.fullmatch(r"[0-9a-f]{32}", item["etag"]):
        raise ValueError(f"Cannot verify non-MD5 ETag: {item['key']}")
    return hashlib.md5(path.read_bytes()).hexdigest() == item["etag"]


def download_one(item, destination, verify_only):
    path = destination / item["key"]
    if valid_file(path, item):
        return "existing"
    if verify_only:
        raise RuntimeError(f"Missing or corrupt: {item['key']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(BASE_URL + "/" + quote(item["key"], safe="/"))
    if len(data) != item["size"] or hashlib.md5(data).hexdigest() != item["etag"]:
        raise RuntimeError(f"Checksum mismatch: {item['key']}")
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    return "downloaded"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--resume", action="store_true", help="Reuse the saved object listing after an interrupted download")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    args.destination.mkdir(parents=True, exist_ok=True)
    manifest_path = args.destination / "download_manifest.json"
    if args.verify_only or args.resume:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        objects = list_objects()
        manifest = {
            "source": BASE_URL,
            "registry": "https://registry.opendata.aws/bodym/",
            "listed_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": objects,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    objects = manifest["files"]
    total_size = sum(item["size"] for item in objects)
    print(f"Total: {len(objects):,} files, {total_size / 1024**2:.2f} MiB", flush=True)
    errors = []
    downloaded = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(download_one, item, args.destination, args.verify_only): item for item in objects}
        for completed, future in enumerate(as_completed(futures), 1):
            try:
                downloaded += future.result() == "downloaded"
            except Exception as error:
                errors.append(f"{futures[future]['key']}: {error}")
            if completed % 500 == 0 or completed == len(objects):
                print(f"Checked {completed:,}/{len(objects):,}; downloaded {downloaded:,}; errors {len(errors)}", flush=True)
    if errors:
        raise RuntimeError("\n".join(errors[:20]) + "\nRun again to retry failed files.")
    manifest["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["verified_files"] = len(objects)
    manifest["total_bytes"] = total_size
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Verified all files in {args.destination}", flush=True)


if __name__ == "__main__":
    main()
