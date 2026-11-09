"""Field metrics with denominators; OCR metrics only with transcripts."""
import unicodedata
from difflib import SequenceMatcher

from .schema import FIELDS


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        new = [i]
        for j, right in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (left != right)))
        row = new
    return row[-1]


def normalize_transcript(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def evaluate(pairs):
    """pairs: reference values + prediction + optional ref/hyp transcript.

    Exact match means normalized numeric equality within 1e-6, with no rounding
    tolerance hidden in F1. Null/null never contributes a true positive.
    """
    if not pairs:
        raise ValueError("Cannot evaluate an empty benchmark")
    stats = {key: {"unit": spec["unit"], "labeled": 0, "predicted": 0, "paired": 0,
                   "exact": 0, "absolute_errors": []} for key, spec in FIELDS.items()}
    success, chars, char_errors, words, word_errors, transcripts = 0, 0, 0, 0, 0, 0
    errors, transcript_errors = [], []
    for pair in pairs:
        correct = True
        for key in FIELDS:
            ref, pred = pair["reference"].get(key), pair["prediction"].get(key)
            item = stats[key]
            item["labeled"] += ref is not None
            item["predicted"] += pred is not None
            if ref is not None and pred is not None:
                item["paired"] += 1
                item["absolute_errors"].append(abs(ref - pred))
            match = (ref is None and pred is None) or (ref is not None and pred is not None and abs(ref - pred) <= 1e-6)
            if ref is not None and match:
                item["exact"] += 1
            if not match:
                correct = False
                errors.append({"document_id": pair["document_id"], "field": key, "reference": ref, "prediction": pred})
        # A completely unlabelled document is not a successful extraction.
        success += correct and any(pair["reference"].get(key) is not None for key in FIELDS)
        if "reference_text" in pair and "prediction_text" in pair:
            ref, pred = normalize_transcript(pair["reference_text"]), normalize_transcript(pair["prediction_text"])
            transcripts += 1
            chars += len(ref)
            char_errors += edit_distance(ref, pred)
            words += len(ref.split())
            word_errors += edit_distance(ref.split(), pred.split())
            if ref != pred:
                differences = [{"reference": ref[i:j], "prediction": pred[k:l]}
                               for op, i, j, k, l in SequenceMatcher(None, ref, pred).get_opcodes() if op != "equal"]
                transcript_errors.append({"document_id": pair["document_id"],
                                          "char_edits": edit_distance(ref, pred), "differences": differences})
    for item in stats.values():
        errors_for_field = item.pop("absolute_errors")
        item["mae"] = sum(errors_for_field) / len(errors_for_field) if errors_for_field else None
        item["coverage"] = item["paired"] / item["labeled"] if item["labeled"] else None
        item["exact_match_rate"] = item["exact"] / item["labeled"] if item["labeled"] else None
    tp = sum(s["exact"] for s in stats.values())
    labeled, predicted = sum(s["labeled"] for s in stats.values()), sum(s["predicted"] for s in stats.values())
    return {"documents": len(pairs), "document_success_rate": success / len(pairs),
            "field_precision": tp / predicted if predicted else None,
            "field_recall": tp / labeled if labeled else None,
            "field_f1": 2 * tp / (labeled + predicted) if labeled + predicted else None,
            "per_field": stats, "transcript_documents": transcripts,
            "cer": char_errors / chars if chars else None, "wer": word_errors / words if words else None,
            "errors": errors, "transcript_errors": transcript_errors}
