#!/usr/bin/env python3
"""Workshop prep for Nowa Huta: sound metadata, credits table rows, optional SVG wiring.

Active workflow (default when you run this file):

1. Edit ``SOUNDS_DATA`` — one entry per sound *slot* you want on the credits page.
2. Set ``CREDITS_PIECE_COUNT`` to how many segment IDs to emit (↑ base, ↓ ``_mod``).
3. Run from repo root::

     python3 nowa-huta/maps/helpers/inkscape_organizer.py

4. Paste ``nowa-huta/maps/helpers/credits_table.html`` into ``nowa-huta/credits.html``
   (table body, after the header row). The map ``index.html`` footer author list is
   still edited by hand; it is not generated here.

``SOUNDS_DATA`` value shape: ``[author, far_name, near_name]`` matching ↑ / ↓ rows.
Missing keys still get audio preview rows with empty author/name cells.

Historical workflow (optional, off by default): pass ``--svg`` to run the Inkscape export
pipeline that adds ``puzzle pieceN``, ``onclick``, and SVG ``<title>`` tooltips. See
``nowa-huta/maps/helpers/README.md`` for paths and caveats.

This script does not copy files into ``nowa-huta/sounds/``; place ``{id}.wav`` and
``{id}_mod.wav`` (or other formats referenced by ``script.js``) there yourself.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# --- Map / deploy settings (Nowa Huta) ---

MAP_PREFIX = "nowa-huta/"
DEPLOY_ORIGIN = "https://beatmaps.pages.dev"

# How many segment IDs (0 .. CREDITS_PIECE_COUNT - 1) appear on the credits page.
# Live map segments may exceed this; raise the count when adding credits for new IDs.
CREDITS_PIECE_COUNT = 14

# author, far-layer label (↑), near-layer label (↓)
SOUNDS_DATA: dict[int, list[str]] = {
    0: ["", "sznurek do prania", "fortepian i talerz"],
    1: ["", "domofon", "buahahaha"],
    2: ["", "nalewanie wody", ""],
    3: ["", "trzmiel", "trzmiel"],
    4: ["", "pszczola", "pszczola"],
    5: ["", "golebie", "korg"],
    6: ["", "plac centralny samochod", "korg"],
    7: ["", "toczaca sie butelka", "fortepian"],
    8: ["", "butelka spada", "pisak"],
    9: ["", "metalowa butelka", ""],
    10: ["", "butelka sie toczy (wyciete)", ""],
    11: ["", "jerzyki", "fortepian"],
    12: ["", "gwizdanie", ""],
    13: ["", "", "impact"],
    14: ["", "", "fortepian"],
}

HELPERS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HELPERS_DIR.parents[2]
CREDITS_TABLE_PATH = HELPERS_DIR / "credits_table.html"

# Legacy SVG pass (only used with --svg)
SVG_INPUT = REPO_ROOT / "nowa-huta/maps/mapa_inkscaped_manual_cut.svg"
SVG_OUTPUT = HELPERS_DIR / "new_map_parsed.svg"


def sound_url(sound_id: int, *, mod: bool = False) -> str:
    suffix = "_mod" if mod else ""
    return f"{DEPLOY_ORIGIN}/{MAP_PREFIX}sounds/{sound_id}{suffix}.wav"


def generate_credits_double_row(sound_id: int) -> str:
    author, far_name, near_name = SOUNDS_DATA[sound_id]
    return f"""
<tr>
    <td>{sound_id} ↑</td>
    <td>{author}</td>
    <td>{far_name}</td>
    <td><audio controls><source src="{sound_url(sound_id)}"></audio></td>
</tr>
<tr>
    <td>{sound_id} ↓</td>
    <td>{author}</td>
    <td>{near_name}</td>
    <td><audio controls><source src="{sound_url(sound_id, mod=True)}"></audio></td>
</tr>"""


def generate_credits_double_empty_row(sound_id: int) -> str:
    return f"""
<tr>
    <td>{sound_id} ↑</td>
    <td></td>
    <td></td>
    <td><audio controls><source src="{sound_url(sound_id)}"></audio></td>
</tr>
<tr>
    <td>{sound_id} ↓</td>
    <td></td>
    <td></td>
    <td><audio controls><source src="{sound_url(sound_id, mod=True)}"></audio></td>
</tr>"""


def write_credits_table(path: Path = CREDITS_TABLE_PATH) -> None:
    rows: list[str] = []
    for sound_id in range(CREDITS_PIECE_COUNT):
        if sound_id in SOUNDS_DATA:
            rows.append(generate_credits_double_row(sound_id))
        else:
            rows.append(generate_credits_double_empty_row(sound_id))
    path.write_text("".join(rows), encoding="utf-8")


def sound_tooltip(sound_id: int) -> str | None:
    if sound_id not in SOUNDS_DATA:
        return None
    author, far_name, near_name = SOUNDS_DATA[sound_id]
    return (
        f'\n    Top sound: "{far_name}"\n'
        f'    Bottom sound: "{near_name}"\n\n'
        f"    Author: {author}\n    "
    )


def write_parsed_svg(
    input_path: Path = SVG_INPUT,
    output_path: Path = SVG_OUTPUT,
) -> int:
    """Add puzzle classes, playSound handlers, and tooltips to an Inkscape group export."""
    sound_num = -1
    sounds_amount = -1
    lines_out: list[str] = []

    with input_path.open(encoding="utf-8") as map_file:
        for line in map_file:
            if 'style="fill:#000000"' in line:
                line = line.replace('style="fill:#000000"', "")
            if ";fill:#000000" in line:
                line = line.replace(";fill:#000000", "")
            if 'fill="#000000"' in line:
                line = line.replace('fill="#000000"', "")
            if 'stroke="none"' in line:
                line = line.replace('stroke="none"', "")

            if "<g" in line:
                if sound_num == -1:
                    sound_num += 1
                elif sound_num <= sounds_amount:
                    line = line.replace(
                        "<g",
                        f"""<g class="puzzle piece{sound_num}" """
                        f'''onclick="playSound('{MAP_PREFIX}', {sound_num})" ''',
                    )
                    sound_num += 1

            if "</g>" in line:
                tooltip = sound_tooltip(sound_num - 1)
                if tooltip:
                    line = line.replace("</g>", f"<title>{tooltip}</title></g>")

            lines_out.append(line)

    output_path.write_text("".join(lines_out), encoding="utf-8")
    return sound_num


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate credits rows and optional SVG wiring.")
    parser.add_argument(
        "--svg",
        action="store_true",
        help="Run legacy Inkscape SVG pass (writes new_map_parsed.svg; does not touch credits_table.html).",
    )
    args = parser.parse_args()

    if args.svg:
        count = write_parsed_svg()
        print(f"Wrote {SVG_OUTPUT} ({count} group passes)")
        return

    write_credits_table()
    print(f"Wrote {CREDITS_TABLE_PATH}")


if __name__ == "__main__":
    main()
