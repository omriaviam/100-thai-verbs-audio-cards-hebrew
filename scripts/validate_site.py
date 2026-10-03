#!/usr/bin/env python3
"""Validate vocabulary data, deduplication, audio coverage, and UI contracts."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_data() -> dict:
    text = (ROOT / "data" / "vocabulary.js").read_text(encoding="utf-8").strip()
    prefix = "window.VOCABULARY_DATA = "
    assert text.startswith(prefix) and text.endswith(";"), "Invalid vocabulary.js wrapper"
    return json.loads(text[len(prefix) : -1])


def thai_key(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("ำา", "ำ")
    return re.sub(r"[^\u0e00-\u0e7f]", "", value)


def validate_audio(item_count: int) -> None:
    audio_dir = ROOT / "audio"
    expected = {f"word-{index:03d}.mp3" for index in range(1, item_count + 1)}
    files = {path.name: path for path in audio_dir.glob("word-*.mp3")}
    assert set(files) == expected, (
        f"Audio mismatch: missing={sorted(expected - set(files))[:10]}, "
        f"extra={sorted(set(files) - expected)[:10]}"
    )
    for name, path in files.items():
        data = path.read_bytes()
        assert len(data) > 1000, f"Audio file is too small: {name}"
        assert data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0), (
            f"Invalid MP3 header: {name}"
        )


def validate_markup() -> None:
    markup = (ROOT / "index.html").read_text(encoding="utf-8")
    required = (
        '<script src="data/vocabulary.js"></script>',
        'id="grid"',
        'id="filters"',
        'id="search"',
        'function applyFilters()',
        'function revealMeaning(button)',
        'function playWord(index, button)',
        '.meaning{',
        'color:transparent!important',
        '.card.revealed .meaning{color:white!important}',
        '@media(max-width:620px)',
    )
    for value in required:
        assert value in markup, f"Missing UI contract: {value}"
    assert '<button class="card"' not in markup, "Cards should be rendered from data"


def main() -> None:
    payload = load_data()
    items = payload["items"]
    categories = payload["categories"]
    report = payload["report"]
    expected_items = report["originalItems"] + report["newItems"]
    assert len(items) == expected_items, f"Expected {expected_items} items, found {len(items)}"
    assert len(categories) == 15, f"Expected 15 categories, found {len(categories)}"
    assert len({category["key"] for category in categories}) == len(categories)

    category_keys = {category["key"] for category in categories}
    keys = []
    for index, item in enumerate(items, 1):
        for field in ("thai", "roman", "hebrew", "category", "categoryLabel", "source"):
            assert str(item.get(field, "")).strip(), f"Card {index} is missing {field}"
        assert item["category"] in category_keys, f"Unknown category on card {index}"
        assert re.search(r"[\u0e00-\u0e7f]", item["thai"]), f"No Thai text on card {index}"
        assert re.search(r"[A-Za-z]", item["roman"]), f"No romanization on card {index}"
        keys.append(thai_key(item["thai"]))
        if item["source"] == "collins":
            assert len(item.get("english", "")) <= 58
            assert 5 <= int(item.get("sourcePage", 0)) <= 146

    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    assert not duplicates, f"Duplicate Thai entries: {duplicates[:10]}"
    assert report["originalItems"] == 100
    assert report["newItems"] == 2677
    assert report["duplicatesRejected"] == 271
    assert report["translationAudit"]["categoryAwareOverrides"] >= 400
    assert report["translationAudit"]["newSplitEntriesTranslated"] == 10
    joined_extraction_errors = {
        "Monday Wednesday",
        "Thursday Tuesday",
        "January April",
        "February May",
        "March June",
    }
    assert not joined_extraction_errors.intersection(
        item.get("english", "") for item in items
    ), "Joined weekday/month extraction errors remain"

    validate_audio(len(items))
    validate_markup()

    counts = Counter(item["category"] for item in items)
    print(json.dumps({"items": len(items), "categories": counts, "report": payload["report"]}, ensure_ascii=False, indent=2))
    print("All static validations passed.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"VALIDATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
