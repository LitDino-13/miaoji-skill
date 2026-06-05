#!/usr/bin/env python3
"""Check optional FunASR local backend dependencies."""

from __future__ import annotations

import importlib.util
import json


MODULES = ["torch", "torchaudio", "funasr", "modelscope"]


def main() -> None:
    status = {name: importlib.util.find_spec(name) is not None for name in MODULES}
    missing = [name for name, ok in status.items() if not ok]
    payload = {
        "ok": not missing,
        "status": status,
        "missing": missing,
        "install_command": "python3 -m pip install torch torchaudio funasr modelscope" if missing else "",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
