#!/usr/bin/env python3
"""Transcribe long local audio with FunASR by chunking and offset-merging."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from transcribe_audio_funasr import collect_sentences, normalize_results, slugify, write_outputs


def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def audio_duration_seconds(audio_path: Path) -> float:
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


def make_chunk(source: Path, destination: Path, start_seconds: float, duration_seconds: float) -> None:
    if not shutil.which("ffmpeg"):
        fail("Missing required binary: ffmpeg")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start_seconds:.3f}",
            "-t",
            f"{duration_seconds:.3f}",
            "-i",
            str(source),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"ffmpeg failed for {destination.name}: {result.stderr.strip() or result.stdout.strip()}")
    if not destination.exists() or destination.stat().st_size == 0:
        fail(f"ffmpeg produced an empty chunk: {destination}")


def offset_sentence(sentence: dict[str, Any], offset_ms: int) -> dict[str, Any]:
    item = dict(sentence)
    for key in ("start", "end"):
        if item.get(key) is not None:
            item[key] = int(item[key]) + offset_ms
    return item


def main() -> None:
    total_started = time.perf_counter()
    parser = argparse.ArgumentParser(description="Transcribe long local audio with FunASR chunking.")
    parser.add_argument("audio_path")
    parser.add_argument("--out-dir", default="/tmp/miaoji-skill-funasr")
    parser.add_argument("--chunk-seconds", type=int, default=300)
    parser.add_argument("--model", default="paraformer-zh")
    parser.add_argument("--vad-model", default="fsmn-vad")
    parser.add_argument("--punc-model", default="ct-punc")
    parser.add_argument("--spk-model", default="cam++")
    parser.add_argument("--disable-speaker-diarization", action="store_true")
    parser.add_argument("--enable-update-check", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size-s", type=int, default=60)
    parser.add_argument("--keep-chunks", action="store_true")
    args = parser.parse_args()

    source = Path(args.audio_path).expanduser().resolve()
    if not source.exists():
        fail(f"Audio file does not exist: {source}")
    if not source.is_file():
        fail(f"Audio path is not a file: {source}")
    if args.chunk_seconds <= 0:
        fail("--chunk-seconds must be greater than zero.")

    out_dir = Path(args.out_dir).expanduser().resolve()
    chunks_dir = out_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    duration = audio_duration_seconds(source)

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

    sentences: list[dict[str, Any]] = []
    chunk_summaries: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    chunk_count = int((duration + args.chunk_seconds - 0.001) // args.chunk_seconds)
    for index in range(chunk_count):
        chunk_start = index * args.chunk_seconds
        chunk_duration = min(args.chunk_seconds, max(0.0, duration - chunk_start))
        if chunk_duration <= 0:
            continue
        chunk_path = chunks_dir / f"chunk_{index:04d}.wav"
        make_chunk(source, chunk_path, chunk_start, chunk_duration)

        generate_started = time.perf_counter()
        raw_result = model.generate(input=str(chunk_path), batch_size_s=args.batch_size_s)
        generate_seconds = time.perf_counter() - generate_started
        results = normalize_results(raw_result)
        chunk_sentences = collect_sentences(results)
        offset_ms = int(round(chunk_start * 1000))
        shifted = [offset_sentence(sentence, offset_ms) for sentence in chunk_sentences]
        sentences.extend(shifted)
        raw_results.append(
            {
                "chunk_index": index,
                "chunk_start_ms": offset_ms,
                "chunk_duration_ms": int(round(chunk_duration * 1000)),
                "raw_result": results,
            }
        )
        chunk_summaries.append(
            {
                "chunk_index": index,
                "chunk_start_ms": offset_ms,
                "chunk_duration_ms": int(round(chunk_duration * 1000)),
                "sentence_count": len(shifted),
                "speaker_count": len({sent.get("speaker") for sent in shifted if sent.get("speaker") is not None}),
                "generate_seconds": round(generate_seconds, 3),
            }
        )
        print(
            json.dumps(
                {
                    "chunk": index + 1,
                    "chunks": chunk_count,
                    "sentence_count": len(shifted),
                    "generate_seconds": round(generate_seconds, 3),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if not args.keep_chunks:
            chunk_path.unlink(missing_ok=True)

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
        "duration_seconds": duration,
        "chunk_seconds": args.chunk_seconds,
        "chunk_count": len(chunk_summaries),
        "chunk_summaries": chunk_summaries,
        "full_text": full_text,
        "sentences": sentences,
        "raw_result": raw_results,
        "timings": {
            "import_seconds": round(import_seconds, 3),
            "model_load_seconds": round(model_load_seconds, 3),
            "total_seconds": round(time.perf_counter() - total_started, 3),
        },
    }
    outputs = write_outputs(out_dir, payload)
    payload["outputs"] = outputs
    Path(outputs["json"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "status": status, "speaker_count": len(speakers), "sentences": len(sentences), "outputs": outputs}, ensure_ascii=False, indent=2))
    if status != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
