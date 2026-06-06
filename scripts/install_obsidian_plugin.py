#!/usr/bin/env python3
"""Install the bundled Obsidian timestamp plugin into a vault."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PLUGIN_ID = "audio-transcript-jumper"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install the bundled Obsidian plugin for audio timestamp playback."
    )
    parser.add_argument(
        "--vault",
        required=True,
        help="Absolute path to the target Obsidian vault.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing installed plugin directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skill_dir = Path(__file__).resolve().parents[1]
    source_dir = skill_dir / "obsidian-plugin" / PLUGIN_ID
    vault_dir = Path(args.vault).expanduser().resolve()
    target_dir = vault_dir / ".obsidian" / "plugins" / PLUGIN_ID

    if not source_dir.is_dir():
        raise SystemExit(f"Bundled plugin directory not found: {source_dir}")
    if not vault_dir.is_dir():
        raise SystemExit(f"Vault directory not found: {vault_dir}")

    required = ["manifest.json", "main.js", "styles.css"]
    missing = [name for name in required if not (source_dir / name).is_file()]
    if missing:
        raise SystemExit(f"Bundled plugin is incomplete: {', '.join(missing)}")

    if target_dir.exists():
        if not args.overwrite:
            raise SystemExit(
                f"Plugin already exists: {target_dir}\n"
                "Re-run with --overwrite if you want to replace it."
            )
        shutil.rmtree(target_dir)

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)
    print(
        "{\n"
        '  "ok": true,\n'
        f'  "plugin_id": "{PLUGIN_ID}",\n'
        f'  "installed_to": "{target_dir}"\n'
        "}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
