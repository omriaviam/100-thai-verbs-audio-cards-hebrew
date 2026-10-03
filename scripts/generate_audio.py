#!/usr/bin/env python3
"""Generate local Thai MP3 files for vocabulary cards 101 and onward."""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.parse
import urllib.request
from pathlib import Path


def read_data(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    prefix = "window.VOCABULARY_DATA = "
    if not text.startswith(prefix) or not text.endswith(";"):
        raise ValueError("Unexpected vocabulary data wrapper")
    return json.loads(text[len(prefix) : -1])


async def generate_one(
    index: int,
    thai: str,
    destination: Path,
    semaphore: asyncio.Semaphore,
    overwrite: bool,
) -> None:
    if not overwrite and destination.exists() and destination.stat().st_size > 1000:
        return
    async with semaphore:
        for attempt in range(4):
            try:
                temporary = destination.with_suffix(".mp3.part")
                query = urllib.parse.urlencode(
                    {"ie": "UTF-8", "client": "tw-ob", "tl": "th", "q": thai}
                )
                request = urllib.request.Request(
                    f"https://translate.google.com/translate_tts?{query}",
                    headers={"User-Agent": "Mozilla/5.0"},
                )

                def download() -> None:
                    with urllib.request.urlopen(request, timeout=45) as response:
                        temporary.write_bytes(response.read())

                await asyncio.to_thread(download)
                if temporary.stat().st_size <= 1000:
                    raise ValueError(f"Generated audio is too small for card {index + 1}")
                temporary.replace(destination)
                return
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)


async def run(
    data_path: Path,
    audio_dir: Path,
    first_new_index: int,
    concurrency: int,
    overwrite: bool,
) -> None:
    payload = read_data(data_path)
    items = payload["items"]
    audio_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    pending = []
    for index, item in enumerate(items):
        if index < first_new_index:
            continue
        destination = audio_dir / f"word-{index + 1:03d}.mp3"
        pending.append((index, item["thai"], destination))

    completed = 0
    chunk_size = 50
    for start in range(0, len(pending), chunk_size):
        chunk = pending[start : start + chunk_size]
        await asyncio.gather(
            *(
                generate_one(index, thai, destination, semaphore, overwrite)
                for index, thai, destination in chunk
            )
        )
        completed += len(chunk)
        print(f"audio {completed}/{len(pending)}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("audio_dir", type=Path)
    parser.add_argument("--first-new-index", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run(
            args.data,
            args.audio_dir,
            args.first_new_index,
            args.concurrency,
            args.overwrite,
        )
    )


if __name__ == "__main__":
    main()
