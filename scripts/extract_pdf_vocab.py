#!/usr/bin/env python3
"""Extract short English/Thai/romanization entries from the Collins booklet.

The PDF uses three distinct fonts for the three parts of every entry.  Reading
the PDF's content-stream character order is important for Thai combining marks;
sorting glyphs only by their horizontal position corrupts some words.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pdfplumber


CATEGORIES = (
    (5, 18, "essentials", "יסודות"),
    (19, 32, "transport", "תחבורה"),
    (33, 46, "home", "בבית"),
    (47, 68, "shopping", "קניות"),
    (69, 84, "daily-life", "חיי יום-יום"),
    (85, 96, "leisure", "פנאי"),
    (97, 110, "sport", "ספורט"),
    (111, 126, "health", "בריאות"),
    (127, 140, "planet-earth", "כדור הארץ"),
    (141, 146, "celebrations", "חגים ופסטיבלים"),
)

COLUMNS = ((15.0, 103.0), (103.0, 192.0), (192.0, 286.0))
THAI_MARKS = set("\u0e31\u0e34\u0e35\u0e36\u0e37\u0e38\u0e39\u0e3a\u0e47\u0e48\u0e49\u0e4a\u0e4b\u0e4c\u0e4d\u0e4e")

SPECIAL_ENTRIES = {
    17: [
        ("1", "หนึ่ง", "nèung"), ("2", "สอง", "sǒrng"), ("3", "สาม", "sǎam"),
        ("4", "สี่", "sèe"), ("5", "ห้า", "hâa"), ("6", "หก", "hòk"),
        ("7", "เจ็ด", "jèt"), ("8", "แปด", "bpàirt"), ("9", "เก้า", "gâao"),
        ("10", "สิบ", "sìp"), ("11", "สิบเอ็ด", "sìp èt"),
        ("12", "สิบสอง", "sìp sǒrng"), ("13", "สิบสาม", "sìp sǎam"),
        ("14", "สิบสี่", "sìp sèe"), ("15", "สิบห้า", "sìp hâa"),
        ("16", "สิบหก", "sìp hòk"), ("17", "สิบเจ็ด", "sìp jèt"),
        ("18", "สิบแปด", "sìp bpàirt"), ("19", "สิบเก้า", "sìp gâao"),
        ("20", "ยี่สิบ", "yêe sìp"), ("30", "สามสิบ", "sǎam sìp"),
        ("40", "สี่สิบ", "sèe sìp"), ("50", "ห้าสิบ", "hâa sìp"),
        ("60", "หกสิบ", "hòk sìp"), ("70", "เจ็ดสิบ", "jèt sìp"),
        ("80", "แปดสิบ", "bpàirt sìp"), ("90", "เก้าสิบ", "gâao sìp"),
        ("100", "หนึ่งร้อย", "nèung róy"), ("1,000", "หนึ่งพัน", "nèung pan"),
        ("1,000,000", "หนึ่งล้าน", "nèung láan"),
    ],
    127: [
        ("parrot", "นกแก้ว", "nók gâew"), ("beak", "จะงอยปาก", "jà ngoy bpàak"),
        ("tail", "หาง", "hǎang"), ("claw", "กรงเล็บ", "grong lép"),
    ],
    141: [
        ("incense sticks and candle", "ธูปเทียน", "tôop tian"),
        ("banana leaf", "ใบตอง", "bai dtorng"),
        ("floating basket", "กระทง", "grà tong"),
    ],
}

# Page 14 lays out the first six weekdays/months in two visual subcolumns.
# Their glyph streams interleave, so the generic line parser joins each pair.
# Replace those five joined records with their intended individual entries.
SPLIT_ENTRIES = {
    "Monday Wednesday": [
        ("Monday", "วันจันทร์", "wan jan"),
        ("Wednesday", "วันพุธ", "wan pút"),
    ],
    "Thursday Tuesday": [
        ("Thursday", "วันพฤหัส", "wan pá réu hàt"),
        ("Tuesday", "วันอังคาร", "wan ang kaan"),
    ],
    "January April": [
        ("January", "มกราคม", "má gà raa kom"),
        ("April", "เมษายน", "may sǎa yon"),
    ],
    "February May": [
        ("February", "กุมภาพันธ์", "gum paa pan"),
        ("May", "พฤษภาคม", "préut sà paa kom"),
    ],
    "March June": [
        ("March", "มีนาคม", "mee naa kom"),
        ("June", "มิถุนายน", "mí tù naa yon"),
    ],
}


def category_for_page(page_number: int) -> tuple[str, str]:
    for start, end, key, label in CATEGORIES:
        if start <= page_number <= end:
            return key, label
    raise ValueError(f"Page {page_number} is outside the vocabulary ranges")


def classify_char(char: dict) -> str | None:
    font = char.get("fontname", "")
    size = round(float(char.get("size", 0)), 1)
    if "FrescoSans-Normal" in font and size == 7.5:
        return "english"
    if "NimbusSansThai-Light" in font and size == 10.0:
        return "thai"
    if "LucidaGrande" in font and size == 6.0:
        return "roman"
    return None


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_thai(text: str) -> str:
    text = unicodedata.normalize("NFC", re.sub(r"\s+", "", text))
    # The PDF represents sara am as a combined glyph followed by a visual aa.
    text = text.replace("ำา", "ำ")
    # Some exported glyph runs repeat the same combining mark or mark cluster.
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"([\u0e31\u0e34-\u0e3a\u0e47-\u0e4e])\1+", r"\1", text)
        text = re.sub(r"([\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]{2,4})\1", r"\1", text)
    return text


def normalized_thai_key(text: str) -> str:
    return re.sub(r"[^\u0e00-\u0e7f]", "", normalize_thai(text))


def line_text(chars: list[tuple[int, dict]], kind: str) -> str:
    # Preserve content-stream order. Thai combining marks often have an x value
    # that is slightly to the right of the following base consonant.
    value = "".join(char.get("text", "") for _, char in sorted(chars))
    return normalize_thai(value) if kind == "thai" else normalize_spaces(value)


def extract_lines(page) -> list[dict]:
    """Return font-classified line fragments without cutting long entries.

    A word near the right edge of a column can extend into the next column's
    nominal x range.  Segment first, then assign the entire fragment according
    to its starting x position.
    """
    segments: list[list[tuple[int, dict]]] = []
    current: list[tuple[int, dict]] = []
    current_kind = None
    current_top = None
    previous_x0 = None
    previous_x1 = None

    def flush_segment() -> None:
        nonlocal current
        if current:
            segments.append(current)
        current = []

    for index, char in enumerate(page.chars):
        top = float(char.get("top", 0))
        kind = classify_char(char)
        if not kind or not (8.0 <= top <= 405.0):
            flush_segment()
            current_kind = current_top = previous_x0 = previous_x1 = None
            continue
        x0 = float(char.get("x0", 0))
        x1 = float(char.get("x1", x0))
        continues = (
            current
            and kind == current_kind
            and abs(top - float(current_top)) <= 0.3
            and x0 >= float(previous_x0) - 1.0
            and x0 - float(previous_x1) <= 20.0
        )
        if not continues:
            flush_segment()
            current_kind = kind
            current_top = top
        current.append((index, char))
        previous_x0 = x0
        previous_x1 = x1
    flush_segment()

    lines = []
    for chars in segments:
        kind = classify_char(chars[0][1])
        if not kind:
            continue
        first_x = min(float(char.get("x0", 0)) for _, char in chars)
        lines.append(
            {
                "kind": kind,
                "top": round(float(chars[0][1].get("top", 0)), 1),
                "x": first_x,
                "text": line_text(chars, kind),
            }
        )
    return lines


def extract_column(page_lines: list[dict], x_start: float, x_end: float) -> list[dict]:
    lines = [line for line in page_lines if x_start <= line["x"] < x_end]
    lines.sort(key=lambda line: (line["top"], {"english": 0, "thai": 1, "roman": 2}[line["kind"]]))

    entries: list[dict] = []
    current = {"english": [], "thai": [], "roman": []}

    def flush() -> None:
        nonlocal current
        if current["english"] and current["thai"] and current["roman"]:
            entries.append(
                {
                    "english": normalize_spaces(" ".join(current["english"])),
                    "thai": normalize_thai("".join(current["thai"])),
                    "roman": normalize_spaces(" ".join(current["roman"])),
                }
            )
        current = {"english": [], "thai": [], "roman": []}

    state = None
    for line in lines:
        kind = line["kind"]
        text = line["text"]
        if not text:
            continue
        if kind == "english":
            if state in {"thai", "roman"}:
                flush()
            current["english"].append(text)
            state = "english"
        elif kind == "thai":
            if not current["english"]:
                continue
            if state == "roman":
                flush()
                continue
            current["thai"].append(text)
            state = "thai"
        elif kind == "roman":
            if not current["english"] or not current["thai"]:
                continue
            current["roman"].append(text)
            state = "roman"
    flush()
    return entries


def is_short_relevant(entry: dict) -> tuple[bool, str | None]:
    english = entry["english"]
    thai = entry["thai"]
    roman = entry["roman"]
    word_count = len(re.findall(r"[A-Za-z]+(?:[’'-][A-Za-z]+)?", english))
    if not re.search(r"[\u0e00-\u0e7f]", thai):
        return False, "missing-thai"
    if not re.search(r"[A-Za-z]", roman):
        return False, "missing-romanization"
    if word_count == 0 or word_count > 7 or len(english) > 58:
        return False, "long-or-non-vocabulary"
    if len(thai) > 65 or len(roman) > 90:
        return False, "long-translation"
    return True, None


def extract(pdf_path: Path, existing_html: Path | None = None) -> dict:
    accepted: list[dict] = []
    rejected: list[dict] = []
    source_seen: dict[str, dict] = {}
    rejection_counts: Counter[str] = Counter()

    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) != 146:
            raise ValueError(f"Expected 146 pages, found {len(pdf.pages)}")
        for page_number in range(5, 147):
            category, category_he = category_for_page(page_number)
            page_lines = extract_lines(pdf.pages[page_number - 1])
            for column_number, (x_start, x_end) in enumerate(COLUMNS, 1):
                for item in extract_column(page_lines, x_start, x_end):
                    item.update(
                        {
                            "category": category,
                            "categoryHe": category_he,
                            "sourcePage": page_number,
                            "sourceColumn": column_number,
                        }
                    )
                    ok, reason = is_short_relevant(item)
                    if not ok:
                        item["rejectionReason"] = reason
                        rejected.append(item)
                        rejection_counts[reason or "unknown"] += 1
                        continue
                    key = normalized_thai_key(item["thai"])
                    if key in source_seen:
                        item["rejectionReason"] = "duplicate-thai-in-pdf"
                        item["duplicateOf"] = source_seen[key]["thai"]
                        rejected.append(item)
                        rejection_counts["duplicate-thai-in-pdf"] += 1
                        continue
                    source_seen[key] = item
                    accepted.append(item)

    expanded: list[dict] = []
    for item in accepted:
        replacements = SPLIT_ENTRIES.get(item["english"])
        if not replacements:
            expanded.append(item)
            continue
        for english_text, thai, roman in replacements:
            replacement = dict(item)
            replacement.update(
                {"english": english_text, "thai": normalize_thai(thai), "roman": roman}
            )
            expanded.append(replacement)
    accepted = expanded
    source_seen = {normalized_thai_key(item["thai"]): item for item in accepted}

    for page_number, entries in SPECIAL_ENTRIES.items():
        category, category_he = category_for_page(page_number)
        for english_text, thai, roman in entries:
            item = {
                "english": english_text,
                "thai": normalize_thai(thai),
                "roman": roman,
                "category": category,
                "categoryHe": category_he,
                "sourcePage": page_number,
                "sourceColumn": 0,
            }
            key = normalized_thai_key(thai)
            if key in source_seen:
                continue
            source_seen[key] = item
            accepted.append(item)

    existing_duplicate_count = 0
    if existing_html:
        markup = existing_html.read_text(encoding="utf-8")
        existing_thai = {
            normalized_thai_key(html.unescape(value))
            for value in re.findall(r'<div class="thai">(.*?)</div>', markup, re.DOTALL)
        }
        data_prefix = "window.VOCABULARY_DATA = "
        if markup.strip().startswith(data_prefix):
            payload = json.loads(markup.strip()[len(data_prefix) :].removesuffix(";"))
            existing_thai.update(
                normalized_thai_key(item["thai"])
                for item in payload["items"]
                if item.get("source") == "original-site"
            )
        kept = []
        for item in accepted:
            if normalized_thai_key(item["thai"]) in existing_thai:
                item["rejectionReason"] = "duplicate-thai-in-existing-site"
                rejected.append(item)
                rejection_counts["duplicate-thai-in-existing-site"] += 1
                existing_duplicate_count += 1
            else:
                kept.append(item)
        accepted = kept

    for index, item in enumerate(accepted, 1):
        item["sourceId"] = f"collins-{index:04d}"

    return {
        "metadata": {
            "source": pdf_path.name,
            "pagesProcessed": 142,
            "accepted": len(accepted),
            "rejected": len(rejected),
            "existingDuplicatesRejected": existing_duplicate_count,
            "rejectionsByReason": dict(sorted(rejection_counts.items())),
            "categories": dict(Counter(item["category"] for item in accepted)),
        },
        "items": accepted,
        "rejected": rejected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--existing-html", type=Path)
    args = parser.parse_args()
    result = extract(args.pdf, args.existing_html)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metadata"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
