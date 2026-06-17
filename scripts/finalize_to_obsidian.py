#!/usr/bin/env python3
"""Finalize ASR JSON into Obsidian transcript and summary notes."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", "~/ObsidianVault")).expanduser()
DEFAULT_SOURCE_FOLDER = Path(os.environ.get("MIAOJI_SOURCE_FOLDER", "40 Resources/源料库"))
DEFAULT_AUDIO_FOLDER = os.environ.get("MIAOJI_AUDIO_FOLDER")
FILLER_WORDS = {"嗯", "呃", "啊", "哎", "好", "对", "好的", "好的好的", "嗯嗯", "hello", "你好"}
TECH_REPLACEMENTS = [
    ("复 conu i", "ComfyUI"),
    ("制 comu i", "ComfyUI"),
    ("comu i", "ComfyUI"),
    ("comver UI", "ComfyUI"),
    ("康复 UI", "ComfyUI"),
    ("看复用来", "ComfyUI"),
    ("AI 生土", "AI 生图"),
    ("申土式", "生图式"),
    ("图声视频", "图生视频"),
    ("AI 纹身图", "AI 文生图"),
    ("workfloor", "workflow"),
    ("flom", "workflow"),
    ("program", "prompt"),
    ("problem", "prompt"),
    ("back coding", "vibe coding"),
    ("code x", "Codex"),
    ("GGMV", "GMV"),
    ("boook", "Bot"),
    ("boat", "Bot"),
    ("AI 的 Bot", "AI Bot"),
    ("ai 的 Bot", "AI Bot"),
    ("ai 助手", "AI 助手"),
    ("启微", "企微"),
    ("戚微", "企微"),
    ("低端的消费者", "终端消费者"),
    ("隐利", "盈利"),
    ("诚挚", "承制"),
    ("分批环", "分发/承制闭环"),
    ("变相逻辑", "变现逻辑"),
    ("绩效", "提效"),
    ("提项", "提效"),
    ("起效", "提效"),
    ("产品现态", "产品形态"),
    ("自节", "字节"),
    ("销售产品", "校招生产品"),
    ("校中生", "校招生"),
    ("打火", "打杂"),
    ("LO 可以", "ROI 可以"),
    ("PA 的方式", "RPA 的方式"),
    ("待操作", "代操作"),
    ("账样流", "账号限流"),
    ("美试官", "面试官"),
    ("下一页", "下一面"),
    ("千万 edit", "Qwen-Image-Edit"),
    ("千问 edit", "Qwen-Image-Edit"),
]


@dataclass
class Sentence:
    speaker: int | None
    start: int | None
    end: int | None
    text: str


@dataclass
class Turn:
    speaker: int | None
    start: int | None
    end: int | None
    texts: list[str]


def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def secret_patterns() -> list[str]:
    value = os.environ.get("AUDIO_TO_OBSIDIAN_SECRET_PATTERNS", "")
    return [item.strip() for item in value.split(",") if item.strip()]


def slugify(value: str) -> str:
    value = Path(value).stem
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:120] or "录音"


def title_prefix(created: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", created)
    if not match:
        fail(f"Invalid --created value: {created}. Expected YYYY-MM-DD.")
    return f"{match.group(1)}-{match.group(2)}{match.group(3)}"


def apply_title_prefix(title: str, created: str) -> str:
    title = slugify(title)
    if re.match(r"^\d{4}-\d{4}-", title):
        return title
    return f"{title_prefix(created)}-{title}"


def quote_yaml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def seconds_to_stamp(seconds: float) -> str:
    total = int(max(0, round(seconds)))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def ms_to_stamp(value: int | None) -> str:
    if value is None:
        return "00:00"
    return seconds_to_stamp(value / 1000)


def audio_duration(audio_path: Path) -> float:
    if not shutil.which("ffprobe"):
        fail("Missing required binary: ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"ffprobe failed: {result.stderr.strip() or result.stdout.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError:
        fail(f"Unable to parse audio duration: {result.stdout.strip()!r}")


def ensure_mp3(source_audio: Path, destination_dir: Path, title: str, overwrite: bool) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{slugify(title)}.mp3"
    if destination.exists() and not overwrite:
        return destination
    if not shutil.which("ffmpeg"):
        fail("Missing required binary: ffmpeg")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_audio),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"ffmpeg failed: {result.stderr.strip() or result.stdout.strip()}")
    if not destination.exists() or destination.stat().st_size == 0:
        fail(f"ffmpeg produced an empty audio file: {destination}")
    return destination


def clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^[，。！？、\s]+|[，。！？、\s]+$", "", text)
    for source, target in TECH_REPLACEMENTS:
        text = text.replace(source, target)
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" ，", "，").replace(" 。", "。").replace(" ？", "？").replace(" ！", "！")
    text = text.replace("AI 产 AI 搜索", "AI 搜索")
    return text.strip()


def load_sentences(transcript_json: Path) -> tuple[dict[str, Any], list[Sentence]]:
    payload = json.loads(transcript_json.read_text(encoding="utf-8"))
    sentences: list[Sentence] = []
    if isinstance(payload.get("sentences"), list):
        for item in payload["sentences"]:
            if not isinstance(item, dict):
                continue
            text = clean_text(str(item.get("text") or ""))
            if not text or text.strip("，。！？、 ") in FILLER_WORDS:
                continue
            speaker = item.get("speaker")
            sentences.append(
                Sentence(
                    speaker=int(speaker) if speaker is not None else None,
                    start=int(item["start"]) if item.get("start") is not None else None,
                    end=int(item["end"]) if item.get("end") is not None else None,
                    text=text,
                )
            )
    elif isinstance(payload.get("chunks"), list):
        for chunk in payload["chunks"]:
            if not isinstance(chunk, dict) or not chunk.get("text"):
                continue
            start = int(float(chunk.get("start") or 0) * 1000)
            end = int(float(chunk.get("end") or 0) * 1000)
            sentences.append(Sentence(speaker=None, start=start, end=end, text=clean_text(str(chunk["text"]))))
    else:
        fail("Transcript JSON must contain either `sentences` or `chunks`.")
    if not sentences:
        fail("Transcript JSON contains no usable transcript text.")
    return payload, sentences


def merge_turns(sentences: list[Sentence], max_chars: int, max_gap_ms: int) -> list[Turn]:
    turns: list[Turn] = []
    current: Turn | None = None
    for sentence in sentences:
        if current is None:
            current = Turn(sentence.speaker, sentence.start, sentence.end, [sentence.text])
            continue
        text_len = sum(len(item) for item in current.texts)
        gap = 0 if current.end is None or sentence.start is None else sentence.start - current.end
        if sentence.speaker == current.speaker and gap <= max_gap_ms and text_len < max_chars:
            current.texts.append(sentence.text)
            current.end = sentence.end
        else:
            turns.append(current)
            current = Turn(sentence.speaker, sentence.start, sentence.end, [sentence.text])
    if current is not None:
        turns.append(current)
    return turns


def join_text(parts: list[str]) -> str:
    output = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not output:
            output = part
        elif re.match(r"^[A-Za-z0-9]", part) and re.search(r"[A-Za-z0-9]$", output):
            output += " " + part
        else:
            output += part
    output = re.sub(r"(，){2,}", "，", output)
    output = re.sub(r"(。){2,}", "。", output)
    output = re.sub(r"，([。！？])", r"\1", output)
    output = re.sub(r"([。！？])([。！？])+", r"\1", output)
    if output and output[-1] not in "。！？：；”）』》":
        output += "。"
    return output


def speaker_ids(sentences: list[Sentence]) -> list[int]:
    return sorted({sentence.speaker for sentence in sentences if sentence.speaker is not None})


def parse_speaker_roles(values: list[str]) -> dict[int, str]:
    roles: dict[int, str] = {}
    for value in values:
        if "=" not in value:
            fail(f"Invalid --speaker-role value: {value}. Expected format: 0=候选人")
        speaker, role = value.split("=", 1)
        try:
            roles[int(speaker.strip())] = role.strip()
        except ValueError:
            fail(f"Invalid speaker id in --speaker-role: {value}")
    return roles


def participants_yaml(ids: list[int]) -> str:
    if not ids:
        return "  - Speaker 0"
    return "\n".join(f"  - Speaker {speaker_id}" for speaker_id in ids)


def tags_yaml(tags: list[str]) -> str:
    unique_tags = []
    for tag in tags:
        normalized = tag.strip()
        if normalized and normalized not in unique_tags:
            unique_tags.append(normalized)
    return "\n".join(f"  - {tag}" for tag in unique_tags)


def speaker_note(ids: list[int], roles: dict[int, str]) -> str:
    if not ids:
        return "- Speaker 0：ASR 未返回说话人区分；此处为插件兼容的未知单一说话人占位。"
    lines = []
    for speaker_id in ids:
        role = roles.get(speaker_id)
        if role:
            lines.append(f"- Speaker {speaker_id}：{role}。")
        else:
            lines.append(f"- Speaker {speaker_id}：未确认身份。")
    lines.append("")
    lines.append("以上身份仅基于本次整理时提供或推断的信息，后续如需正式归档，可以按实际姓名替换。")
    return "\n".join(lines)


def turn_blocks(turns: list[Turn]) -> str:
    blocks = []
    for turn in turns:
        speaker = f"Speaker {turn.speaker}" if turn.speaker is not None else "Speaker 0"
        blocks.append(f"{speaker} {ms_to_stamp(turn.start)}\n\n{join_text(turn.texts)}")
    return "\n\n".join(blocks)


def extract_keywords(text: str) -> list[str]:
    keyword_map = [
        ("AI", "AI"),
        ("产品", "产品"),
        ("面试", "面试"),
        ("商家", "商家"),
        ("GMV", "GMV"),
        ("短剧", "AI短剧"),
        ("ComfyUI", "ComfyUI"),
        ("workflow", "workflow"),
        ("Agent", "Agent"),
        ("知识库", "知识库"),
        ("企微", "企微"),
    ]
    result = []
    for needle, label in keyword_map:
        if needle in text and label not in result:
            result.append(label)
    return result[:8]


def representative_lines(turns: list[Turn], max_items: int) -> list[tuple[str, str]]:
    selected = []
    for turn in turns:
        text = join_text(turn.texts)
        if len(text) < 35:
            continue
        selected.append((ms_to_stamp(turn.start), text))
        if len(selected) >= max_items:
            break
    return selected


def build_chapters(turns: list[Turn], duration_seconds: float) -> str:
    if not turns:
        return "- 未生成章节。"
    chapter_count = min(8, max(3, int(duration_seconds // 420) + 1))
    stride = max(1, len(turns) // chapter_count)
    chapters = []
    used_stamps = set()
    for turn in turns[::stride]:
        stamp = ms_to_stamp(turn.start)
        if stamp in used_stamps:
            continue
        used_stamps.add(stamp)
        text = join_text(turn.texts)
        title = infer_chapter_title(text)
        chapters.append(f"### {stamp}  {title}\n\n{text[:180]}")
        if len(chapters) >= chapter_count:
            break
    return "\n\n".join(chapters)


def infer_chapter_title(text: str) -> str:
    rules = [
        ("自我介绍", "开场与自我介绍"),
        ("项目", "项目经历展开"),
        ("商业", "商业逻辑讨论"),
        ("GMV", "商家增长与 GMV 拆解"),
        ("AI 小二", "AI 小二与产品形态"),
        ("企微", "企微触达与风控讨论"),
        ("通过", "面试反馈与后续建议"),
        ("问题", "问题追问与回答"),
    ]
    for needle, title in rules:
        if needle in text:
            return title
    return "对话重点"


def build_summary(title: str, turns: list[Turn], duration_seconds: float, transcript_note_title: str, audio_rel: str) -> dict[str, str]:
    full_text = "\n".join(join_text(turn.texts) for turn in turns)
    keywords = extract_keywords(full_text)
    lines = representative_lines(turns, 3)
    focus = "、".join(keywords) if keywords else "录音中的核心议题"
    detail = "\n\n".join(f"- {stamp}：{text[:160]}" for stamp, text in lines) or "- 本次录音已完成转写，建议结合逐字稿复核重点。"
    return {
        "overall": f"本次录音主题为「{title}」，主要围绕{focus}展开。\n\n可优先复盘以下片段：\n\n{detail}",
        "near_term": "- 复核逐字稿中专有名词、英文术语和关键承诺。\n- 根据智能章节回听重点片段，补充人工确认后的结论。",
        "long_term": "- 将本次录音中可复用的方法、问题和表达沉淀为后续复盘材料。\n- 如果这是面试或会议录音，持续积累高频问题、回答框架和改进清单。",
        "actions": "- [ ] 未明确：回听并确认关键专有名词；截止时间：未明确。\n- [ ] 未明确：根据逐字稿补充人工确认后的复盘结论；截止时间：未明确。",
        "chapters": build_chapters(turns, duration_seconds),
        "decisions": "- 决策：未从转写中稳定抽取到需要自动确认的正式决策。\n- 依据：请结合逐字稿人工复核后补充。",
        "quotes": "- 暂未自动提取高置信金句；建议人工复核后补充。",
        "risks": "- 智能摘要由规则脚本基于转写文本生成，不能替代人工判断。\n- ASR 对专有名词、英文表达、多人重叠发言可能存在识别错误。\n- 需要结合原录音和逐字稿确认关键事实。",
        "links": f"- 逐字稿：[[{transcript_note_title}]]\n- 录音文件：[[{audio_rel}|{Path(audio_rel).name}]]",
    }


def copy_transcript_json(transcript_json: Path, assets_dir: Path, overwrite: bool) -> Path:
    destination = assets_dir / "transcript.json"
    if destination.exists() and not overwrite:
        return destination
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(transcript_json, destination)
    return destination


def package_dir_for(vault: Path, source_folder: Path, title: str) -> Path:
    return vault / source_folder / title


def audio_link_for_note(audio_path: Path, note_dir: Path) -> str:
    return audio_path.name if audio_path.parent == note_dir else str(audio_path)


def write_notes(
    note_dir: Path,
    title: str,
    audio_rel: str,
    transcript_json_rel: str,
    duration: str,
    created: str,
    speaker_ids_value: list[int],
    roles: dict[int, str],
    turns: list[Turn],
    tags: list[str],
    category: str,
    recorded_time: str,
    overwrite: bool,
) -> tuple[Path, Path]:
    note_dir.mkdir(parents=True, exist_ok=True)
    transcript_note_title = f"{title}—逐字稿"
    raw_note_title = f"{title}—Raw"
    summary_note_title = f"{title}—Summary"
    raw_path = note_dir / f"{raw_note_title}.md"
    transcript_path = note_dir / f"{transcript_note_title}.md"
    summary_path = note_dir / f"{summary_note_title}.md"
    if not overwrite and (raw_path.exists() or transcript_path.exists() or summary_path.exists()):
        fail(f"Output note already exists. Use --overwrite to replace: {raw_path} / {transcript_path} / {summary_path}")

    participant_block = participants_yaml(speaker_ids_value)
    tag_block = tags_yaml(tags)
    audio_link = f"[[{audio_rel}|{Path(audio_rel).name}]]"
    embedded_audio = f"![[{audio_link_for_note(Path(audio_rel), note_dir)}]]"
    transcript_text = turn_blocks(turns)
    cleanup_note = (
        "- 本文由 ASR 转写结果整理而成，已合并连续同一说话人的短句碎片。\n"
        "- 已对明显 ASR 错字、重复语气词和常见英文技术词做轻度清理。\n"
        "- 少量模型名、专有名词和口误处仍建议结合原录音核对；本文适合作为复盘材料，不作为法律级逐字记录。\n"
        "- 逐字稿中的 `Speaker N MM:SS` 行用于 Obsidian 时间戳跳转插件识别。"
    )
    summary = build_summary(title, turns, stamp_to_seconds(duration), transcript_note_title, audio_rel)
    raw_md = f"""---
type: audio-raw
title: {quote_yaml(raw_note_title)}
source_type: audio
audio: {quote_yaml(audio_rel)}
transcript_json: {quote_yaml(transcript_json_rel)}
duration: {quote_yaml(duration)}
created: {quote_yaml(created)}
review_status: "原始资料"
tags:
{tags_yaml(["录音原始资料", *tags])}
---

# {raw_note_title}

## 原始资料

- 音频文件：{audio_link}
- ASR 结构化结果：[[{transcript_json_rel}|transcript.json]]
- 音频时长：{duration}
- 创建日期：{created}

## 说明

此文件是录音资料包的原始资料索引。原始音频保存于 `assets/`，逐字稿与智能摘要分别保存在同一资料包目录下。
"""
    transcript_md = f"""---
type: interview-transcript
title: {quote_yaml(transcript_note_title)}
category: {quote_yaml(category)}
source_type: audio
audio: {quote_yaml(audio_rel)}
raw_note: "[[{raw_note_title}]]"
duration: {quote_yaml(duration)}
created: {quote_yaml(created)}
review_status: "已整理"
participants:
{participant_block}
tags:
{tag_block}
---

# {transcript_note_title}

> 会议主题：{title}  
> 音频文件：{audio_link}  
> 音频时长：{duration}

{embedded_audio}

## 智能纪要

{summary["overall"]}

## 说话人说明

{speaker_note(speaker_ids_value, roles)}

## 整理说明

{cleanup_note}

## 文字记录

{transcript_text}
"""
    summary_md = f"""---
type: audio-summary
title: {quote_yaml(summary_note_title)}
source_type: audio
transcript: "[[{transcript_note_title}]]"
raw_note: "[[{raw_note_title}]]"
audio: {quote_yaml(audio_rel)}
duration: {quote_yaml(duration)}
created: {quote_yaml(created)}
review_status: "已整理"
participants:
{participant_block}
tags:
{tags_yaml(["智能纪要", *tags])}
---

# 智能纪要：{title}

> 录音主题：{title}  
> 录音时间：{recorded_time}  
> 逐字稿：[[{transcript_note_title}]]  
> 音频文件：{audio_link}
>
> 智能纪要由规则脚本基于转写文本整理，可能不准确，请结合原录音与逐字稿甄别后使用。

## 总结

{summary["overall"]}

## 后续计划

### 近期事项

{summary["near_term"]}

### 长期规划

{summary["long_term"]}

## 待办

{summary["actions"]}

## 智能章节

{summary["chapters"]}

## 关键决策

{summary["decisions"]}

## 金句时刻

{summary["quotes"]}

## 风险与待确认

{summary["risks"]}

## 相关链接

{summary["links"]}
"""
    for secret in secret_patterns():
        if secret and (secret in raw_md or secret in transcript_md or secret in summary_md):
            fail("Generated note contains a known secret pattern; refusing to write.")
    raw_path.write_text(raw_md, encoding="utf-8")
    transcript_path.write_text(transcript_md, encoding="utf-8")
    summary_path.write_text(summary_md, encoding="utf-8")
    return raw_path, transcript_path, summary_path


def stamp_to_seconds(stamp: str) -> float:
    parts = [int(part) for part in stamp.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize ASR JSON into Obsidian transcript and summary notes.")
    parser.add_argument("transcript_json")
    parser.add_argument("--source-audio", required=True)
    parser.add_argument("--title")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--source-folder", default=str(DEFAULT_SOURCE_FOLDER))
    parser.add_argument("--note-folder", help="Deprecated alias for --source-folder.")
    parser.add_argument("--audio-folder", default=DEFAULT_AUDIO_FOLDER)
    parser.add_argument("--category", default="面试")
    parser.add_argument("--tag", action="append", default=["录音转写"])
    parser.add_argument("--speaker-role", action="append", default=[])
    parser.add_argument("--recorded-time", default="未明确")
    parser.add_argument("--created", default=date.today().isoformat())
    parser.add_argument("--max-turn-chars", type=int, default=520)
    parser.add_argument("--max-gap-ms", type=int, default=15000)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    transcript_json = Path(args.transcript_json).expanduser().resolve()
    source_audio = Path(args.source_audio).expanduser().resolve()
    vault = Path(args.vault).expanduser().resolve()
    source_folder = Path(args.note_folder or args.source_folder)
    if not transcript_json.exists():
        fail(f"Transcript JSON does not exist: {transcript_json}")
    if not source_audio.exists():
        fail(f"Source audio does not exist: {source_audio}")
    if not vault.exists():
        fail(f"Vault does not exist: {vault}")

    payload, sentences = load_sentences(transcript_json)
    title = apply_title_prefix(str(args.title or payload.get("source_file") or source_audio.stem), args.created)
    note_dir = package_dir_for(vault, source_folder, title)
    assets_dir = note_dir / "assets"
    audio_dir = vault / Path(args.audio_folder) if args.audio_folder else assets_dir
    audio_path = ensure_mp3(source_audio, audio_dir, title, overwrite=args.overwrite)
    audio_rel = str(audio_path.relative_to(vault))
    transcript_json_path = copy_transcript_json(transcript_json, assets_dir, overwrite=args.overwrite)
    transcript_json_rel = str(transcript_json_path.relative_to(vault))
    duration = seconds_to_stamp(audio_duration(audio_path))
    turns = merge_turns(sentences, max_chars=args.max_turn_chars, max_gap_ms=args.max_gap_ms)
    ids = speaker_ids(sentences)
    roles = parse_speaker_roles(args.speaker_role)
    raw_path, transcript_path, summary_path = write_notes(
        note_dir=note_dir,
        title=title,
        audio_rel=audio_rel,
        transcript_json_rel=transcript_json_rel,
        duration=duration,
        created=args.created,
        speaker_ids_value=ids,
        roles=roles,
        turns=turns,
        tags=args.tag,
        category=args.category,
        recorded_time=args.recorded_time,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "title": title,
                "audio": str(audio_path),
                "raw_note": str(raw_path),
                "transcript_note": str(transcript_path),
                "summary_note": str(summary_path),
                "speaker_count": len(ids),
                "turn_count": len(turns),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
