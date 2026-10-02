# Nowa Huta map helpers

Production prep scripts for BeatMap 1. Nothing here runs in the browser.

## Credits and sound attribution

Visitors see two different “credits” surfaces:

| Surface | File | What it contains |
|---------|------|------------------|
| Sound table | [`nowa-huta/credits.html`](../../credits.html) | Per segment ID: author, sample name, audio preview (↑ = default layer, ↓ = `_mod` zoom layer) |
| Workshop names | [`nowa-huta/index.html`](../../index.html) footer (`.authors`) | People who took part; edited manually |

There is no link from the map page to `credits.html` today; the page is reachable at `/nowa-huta/credits.html`.

### `inkscape_organizer.py`

Single source of truth for **sound names and authors** used on the credits table.

**Data model** — `SOUNDS_DATA[id]` is a three-string list:

1. Author (often empty in the shipped map)
2. Label for ↑ row — file `{id}.wav` / default loop in `playSound`
3. Label for ↓ row — file `{id}_mod.wav` / “near” loop when the zoom slider is up (Nowa Huta only)

**Generate table rows**

```bash
# from repository root
python3 nowa-huta/maps/helpers/inkscape_organizer.py
```

Output: [`credits_table.html`](credits_table.html) — only `<tr>…</tr>` fragments.

**Publish**

1. Open `nowa-huta/credits.html`.
2. Replace the table body (keep the header row with ID / Author / Name / Audio file).
3. Ensure matching files exist under `nowa-huta/sounds/` (`{id}.wav`, `{id}_mod.wav`, plus any `.mp3` variants the live map uses).

**Tune scope** — `CREDITS_PIECE_COUNT` controls how many IDs get rows (default `14` → IDs `0`–`13`). The live SVG has more clickable pieces (`0`–`21`); extend the count and `SOUNDS_DATA` when you add credits for new segments. Keys in `SOUNDS_DATA` that fall outside `range(CREDITS_PIECE_COUNT)` are ignored until you raise the count.

Audio URLs in generated HTML point at `https://beatmaps.pages.dev/…` so previews work on the deployed site; local `file://` preview may not load those sources.

### Legacy SVG wiring (`--svg`)

Early workshop flow: Inkscape export with one top-level `<g>` per puzzle piece, then automatic:

- `class="puzzle pieceN"`
- `onclick="playSound('nowa-huta/', N)"`
- `<title>` tooltip from `SOUNDS_DATA`

```bash
python3 nowa-huta/maps/helpers/inkscape_organizer.py --svg
```

Reads `nowa-huta/maps/mapa_inkscaped_manual_cut.svg`, writes `new_map_parsed.svg`. The live map is the **inline SVG** inside `index.html`; this pass is kept for reference when preparing a new export, not for day-to-day edits.

## Other files

- [`credits_table.html`](credits_table.html) — generated fragment; safe to regenerate.
- [`new_map_parsed.svg`](new_map_parsed.svg) — last optional `--svg` output.

## Wesoła and other maps

Same pattern applies: per-map `SOUNDS_DATA`, credits HTML, and `sounds/{id}…` files. Wesoła has no `_mod` layer or zoom slider — a future helper can emit one row per segment instead of ↑/↓ pairs (copy-paste from this script is fine).
