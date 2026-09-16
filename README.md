# BeatMaps

BeatMaps is a workshop project: a hand-drawn map is turned into an SVG full of clickable segments. Workshop participants map each segment to a sound. Together, those loops become a polyrhythmic composition you play in the browser.

Live site: [beatmaps.pages.dev](https://beatmaps.pages.dev/)

Workshops are run by [Joanna Wabik](https://yoxoko.wordpress.com/) and [ehh hahah](https://linktr.ee/ehhhahah).

## How it works (as a visitor)

1. Open a BeatMap (for example *Nowa Huta*).
2. Click a region on the map to start or stop its loop.
3. Layer several regions — the piece is whatever you’re playing at once.
4. On the first map, use the top slider to zoom and crossfade into alternate (“mod”) versions of the sounds.

## Maps

| Map | When | Notes |
|-----|------|--------|
| [BeatMap 1: Nowa Huta, Kraków](./nowa-huta/) | July 2022 | Zoom / sound-morph slider |
| [BeatMap 2: Wesoła](./wesola/) | October 2026 | No zoom slider; mint / green |

## Tech (short version)

This is a static website. There is no build step and no backend. Each map page embeds an SVG that is already cut into segments; the page just wires clicks to audio files.

To try it locally, serve the repo root over HTTP (browsers often block audio from `file://`):

```bash
npx serve .
# or: python3 -m http.server
```

Then open the printed URL and go to `/nowa-huta/`.

Contact: [wabikas@gmail.com](mailto:wabikas@gmail.com) · [ehhhahah@gmail.com](mailto:ehhhahah@gmail.com)
