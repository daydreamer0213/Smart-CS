"""Minimal process boundary for advanced RAG fixture parsing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.parsing.router import parse_structured_file
from app.core.parsing.runtime import configure_parser_runtime


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse one RAG evaluation fixture")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)

    configure_parser_runtime()
    parsed = parse_structured_file(args.source.name, args.source.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(parsed.model_dump_json(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
