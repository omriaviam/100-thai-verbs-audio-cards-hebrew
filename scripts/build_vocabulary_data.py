#!/usr/bin/env python3
"""Merge the original cards with the audited Collins vocabulary."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path


ORIGINAL_CATEGORIES = {
    "1": ("verbs-daily", "יומיום", "פעלים יומיומיים", "#278879"),
    "2": ("verbs-food", "אוכל", "אוכל ובישול", "#3d78ba"),
    "3": ("verbs-motion", "תנועה", "תנועה ונסיעות", "#cd392f"),
    "4": ("verbs-communication", "תקשורת", "דיבור ותקשורת", "#e99200"),
    "5": ("verbs-learning", "לימוד", "לימוד וחשיבה", "#824caf"),
}

NEW_CATEGORIES = {
    "essentials": ("יסודות", "יסודות", "#278879"),
    "transport": ("תחבורה", "תחבורה", "#cd392f"),
    "home": ("בבית", "בבית", "#3d78ba"),
    "shopping": ("קניות", "קניות", "#e99200"),
    "daily-life": ("יום-יום", "חיי יום-יום", "#2f7a55"),
    "leisure": ("פנאי", "פנאי", "#824caf"),
    "sport": ("ספורט", "ספורט", "#d34f73"),
    "health": ("בריאות", "בריאות", "#2f9fa3"),
    "planet-earth": ("טבע", "כדור הארץ", "#638c3a"),
    "celebrations": ("חגים", "חגים ופסטיבלים", "#b05a8d"),
}


def strip_hebrew_marks(value: str) -> str:
    value = re.sub(r"[\u0591-\u05bd\u05bf-\u05c7]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def original_items(source_text: str) -> list[dict]:
    pattern = re.compile(
        r'<button class="card" data-set="(?P<set>\d+)".*?'
        r'<div class="thai">(?P<thai>.*?)</div>\s*'
        r'<div class="roman">(?P<roman>.*?)</div>\s*'
        r'<div class="meaning">(?P<hebrew>.*?)</div>\s*'
        r'<div class="setname">(?P<setname>.*?)</div>',
        re.DOTALL,
    )
    items = []
    for match in pattern.finditer(source_text):
        category, _, category_label, _ = ORIGINAL_CATEGORIES[match.group("set")]
        items.append(
            {
                "thai": html.unescape(match.group("thai")).strip(),
                "roman": html.unescape(match.group("roman")).strip(),
                "hebrew": strip_hebrew_marks(html.unescape(match.group("hebrew"))),
                "category": category,
                "categoryLabel": category_label,
                "source": "original-site",
            }
        )

    prefix = "window.VOCABULARY_DATA = "
    if not items and source_text.strip().startswith(prefix):
        payload = json.loads(source_text.strip()[len(prefix) :].removesuffix(";"))
        items = [
            {
                "thai": item["thai"],
                "roman": item["roman"],
                "hebrew": strip_hebrew_marks(item["hebrew"]),
                "category": item["category"],
                "categoryLabel": item["categoryLabel"],
                "source": "original-site",
            }
            for item in payload["items"]
            if item.get("source") == "original-site"
        ]
    if len(items) != 100:
        raise ValueError(f"Expected 100 original cards, found {len(items)}")
    return items


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: build_vocabulary_data.py ORIGINAL_SOURCE AUDITED OUTPUT")
    original_source_path, audited_path, output_path = map(Path, sys.argv[1:4])
    originals = original_items(original_source_path.read_text(encoding="utf-8"))
    audited = json.loads(audited_path.read_text(encoding="utf-8"))

    items = list(originals)
    for source in audited["items"]:
        _, category_label, _ = NEW_CATEGORIES[source["category"]]
        items.append(
            {
                "thai": source["thai"],
                "roman": source["roman"],
                "hebrew": strip_hebrew_marks(source["hebrew"]),
                "english": source["english"],
                "category": source["category"],
                "categoryLabel": category_label,
                "source": "collins",
                "sourcePage": source["sourcePage"],
            }
        )

    categories = []
    for _, (key, short_label, label, accent) in ORIGINAL_CATEGORIES.items():
        categories.append(
            {"key": key, "shortLabel": short_label, "label": label, "accent": accent}
        )
    for key, (short_label, label, accent) in NEW_CATEGORIES.items():
        categories.append(
            {"key": key, "shortLabel": short_label, "label": label, "accent": accent}
        )

    payload = {
        "categories": categories,
        "items": items,
        "report": {
            "originalItems": len(originals),
            "newItems": len(audited["items"]),
            "duplicatesRejected": audited["metadata"]["rejected"],
            "duplicateBreakdown": audited["metadata"]["rejectionsByReason"],
            "translationAudit": audited["metadata"].get("translationAudit", {}),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.VOCABULARY_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
