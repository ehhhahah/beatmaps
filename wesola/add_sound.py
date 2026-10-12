#!/usr/bin/env python3
"""Add a workshop sound to BeatMap 2: Wesoła.

Run from the repository root::

    python3 wesola/add_sound.py <audio_path> <area_id> <author> <title>

What this updates:
1. Copies audio → ``wesola/sounds/{id}{ext}``
2. ``SOUNDS_DATA`` (and ``SOUND_EXT`` if not .wav) in ``maps/helpers/credits_organizer.py``
3. ``WESOLA_SOUND_EXT`` in ``wesola/index.html`` (so the piece becomes clickable)
4. A ``<tr>`` row in ``wesola/credits.html``
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOUNDS_DIR = REPO_ROOT / "wesola" / "sounds"
RAW_SOUNDS_DIR = SOUNDS_DIR / "raw"
CREDITS_ORGANIZER = REPO_ROOT / "wesola" / "maps" / "helpers" / "credits_organizer.py"
INDEX_HTML = REPO_ROOT / "wesola" / "index.html"
CREDITS_HTML = REPO_ROOT / "wesola" / "credits.html"
DEPLOY_ORIGIN = "https://beatmaps.pages.dev"


def _escape_js_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _py_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _upsert_sounds_data(sound_id: int, author: str, title: str) -> None:
    value = f"[{_py_str(author)}, {_py_str(title)}]"
    _upsert_dict_entry(CREDITS_ORGANIZER, "SOUNDS_DATA", sound_id, value)


def _upsert_dict_entry(path: Path, dict_name: str, sound_id: int, value_code: str | None) -> None:
    """Insert/replace ``sound_id: value_code`` inside ``dict_name = {...}``, or remove if value_code is None."""
    text = path.read_text(encoding="utf-8")
    m = re.search(
        rf"({dict_name}\s*:[^=\n]+=\s*\{{)(.*?)(\n\}})",
        text,
        flags=re.S,
    )
    if not m:
        raise SystemExit(f"Could not find {dict_name} in {path}")

    body = m.group(2)
    line_re = re.compile(rf"^\s*{sound_id}\s*:.*\n?", re.M)
    had = bool(line_re.search(body))
    body_wo = line_re.sub("", body)

    if value_code is None:
        if not had:
            return
        new_body = body_wo
        action = "Removed"
    else:
        entry_line = f"\n    {sound_id}: {value_code},"
        new_body = body_wo.rstrip() + entry_line + "\n"
        action = "Updated"

    path.write_text(text[: m.start(2)] + new_body + text[m.end(2) :], encoding="utf-8")
    print(f"{action} {dict_name}[{sound_id}] in {path.relative_to(REPO_ROOT)}")


def _upsert_sound_ext(sound_id: int, ext: str) -> None:
    """Keep SOUND_EXT only for non-default (.wav) files."""
    if ext == ".wav":
        _upsert_dict_entry(CREDITS_ORGANIZER, "SOUND_EXT", sound_id, None)
    else:
        _upsert_dict_entry(CREDITS_ORGANIZER, "SOUND_EXT", sound_id, f'"{ext}"')


def _upsert_wesola_sound_ext(sound_id: int, ext: str) -> None:
    """Piece is clickable only if its id is a key in WESOLA_SOUND_EXT."""
    text = INDEX_HTML.read_text(encoding="utf-8")
    entry = f"{sound_id}: '{_escape_js_str(ext)}'"

    m = re.search(r"var\s+WESOLA_SOUND_EXT\s*=\s*\{([^}]*)\}\s*;", text)
    if not m:
        raise SystemExit(f"Could not find WESOLA_SOUND_EXT in {INDEX_HTML}")

    body = m.group(1).strip()
    pairs: dict[int, str] = {}
    if body:
        for part in body.split(","):
            part = part.strip()
            if not part:
                continue
            km = re.match(r"(\d+)\s*:\s*['\"]([^'\"]*)['\"]", part)
            if km:
                pairs[int(km.group(1))] = km.group(2)

    pairs[sound_id] = ext
    new_body = ", ".join(f"{k}: '{_escape_js_str(pairs[k])}'" for k in sorted(pairs))
    new_decl = f"var WESOLA_SOUND_EXT = {{{new_body}}};"
    text = text[: m.start()] + new_decl + text[m.end() :]
    INDEX_HTML.write_text(text, encoding="utf-8")
    print(f"Updated WESOLA_SOUND_EXT in {INDEX_HTML.relative_to(REPO_ROOT)}")


def _credits_row(sound_id: int, author: str, title: str, ext: str) -> str:
    url = f"{DEPLOY_ORIGIN}/wesola/sounds/{sound_id}{ext}"
    return (
        f"<tr>\n"
        f"    <td>{sound_id}</td>\n"
        f"    <td>{_escape_html(author)}</td>\n"
        f"    <td>{_escape_html(title)}</td>\n"
        f'    <td><audio controls><source src="{url}"></audio></td>\n'
        f"</tr>"
    )


def _upsert_credits_row(sound_id: int, author: str, title: str, ext: str) -> None:
    text = CREDITS_HTML.read_text(encoding="utf-8")
    row = _credits_row(sound_id, author, title, ext)
    row_re = re.compile(
        rf"<tr>\s*<td>\s*{sound_id}\s*</td>.*?</tr>",
        flags=re.S | re.I,
    )

    if row_re.search(text):
        text = row_re.sub(row, text, count=1)
        print(f"Replaced credits row for ID {sound_id}")
    else:
        marker = "<!-- Paste wesola/maps/helpers/credits_table.html below -->"
        if marker not in text:
            raise SystemExit(f"Credits marker not found in {CREDITS_HTML}")
        text = text.replace(marker, marker + "\n\n" + row, 1)
        print(f"Inserted credits row for ID {sound_id}")

    CREDITS_HTML.write_text(text, encoding="utf-8")


def resolve_source(source_file: str) -> Path:
    """Absolute / ~/ paths as-is; otherwise look under ``wesola/sounds/raw/``."""
    src = Path(source_file).expanduser()
    if not src.is_absolute():
        src = RAW_SOUNDS_DIR / src
    return src.resolve()


def add_sound(source_file: str, sound_id: str, author: str, title: str) -> None:
    src = resolve_source(source_file)
    if not src.is_file():
        raise SystemExit(
            f"Audio file not found: {src}\n"
            f"  (relative names are resolved under {RAW_SOUNDS_DIR})"
        )

    try:
        sid = int(sound_id)
    except ValueError:
        raise SystemExit(f"Area ID must be an integer, got: {sound_id!r}") from None

    ext = src.suffix or ".wav"
    dest = SOUNDS_DIR / f"{sid}{ext}"
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"Copied audio → {dest.relative_to(REPO_ROOT)}")

    _upsert_sounds_data(sid, author, title)
    _upsert_sound_ext(sid, ext)
    _upsert_wesola_sound_ext(sid, ext)
    _upsert_credits_row(sid, author, title, ext)


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python3 wesola/add_sound.py <audio_path> <area_id> <author> <title>")
        print("  (run from the repository root)")
        print(f"  Relative <audio_path> → {RAW_SOUNDS_DIR}/<audio_path>")
        sys.exit(1)

    add_sound(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
