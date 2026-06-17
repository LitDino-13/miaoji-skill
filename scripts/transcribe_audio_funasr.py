#!/usr/bin/env python3
"""Transcribe local audio with FunASR and optional speaker labels."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def slugify(value: str) -> str:
    value = Path(value).stem
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:120] or "audio"


def stamp_ms(value: Any) -> str:
    try:
        total_ms = int(float(value))
    except Exception:
        return "unknown"
    total_seconds = max(0, total_ms // 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def normalize_results(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def collect_sentences(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sentences: list[dict[str, Any]] = []
    for item in results:
        sentence_info = item.get("sentence_info")
        if isinstance(sentence_info, list):
            for sent in sentence_info:
                if isinstance(sent, dict):
                    text = sent.get("text") or sent.get("sentence") or ""
                    if text:
                        sentences.append(
                            {
                                "speaker": sent.get("spk"),
                                "start": sent.get("start"),
                                "end": sent.get("end"),
                                "text": text,
                            }
                        )
        elif item.get("text"):
            sentences.append(
                {
                    "speaker": None,
                    "start": None,
                    "end": None,
                    "text": item.get("text"),
                }
            )
    return sentences


def write_outputs(out_dir: Path, payload: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = slugify(payload["source_file"])
    json_path = out_dir / f"{base}.funasr.transcript.json"
    md_path = out_dir / f"{base}.funasr.transcript.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# {Path(payload['source_file']).stem}",
        "",
        f"- Source file: {payload['source_file']}",
        f"- Status: {payload['status']}",
        f"- ASR provider: {payload['asr_provider']}",
        f"- ASR model: {payload['asr_model']}",
        f"- Speaker model: {payload['spk_model']}",
        f"- Speaker count: {payload['speaker_count']}",
        f"- Created: {payload['created']}",
        "",
        "## Transcript",
        "",
    ]

    for sent in payload["sentences"]:
        speaker = sent.get("speaker")
        speaker_label = f"Speaker {speaker}" if speaker is not None else "Speaker 0"
        start = stamp_ms(sent.get("start"))
        end = stamp_ms(sent.get("end"))
        if start == "unknown" and end == "unknown":
            lines.append(f"- {speaker_label}: {sent['text']}")
        else:
            lines.append(f"- [{start}-{end}] {speaker_label}: {sent['text']}")

    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def main() -> None:
    total_started = time.perf_counter()
    parser = argparse.ArgumentParser(description="Transcribe local audio with FunASR speaker diarization.")
    parser.add_argument("audio_path")
    parser.add_argument("--out-dir", default="/tmp/miaoji-skill-funasr")
    parser.add_argument("--model", default="paraformer-zh")
    parser.add_argument("--vad-model", default="fsmn-vad")
    parser.add_argument("--punc-model", default="ct-punc")
    parser.add_argument("--spk-model", default="cam++")
    parser.add_argument("--disable-speaker-diarization", action="store_true")
    parser.add_argument("--enable-update-check", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size-s", type=int, default=300)
    args = parser.parse_args()

    source = Path(args.audio_path).expanduser().resolve()
    if not source.exists():
        fail(f"Audio file does not exist: {source}")
    if not source.is_file():
        fail(f"Audio path is not a file: {source}")

    try:
        import_started = time.perf_counter()
        from funasr import AutoModel  # type: ignore
        import_seconds = time.perf_counter() - import_started
    except Exception:
        fail("Missing FunASR. Run check_funasr_dependencies.py, then install required packages if approved.")

    model_kwargs: dict[str, Any] = {
        "model": args.model,
        "vad_model": args.vad_model,
        "punc_model": args.punc_model,
        "device": args.device,
        "disable_update": not args.enable_update_check,
    }
    if not args.disable_speaker_diarization:
        model_kwargs["spk_model"] = args.spk_model

    model_started = time.perf_counter()
    model = AutoModel(**model_kwargs)
    model_load_seconds = time.perf_counter() - model_started
    generate_started = time.perf_counter()
    raw_result = model.generate(input=str(source), batch_size_s=args.batch_size_s)
    generate_seconds = time.perf_counter() - generate_started
    results = normalize_results(raw_result)
    sentences = collect_sentences(results)
    full_text = "\n".join(str(sent.get("text") or "") for sent in sentences if sent.get("text")).strip()
    speakers = sorted({sent.get("speaker") for sent in sentences if sent.get("speaker") is not None}, key=str)
    status = "ready" if full_text else "partial"

    payload = {
        "ok": status == "ready",
        "status": status,
        "source_file": source.name,
        "source_path": str(source),
        "created": datetime.now().isoformat(timespec="seconds"),
        "asr_provider": "FunASR",
        "asr_model": args.model,
        "vad_model": args.vad_model,
        "punc_model": args.punc_model,
        "spk_model": None if args.disable_speaker_diarization else args.spk_model,
        "device": args.device,
        "speaker_diarization": not args.disable_speaker_diarization,
        "speaker_count": len(speakers),
        "speakers": speakers,
        "full_text": full_text,
        "sentences": sentences,
        "raw_result": results,
        "timings": {
            "import_seconds": round(import_seconds, 3),
            "model_load_seconds": round(model_load_seconds, 3),
            "generate_seconds": round(generate_seconds, 3),
            "total_seconds": round(time.perf_counter() - total_started, 3),
        },
    }
    outputs = write_outputs(Path(args.out_dir).expanduser().resolve(), payload)
    payload["outputs"] = outputs
    Path(outputs["json"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "status": status, "speaker_count": len(speakers), "outputs": outputs}, ensure_ascii=False, indent=2))
    if status != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
