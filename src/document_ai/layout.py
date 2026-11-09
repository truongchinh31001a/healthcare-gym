"""Conservative spatial field association. Unknown layouts never imply a result column."""
import math
import re
from copy import deepcopy

from .parser import fold, parse_lines, validate_values
from .schema import FIELDS

VERSION = "spatial-fields-0.1.0"
DATE_ALIASES = ("test date", "measurement date", "ngay do")
REFERENCE = re.compile(r"\b(?:reference|ref|range|normal|tham chieu|binh thuong)\b")
NUMBER = r"[+-]?\d+(?:[.,]\d+)?"


def _union(tokens):
    return [min(t["box"][0] for t in tokens), min(t["box"][1] for t in tokens),
            max(t["box"][2] for t in tokens), max(t["box"][3] for t in tokens)]


def _confidence(tokens):
    values = [token.get("confidence") for token in tokens]
    return min(values) if values and all(value is not None for value in values) else None


def _inside(box, roi):
    # Tokens crossing cell boundaries are ambiguous; never clip their text.
    return all((box[0] >= roi[0], box[1] >= roi[1], box[2] <= roi[2], box[3] <= roi[3]))


def _validate_tokens(tokens):
    if not isinstance(tokens, list) or len(tokens) > 5000:
        raise ValueError("Expected at most 5000 OCR tokens")
    result = []
    for index, token in enumerate(tokens):
        box, page, confidence = token.get("box"), token.get("page"), token.get("confidence")
        if (not isinstance(box, list) or len(box) != 4 or
                any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or x < 0 for x in box)
                or box[2] <= box[0] or box[3] <= box[1]):
            raise ValueError("Invalid OCR bounding box")
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ValueError("Invalid OCR page")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or
                                       not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("Invalid OCR confidence")
        if not isinstance(token.get("text"), str):
            raise ValueError("Invalid OCR text")
        if token["text"].strip():
            result.append({**deepcopy(token), "token_id": index})
    return result


def _rows(tokens, tolerance):
    rows = []
    for token in sorted(tokens, key=lambda t: (t["page"], (t["box"][1]+t["box"][3])/2, t["box"][0])):
        center = (token["box"][1]+token["box"][3])/2
        height = token["box"][3]-token["box"][1]
        row = next((r for r in rows if r["page"] == token["page"] and
                    abs(r["center"]-center) <= tolerance*min(height, r["height"])), None)
        if row is None:
            row = {"page": token["page"], "center": center, "height": height, "tokens": []}
            rows.append(row)
        row["tokens"].append(token)
    for row in rows:
        row["tokens"].sort(key=lambda t: t["box"][0])
    return rows


def _match(text):
    normalized = fold(text).strip()
    matches = []
    for field, aliases in [(key, spec["aliases"]) for key, spec in FIELDS.items()] + [("measured_at", DATE_ALIASES)]:
        for alias in aliases:
            match = re.match(r"^"+re.escape(fold(alias))+r"(?=$|[\s:(=])\s*[:=]?\s*(.*)$", normalized)
            if match:
                matches.append((len(alias), field, match[1]))
    return max(matches, default=None)


def _anchors(row, config):
    tokens, anchors, index = row["tokens"], [], 0
    while index < len(tokens):
        for end in range(index, min(index+8, len(tokens))):
            if end > index:
                previous, current = tokens[end-1]["box"], tokens[end]["box"]
                if current[0]-previous[2] > config["max_label_gap_heights"]*min(previous[3]-previous[1], current[3]-current[1]):
                    break
            match = _match(" ".join(t["text"] for t in tokens[index:end+1]))
            if match:
                span = tokens[index:end+1]
                anchors.append({"field": match[1], "tail": match[2], "start": index, "end": end,
                                "tokens": span, "box": _union(span), "page": row["page"]})
                index = end
                break
        index += 1
    return anchors


def _roi(template, field, role, pages):
    spec = template["fields"].get(field)
    if not spec:
        return None
    page = spec["page"]
    if page not in pages:
        raise ValueError("Template page is absent")
    values = spec[role]
    if (len(values) != 4 or any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) or not 0 <= x <= 1 for x in values)
            or not values[0] < values[2] or not values[1] < values[3]):
        raise ValueError("Template ROI must be a positive normalized rectangle")
    width, height = pages[page]
    return page, [values[0]*width, values[1]*height, values[2]*width, values[3]*height]


def _canonical_line(field, tail):
    label = "Test date" if field == "measured_at" else FIELDS[field]["aliases"][0]
    tail = tail.strip(" :=")
    # If a printed label supplies the unit, retain it explicitly. Never insert a
    # unit merely because the field registry expects one.
    unit_first = re.fullmatch(r"\(([^)]+)\)\s*:?\s*("+NUMBER+r")\s*(.*)", tail)
    if unit_first and unit_first[3].strip():
        first_unit, number, last_unit = unit_first.groups()
        if first_unit.strip().lower() == last_unit.strip().lower():
            tail = f"{number} {last_unit}"
    return f"{label}: {tail}"


def extract_fields(tokens, document_id, model_version, *, pages=(), config=None, template_id=None, confidence_threshold=.85):
    """Return schema-compatible pending extraction plus a spatial evidence sidecar.

    Generic mode splits at other recognized labels, large gaps and explicitly
    labelled reference columns. It does not pick the nearest of multiple numbers.
    Optional templates are explicit caller choices, never inferred from annotations.
    """
    config = config or {}
    geometry = {"row_tolerance": .5, "max_label_gap_heights": 2.0, "max_value_gap_heights": 10.0,
                **config.get("geometry", {})}
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 for value in geometry.values()):
        raise ValueError("Geometry thresholds must be positive and finite")
    tokens = _validate_tokens(tokens)
    dimensions = {}
    for page in pages:
        if page["page"] in dimensions or min(page["width"], page["height"]) <= 0:
            raise ValueError("Invalid or duplicate page dimensions")
        dimensions[page["page"]] = (page["width"], page["height"])
    if any(t["page"] not in dimensions or t["box"][2] > dimensions[t["page"]][0] or t["box"][3] > dimensions[t["page"]][1] for t in tokens) and pages:
        raise ValueError("OCR box outside its page")
    template = None
    if template_id is not None:
        template = config.get("templates", {}).get(template_id)
        if template is None or not dimensions:
            raise ValueError("Unknown template or missing page dimensions")
        for field in template["fields"]:
            if field not in {*FIELDS, "measured_at"}:
                raise ValueError("Unknown template field")
            for role in ("label_box", "value_box"):
                _roi(template, field, role, dimensions)
    entries = []
    for row in _rows(tokens, geometry["row_tolerance"]):
        anchors = _anchors(row, geometry)
        for position, anchor in enumerate(anchors):
            field, label_tokens = anchor["field"], anchor["tokens"]
            flags, excluded, selected = [], [], []
            if template:
                label_roi = _roi(template, field, "label_box", dimensions)
                if not label_roi or anchor["page"] != label_roi[0] or not _inside(anchor["box"], label_roi[1]):
                    continue
                value_page, value_roi = _roi(template, field, "value_box", dimensions)
                selected = [t for t in tokens if t["page"] == value_page and _inside(t["box"], value_roi)
                            and t["token_id"] not in {x["token_id"] for x in label_tokens}]
                selected.sort(key=lambda t: (t["box"][1], t["box"][0]))
                # An inline numeric tail outside the declared value cell cannot
                # be treated as an authorized value from that cell.
                if re.search(r"\d", re.sub(r"\([^)]*\)", "", anchor["tail"])):
                    flags.append("inline_value_outside_template_cell")
            else:
                boundary = anchors[position+1]["start"] if position+1 < len(anchors) else len(row["tokens"])
                previous = anchor["box"]
                for token in row["tokens"][anchor["end"]+1:boundary]:
                    box = token["box"]
                    if box[0]-previous[2] > geometry["max_value_gap_heights"]*min(box[3]-box[1], previous[3]-previous[1]):
                        excluded.append({"token_id": token["token_id"], "reason": "large_horizontal_gap"})
                        break
                    if REFERENCE.search(fold(token["text"])):
                        excluded.extend({"token_id": t["token_id"], "reason": "explicit_reference_column"}
                                        for t in row["tokens"][row["tokens"].index(token):boundary])
                        break
                    selected.append(token)
                    previous = box
            tail = " ".join([anchor["tail"], *(t["text"] for t in selected)]).strip()
            if field in FIELDS:
                units = "|".join(re.escape(unit) for unit in sorted(FIELDS[field]["units"], key=len, reverse=True))
                if len(re.findall(NUMBER+r"\s*(?:"+units+r")(?=$|\s)", tail.lower())) > 1:
                    flags.append("multiple_numeric_values")
            used = label_tokens + selected
            if not tail:
                flags.append("no_spatial_value")
            entries.append({"field": field, "page": anchor["page"], "label_box": anchor["box"],
                            "value_box": _union(selected) if selected else None,
                            "label_token_ids": [t["token_id"] for t in label_tokens],
                            "value_token_ids": [t["token_id"] for t in selected],
                            "raw_text": " ".join(t["text"] for t in used),
                            "canonical_text": _canonical_line(field, tail), "confidence": _confidence(used),
                            "flags": flags, "excluded": excluded})
    assignments = {}
    for entry in entries:
        for token_id in entry["value_token_ids"]:
            assignments.setdefault(token_id, []).append(entry)
    for users in assignments.values():
        if len(users) > 1:
            for entry in users:
                entry["flags"].append("shared_value_token")
    lines = [{"text": entry["canonical_text"], "confidence": entry["confidence"]} for entry in entries]
    result = parse_lines(lines, document_id, model_version, confidence_threshold)
    # Keep the existing extraction contract. Spatial parser identity and all
    # association evidence live in the linked, versioned layout sidecar.
    if not any(entry["field"] == "measured_at" for entry in entries):
        result["quality_flags"].append("measured_at:missing")
    for index, entry in enumerate(entries):
        field = entry["field"]
        if field == "measured_at":
            if entry["flags"]:
                result["measured_at"] = None
                result["quality_flags"].extend("measured_at:"+flag for flag in entry["flags"])
            continue
        evidence = result["field_evidence"][field]
        for candidate in evidence["candidates"]:
            if candidate["line_index"] == index:
                candidate["raw_text"] = entry["raw_text"]
        if entry["flags"]:
            evidence["flags"] = sorted(set(evidence["flags"]+entry["flags"]))
            result[field] = None
    result["quality_flags"] = sorted(set(result["quality_flags"] + validate_values(result) +
        [f"{key}:{flag}" for key, evidence in result["field_evidence"].items() for flag in evidence["flags"]]))
    return result, {"version": VERSION, "template_id": template_id, "geometry": geometry, "entries": entries,
                    "tokens": tokens, "pages": list(pages), "template_routing": "explicit caller selection" if template else "generic label anchors",
                    "limitations": ["Not a learned layout classifier or calibrated confidence", "Missing/ambiguous values require manual review",
                                    "Generic mode does not infer unlabeled reference versus result columns"]}
