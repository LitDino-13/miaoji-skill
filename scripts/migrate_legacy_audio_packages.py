#!/usr/bin/env python3
"""Migrate legacy flat audio notes into source-package folders."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path


DEFAULT_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", "~/ObsidianVault")).expanduser()
DEFAULT_LEGACY_NOTE_FOLDER = Path("40 Resources/录音转写")
DEFAULT_LEGACY_AUDIO_FOLDER = Path("40 Resources/附件/录音原件")
DEFAULT_SOURCE_FOLDER = Path(os.environ.get("MIAOJI_SOURCE_FOLDER", "40 Resources/源料库"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy Miaoji audio notes into source packages.")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--legacy-note-folder", default=str(DEFAULT_LEGACY_NOTE_FOLDER))
    parser.add_argument("--legacy-audio-folder", default=str(DEFAULT_LEGACY_AUDIO_FOLDER))
    parser.add_argument("--source-folder", default=str(DEFAULT_SOURCE_FOLDER))
    parser.add_argument("--execute", action="store_true", help="Actually move files. Default is dry run.")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def quote_yaml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def title_from_transcript(path: Path) -> str:
    return path.name.removesuffix("—逐字稿.md")


def find_pairs(note_dir: Path, audio_dir: Path) -> list[dict[str, Path | str | None]]:
    pairs = []
    for transcript in sorted(note_dir.glob("*—逐字稿.md")):
        title = title_from_transcript(transcript)
        summary = note_dir / f"{title} - 智能摘要.md"
        if not summary.exists():
            summary = note_dir / f"{title}—Summary.md"
        audio = audio_dir / f"{title}.mp3"
        pairs.append(
            {
                "title": title,
                "transcript": transcript,
                "summary": summary if summary.exists() else None,
                "audio": audio if audio.exists() else None,
            }
        )
    return pairs


def rewrite_note_text(text: str, title: str, old_audio_rel: str, new_audio_rel: str) -> str:
    raw_title = f"{title}—Raw"
    summary_old = f"{title} - 智能摘要"
    summary_new = f"{title}—Summary"
    text = text.replace(old_audio_rel, new_audio_rel)
    text = text.replace(f"[[{summary_old}]]", f"[[{summary_new}]]")
    text = text.replace(f"[[{summary_old}]", f"[[{summary_new}]")
    text = text.replace(f"title: {summary_old}", f"title: {summary_new}")
    text = text.replace(f"title: {quote_yaml(summary_old)}", f"title: {quote_yaml(summary_new)}")
    if "type: audio-summary" in text:
        text = re.sub(
            rf"^title:\s*\"?{re.escape(title)}\"?\s*$",
            f"title: {summary_new}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    text = text.replace(f"# 智能纪要：{title}", f"# 智能纪要：{title}")
    text = text.replace(f"transcript: \"[[{title}—逐字稿]]\"", f"transcript: \"[[{title}—逐字稿]]\"\nraw_note: \"[[{raw_title}]]\"")
    if "raw_note:" not in text and "source_type: audio\n" in text:
        text = text.replace("source_type: audio\n", f"source_type: audio\nraw_note: \"[[{raw_title}]]\"\n", 1)
    return text


def raw_note(title: str, new_audio_rel: str, created: str) -> str:
    raw_title = f"{title}—Raw"
    return f"""---
type: audio-raw
title: {quote_yaml(raw_title)}
source_type: audio
audio: {quote_yaml(new_audio_rel)}
created: {quote_yaml(created)}
review_status: "原始资料"
tags:
  - 录音原始资料
---

# {raw_title}

## 原始资料

- 音频文件：[[{new_audio_rel}|{Path(new_audio_rel).name}]]
- 逐字稿：[[{title}—逐字稿]]
- 智能摘要：[[{title}—Summary]]

## 说明

此文件由旧版扁平目录迁移生成，用作录音资料包的原始资料索引。原始音频保存于 `assets/`，逐字稿与智能摘要保存在同一资料包目录下。
"""


def extract_created(text: str) -> str:
    match = re.search(r"^created:\s*\"?([^\"\n]+)\"?\s*$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return date.today().isoformat()


def move_file(source: Path, destination: Path, overwrite: bool, execute: bool) -> None:
    if destination.exists():
        if not overwrite:
            raise SystemExit(f"Destination exists: {destination}")
        if execute:
            destination.unlink()
    if execute:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))


def write_file(path: Path, content: str, overwrite: bool, execute: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"Destination exists: {path}")
    if execute:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    vault = Path(args.vault).expanduser().resolve()
    note_dir = vault / Path(args.legacy_note_folder)
    audio_dir = vault / Path(args.legacy_audio_folder)
    source_dir = vault / Path(args.source_folder)
    if not note_dir.is_dir():
        raise SystemExit(f"Legacy note folder not found: {note_dir}")

    migrated = []
    for pair in find_pairs(note_dir, audio_dir):
        title = str(pair["title"])
        transcript = pair["transcript"]
        summary = pair["summary"]
        audio = pair["audio"]
        assert isinstance(transcript, Path)
        package_dir = source_dir / title
        assets_dir = package_dir / "assets"
        old_audio_rel = str(Path(args.legacy_audio_folder) / f"{title}.mp3")
        new_audio_rel = str(Path(args.source_folder) / title / "assets" / f"{title}.mp3")

        transcript_text = rewrite_note_text(transcript.read_text(encoding="utf-8"), title, old_audio_rel, new_audio_rel)
        created = extract_created(transcript_text)
        summary_text = None
        if isinstance(summary, Path):
            summary_text = rewrite_note_text(summary.read_text(encoding="utf-8"), title, old_audio_rel, new_audio_rel)

        write_file(package_dir / f"{title}—Raw.md", raw_note(title, new_audio_rel, created), args.overwrite, args.execute)
        write_file(package_dir / f"{title}—逐字稿.md", transcript_text, args.overwrite, args.execute)
        if summary_text is not None:
            write_file(package_dir / f"{title}—Summary.md", summary_text, args.overwrite, args.execute)
        if isinstance(audio, Path):
            move_file(audio, assets_dir / f"{title}.mp3", args.overwrite, args.execute)
        if args.execute:
            transcript.unlink()
            if isinstance(summary, Path):
                summary.unlink()
        migrated.append(str(package_dir))

    print(json.dumps({"execute": args.execute, "migrated": migrated}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
