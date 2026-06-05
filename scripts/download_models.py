#!/usr/bin/env python3
"""Download the ModelScope models required by 妙计.Skill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
MODEL_MANIFEST = SKILL_DIR / "config" / "models.json"


def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_manifest() -> dict[str, Any]:
    if not MODEL_MANIFEST.exists():
        fail(f"Model manifest does not exist: {MODEL_MANIFEST}")
    return json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))


def selected_models(manifest: dict[str, Any], include_speaker: bool) -> list[tuple[str, str]]:
    models = manifest.get("models")
    if not isinstance(models, dict):
        fail("Model manifest must contain a `models` object.")
    keys = ["asr", "vad", "punctuation"]
    if include_speaker:
        keys.append("speaker")
    selected: list[tuple[str, str]] = []
    for key in keys:
        item = models.get(key)
        if not isinstance(item, dict) or not item.get("model_id"):
            fail(f"Model manifest is missing `models.{key}.model_id`.")
        selected.append((key, str(item["model_id"])))
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Download required ModelScope models.")
    parser.add_argument(
        "--models-dir",
        default="",
        help="Optional local model directory. Defaults to ModelScope's standard cache.",
    )
    parser.add_argument(
        "--without-speaker",
        action="store_true",
        help="Skip the speaker model when speaker diarization will not be used.",
    )
    args = parser.parse_args()

    try:
        from modelscope.hub.snapshot_download import snapshot_download  # type: ignore
    except Exception:
        fail("Missing `modelscope`. Install dependencies first: python -m pip install modelscope")

    manifest = load_manifest()
    cache_dir = str(Path(args.models_dir).expanduser().resolve()) if args.models_dir else None
    downloaded: list[dict[str, str]] = []
    for role, model_id in selected_models(manifest, include_speaker=not args.without_speaker):
        path = snapshot_download(model_id, cache_dir=cache_dir)
        downloaded.append({"role": role, "model_id": model_id, "path": str(path)})

    print(json.dumps({"ok": True, "downloaded": downloaded}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
