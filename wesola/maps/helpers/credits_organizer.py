#!/usr/bin/env python3
"""Workshop prep for Wesoła: sound metadata and credits table rows (one row per segment).

Wesoła has no zoom crossfade — each clickable ``layer-piece-N`` maps to a single loop
``wesola/sounds/{N}.wav`` (see ``playWesolaPiece`` in ``wesola/index.html``).

Workflow:

1. Edit ``SOUNDS_DATA`` — ``[author, sample_name]`` per piece ID (IDs match ``layer-piece-N``).
2. Run from repo root (piece IDs are read from ``wesola_layered.svg`` by default)::

     python3 wesola/maps/helpers/credits_organizer.py

3. Paste ``wesola/maps/helpers/credits_table.html`` into ``wesola/credits.html``
   after the table header row. Footer author names on ``index.html`` stay manual.

This script does not copy audio into ``wesola/sounds/``.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

MAP_PREFIX = "wesola/"
DEPLOY_ORIGIN = "https://beatmaps.pages.dev"
AUDIO_EXT = ".wav"

# author, sample name (one row per segment)
SOUNDS_DATA: dict[int, list[str]] = {
    # Example:
    # 1: ["Ania", "ptaki nad torami"],
}

HELPERS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HELPERS_DIR.parents[2]
DEFAULT_SVG = REPO_ROOT / "wesola/maps/wesola_layered.svg"
CREDITS_TABLE_PATH = HELPERS_DIR / "credits_table.html"

PIECE_ID_RE = re.compile(r'id="layer-piece-(\d+)"')


def sound_url(sound_id: int) -> str:
    return f"{DEPLOY_ORIGIN}/{MAP_PREFIX}sounds/{sound_id}{AUDIO_EXT}"


def piece_ids_from_svg(svg_path: Path) -> list[int]:
    text = svg_path.read_text(encoding="utf-8")
    return sorted({int(m) for m in PIECE_ID_RE.findall(text)})


def generate_credits_row(sound_id: int) -> str:
    author, name = SOUNDS_DATA.get(sound_id, ["", ""])
    return f"""
<tr>
    <td>{sound_id}</td>
    <td>{author}</td>
    <td>{name}</td>
    <td><audio controls><source src="{sound_url(sound_id)}"></audio></td>
</tr>"""


def write_credits_table(piece_ids: list[int], path: Path = CREDITS_TABLE_PATH) -> None:
    rows = [generate_credits_row(sound_id) for sound_id in piece_ids]
    path.write_text("".join(rows), encoding="utf-8")


def parse_id_list(raw: str) -> list[int]:
    return sorted({int(part.strip()) for part in raw.split(",") if part.strip()})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Wesoła credits table rows.")
    parser.add_argument(
        "--svg",
        type=Path,
        default=DEFAULT_SVG,
        help=f"SVG to scan for layer-piece-N ids (default: {DEFAULT_SVG.relative_to(REPO_ROOT)}).",
    )
    parser.add_argument(
        "--ids",
        metavar="1,2,3",
        help="Comma-separated piece IDs (skips SVG scan).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=CREDITS_TABLE_PATH,
        help="Output HTML fragment path.",
    )
    args = parser.parse_args()

    if args.ids:
        piece_ids = parse_id_list(args.ids)
    else:
        if not args.svg.is_file():
            raise SystemExit(f"SVG not found: {args.svg} (use --ids to specify piece IDs manually)")
        piece_ids = piece_ids_from_svg(args.svg)

    if not piece_ids:
        raise SystemExit("No piece IDs found.")

    write_credits_table(piece_ids, args.output)
    print(f"Wrote {len(piece_ids)} rows to {args.output} (IDs {piece_ids[0]}–{piece_ids[-1]})")


if __name__ == "__main__":
    main()
