"""Bounded local image/PDF preprocessing and PaddleOCR 3.x adapter."""
import hashlib
from pathlib import Path

from PIL import Image, ImageOps

MAX_PIXELS = 25_000_000
MAX_PAGES = 5


def preprocess_document(path, output_dir):
    """Keep full pages: EXIF transpose, grayscale and autocontrast only.

    Deskew/crop/denoise are intentionally not applied until benchmarked; blind
    cropping can remove result columns. Raw originals are never modified.
    """
    path, output_dir = Path(path), Path(output_dir)
    if path.stat().st_size > 30 * 1024 * 1024:
        raise ValueError("Document exceeds research limit of 30 MiB")
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = []

    def save_page(image, index):
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Page exceeds research pixel limit")
        processed = ImageOps.autocontrast(ImageOps.exif_transpose(image).convert("L"))
        target = output_dir / f"page_{index + 1:03d}.png"
        processed.save(target)
        pages.append(target)

    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(str(path)) as document:
            if not 1 <= len(document) <= MAX_PAGES:
                raise ValueError(f"Expected 1..{MAX_PAGES} PDF pages")
            for index in range(len(document)):
                page = document[index]
                try:
                    width, height = page.get_size()
                    if width * height * 4 > MAX_PIXELS:
                        raise ValueError("PDF page exceeds render pixel limit")
                    bitmap = page.render(scale=2)
                    try:
                        save_page(bitmap.to_pil(), index)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    else:
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Multi-frame images are unsupported; supply a PDF")
            save_page(image, 0)
    return {"source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "pages": pages,
            "preprocessing_version": "exif-gray-autocontrast-0.1.0"}


def group_rows(tokens):
    """Join spatially aligned label/value tokens, preserving raw token evidence.

    This initial heuristic is suitable for simple rows. Multi-column/segmental
    sheets may be rejected by the parser and need layout-aware extraction.
    """
    rows = []
    for token in sorted(tokens, key=lambda t: (t["page"], t["box"][1], t["box"][0])):
        x1, y1, x2, y2 = token["box"]
        center, height = (y1 + y2) / 2, y2 - y1
        row = next((r for r in rows if r["page"] == token["page"] and
                    abs(r["center"] - center) <= max(4, min(r["height"], height) * 0.5)), None)
        if row is None:
            row = {"page": token["page"], "center": center, "height": height, "tokens": []}
            rows.append(row)
        row["tokens"].append(token)
    return [{"text": " ".join(t["text"] for t in sorted(r["tokens"], key=lambda t: t["box"][0])),
             "confidence": min(t["confidence"] for t in r["tokens"]), "page": r["page"]}
            for r in sorted(rows, key=lambda r: (r["page"], r["center"]))]


class PaddleEngine:
    VERSION = "PaddleOCR/PP-OCRv6_medium"

    def __init__(self, *, device="cpu", detection_model="PP-OCRv6_medium_det", recognition_model="PP-OCRv6_medium_rec",
                 cpu_threads=4, use_doc_orientation_classify=False, use_doc_unwarping=False):
        import importlib.metadata
        from paddleocr import PaddleOCR
        self.VERSION = f"PaddleOCR-{importlib.metadata.version('paddleocr')}/{detection_model}/{recognition_model}/{device}"
        self.engine = PaddleOCR(device=device, text_detection_model_name=detection_model,
                                text_recognition_model_name=recognition_model,
                                use_doc_orientation_classify=use_doc_orientation_classify, use_doc_unwarping=use_doc_unwarping,
                                use_textline_orientation=False, enable_mkldnn=False,
                                cpu_threads=cpu_threads)

    def predict(self, pages):
        tokens, dimensions = [], []
        for page, path in enumerate(pages):
            with Image.open(path) as image:
                dimensions.append({"page": page, "width": image.width, "height": image.height})
            for result in self.engine.predict(str(path)):
                for text, score, poly in zip(result["rec_texts"], result["rec_scores"], result["rec_polys"]):
                    points = poly.tolist() if hasattr(poly, "tolist") else poly
                    tokens.append({"text": text, "confidence": float(score), "page": page,
                                   "box": [min(p[0] for p in points), min(p[1] for p in points),
                                           max(p[0] for p in points), max(p[1] for p in points)]})
        return {"tokens": tokens, "lines": group_rows(tokens), "pages": dimensions, "model_version": self.VERSION}
