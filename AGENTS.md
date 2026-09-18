# AGENTS.md — BeatMaps

Guidance for coding agents working in this repository.

## Project intent

BeatMaps is a **workshop series** artifact, not a product SPA. Workshop flow:

1. Participants draw / work from a hand-drawn map.
2. The map is converted into an **SVG already divided into segments**.
3. Each segment is assigned sounds by participants.
4. The result is a **static interactive web page**: clicking segments layers looping audio into a polyrhythmic composition.

**Do not** introduce a framework, bundler, or backend unless explicitly requested. Prefer plain HTML / CSS / JS that matches the existing maps.

## Stack and deployment

- Static site hosted at `https://beatmaps.pages.dev/` (Cloudflare Pages).
- Root `index.html` is the hub listing maps.
- Shared logic: `script.js`, shared look: `global-style.css`.
- Per-map folder (e.g. `nowa-huta/`) holds `index.html` (large inline SVG), map CSS, `sounds/`, and optional credits.
- `<base href="https://beatmaps.pages.dev/">` is set on pages — paths in HTML/JS are often site-root-relative (`nowa-huta/...`). Local preview needs an HTTP server from the repo root.

## Audio / segment model (Nowa Huta)

- Interactive SVG groups use classes `puzzle pieceN` and `onclick="playSound('nowa-huta/', N)"`.
- `playSound(projectPath, soundId, fileFormat1, fileFormat2)` toggles a pair of looping `Audio` objects:
  - `{projectPath}sounds/{id}{ext}` — “far” / default layer
  - `{projectPath}sounds/{id}_mod{ext}` — “near” / zoomed layer
- Formats vary per file (`.mp3`, `.wav`, `.WAV`); callers can pass extensions; defaults are `.mp3`.
- Active pieces get `piece-active` (CSS pulse in `nowa-huta-style.css`).
- Zoom slider (`slide`): scales `#svgmap` and sets `ZOOM_POSITION`, crossfading volumes between the two layers via `setModAudioVolumeByZoom`.
- RangeTouch CDN is used for better mobile range input (`rangetouch.js`).

Segment IDs for Nowa Huta today: **0–21**. Credits live in `nowa-huta/credits.html` (↑ = base, ↓ = `_mod`).

## Maps timeline

| Folder / name | Added | Zoom slider |
|---------------|-------|-------------|
| `nowa-huta/` — BeatMap 1 | July 2022 | Yes |
| `wesola/` — BeatMap 2 (Wesoła) | October 2026 | **No** |

Wesoła notes:

- URL slug is `wesola` (ASCII `l`, not `ł`).
- Mint / green palette in `wesola/wesola-style.css` (contrast to Nowa Huta yellow / red).
- Map SVG is loaded from `wesola/wesola.svg` (not inlined). Replace that file with the segmented workshop SVG; interactive groups still use `class="puzzle pieceN"` and `onclick="playSound('wesola/', N)"`.
- No zoom slider; reuse `script.js` without RangeTouch / crossfade UI.
- Working maps / helpers live under `wesola/maps/`. Size split: `wesola/maps/helpers/layer_by_size.py`. Spatial refine (absorb nearby flecks, optional roads/trains clip of former piece-0): `wesola/maps/helpers/refine_layers.py`. Keep `wesola_layered_v1.svg` as pre-refine backup when iterating.

## SVG workflow (important)

The app **assumes the SVG is already segmented**. Agents should not invent auto-segmentation pipelines unless asked. Source / working SVGs under `nowa-huta/maps/` (Inkscape exports, helpers) are production prep artifacts; the live map is the **inline SVG** inside `nowa-huta/index.html` (`id="svgmap"`).

Editable expectations for clickable pieces:

- `class` includes `puzzle` and `piece{id}`
- `onclick` calls `playSound` with the map path prefix and numeric id
- Decorative / non-interactive groups stay without `puzzle` / click handlers

## Conventions for changes

- Keep the aesthetic and interaction language of existing pages (serif typography, light wash background, red puzzle fills, black UI accents).
- Avoid large refactors of the inline SVG unless the task is map content.
- Do not commit secrets; there are none expected in this static workshop site.
- Prefer minimal diffs: one map at a time, preserve Nowa Huta behavior when adding new maps.
- `artzona_sample/` under a map folder may contain Bitwig / sample workshop material — treat as content, not app runtime.

## Quick local check

```bash
# from repo root
npx serve .
# open / and /nowa-huta/ — click segments, verify loops and (map 1) slider crossfade
```

## Authors / contacts

Joanna Wabik · ehh hahah — see root `README.md` and hub page for public links and emails.
