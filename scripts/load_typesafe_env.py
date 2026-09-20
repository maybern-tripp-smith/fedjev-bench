"""Load TYPESAFE_API_KEY from the environment only.

Never print the key. Box/local secret-file paths are intentionally unsupported
in the public tree — set the env var (or a local `.env` that you do not commit).
"""
from __future__ import annotations

import os


def ensure() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY"))


if __name__ == "__main__":
    print("set" if ensure() else "missing")
