#!/usr/bin/env python3
"""Refine wesola_layered.svg after the initial size-based split.

Fixes that size-sorting alone cannot do:

1. piece-0 (roads+trains) is one filled mesh with ~1000 holes — not separate
   shapes. Optional clip-band split into ``network-roads`` + ``network-trains``.
2–6. Absorb tiny paths (and overlapping neighbor pieces) into nearby buildings.

Example:
  mise exec -- python wesola/maps/helpers/refine_layers.py \\
    wesola/maps/wesola_layered.svg -o wesola/maps/wesola_layered.svg \\
    --split-network --rail-y0 1980 --rail-y1 2360 --stats
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)

NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
TRANSLATE_RE = re.compile(
    r"translate\(\s*([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)\s*[,\s]\s*"
    r"([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)\s*\)"
)
INK_LABEL = f"{{{INKSCAPE_NS}}}label"
INK_MODE = f"{{{INKSCAPE_NS}}}groupmode"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass
class BBox:
    minx: float
    miny: float
    maxx: float
    maxy: float

    @property
    def width(self) -> float:
        return self.maxx - self.minx

    @property
    def height(self) -> float:
        return self.maxy - self.miny

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def cx(self) -> float:
        return (self.minx + self.maxx) / 2

    @property
    def cy(self) -> float:
        return (self.miny + self.maxy) / 2

    def expanded(self, pad: float) -> "BBox":
        return BBox(
            self.minx - pad, self.miny - pad, self.maxx + pad, self.maxy + pad
        )

    def contains_point(self, x: float, y: float, margin: float = 0.0) -> bool:
        return (
            self.minx - margin <= x <= self.maxx + margin
            and self.miny - margin <= y <= self.maxy + margin
        )

    def intersects(self, other: "BBox") -> bool:
        return not (
            self.maxx < other.minx
            or self.minx > other.maxx
            or self.maxy < other.miny
            or self.miny > other.maxy
        )

    def gap(self, other: "BBox") -> float:
        dx = max(0.0, max(self.minx - other.maxx, other.minx - self.maxx))
        dy = max(0.0, max(self.miny - other.maxy, other.miny - self.maxy))
        return (dx * dx + dy * dy) ** 0.5

    def union(self, other: "BBox") -> "BBox":
        return BBox(
            min(self.minx, other.minx),
            min(self.miny, other.miny),
            max(self.maxx, other.maxx),
            max(self.maxy, other.maxy),
        )


def path_bbox(el: ET.Element) -> BBox | None:
    d = (el.get("d") or "").strip()
    if not d:
        return None
    nums = [float(x) for x in NUMBER_RE.findall(d)]
    xs, ys = nums[0::2], nums[1::2]
    if not xs or not ys:
        return None
    m = TRANSLATE_RE.search(el.get("transform") or "")
    tx = float(m.group(1)) if m else 0.0
    ty = float(m.group(2)) if m else 0.0
    return BBox(min(xs) + tx, min(ys) + ty, max(xs) + tx, max(ys) + ty)


def layer_label(g: ET.Element) -> str:
    return g.get(INK_LABEL) or g.get("id") or ""


def make_layer(label: str, layer_id: str) -> ET.Element:
    g = ET.Element(f"{{{SVG_NS}}}g")
    g.set("id", layer_id)
    g.set(INK_MODE, "layer")
    g.set(INK_LABEL, label)
    return g


def iter_layers(root: ET.Element) -> list[ET.Element]:
    return [c for c in list(root) if local_name(c.tag) == "g"]


def layer_paths(g: ET.Element) -> list[ET.Element]:
    return [p for p in list(g) if local_name(p.tag) == "path"]


def layer_bbox(g: ET.Element) -> BBox | None:
    boxes = [b for b in (path_bbox(p) for p in layer_paths(g)) if b]
    if not boxes:
        return None
    out = boxes[0]
    for b in boxes[1:]:
        out = out.union(b)
    return out


def find_layer(root: ET.Element, label: str) -> ET.Element | None:
    for g in iter_layers(root):
        if layer_label(g) == label:
            return g
    return None


def absorb_smalls_into_piece(
    root: ET.Element,
    piece_label: str,
    *,
    inside_margin: float = 8.0,
    max_gap: float = 12.0,
    max_small_area: float = 5000.0,
) -> int:
    """Move small-merged paths into a piece if inside or within max_gap."""
    piece = find_layer(root, piece_label)
    small = find_layer(root, "small-merged")
    if piece is None or small is None:
        return 0
    bb = layer_bbox(piece)
    if bb is None:
        return 0

    take: list[ET.Element] = []
    for p in layer_paths(small):
        pb = path_bbox(p)
        if pb is None or pb.area > max_small_area:
            continue
        if bb.expanded(inside_margin).contains_point(pb.cx, pb.cy) or bb.gap(pb) <= max_gap:
            take.append(p)

    for p in take:
        small.remove(p)
        piece.append(p)
    return len(take)


def merge_pieces(root: ET.Element, keep_label: str, drop_label: str) -> int:
    """Move all paths from drop into keep; remove empty drop layer."""
    keep = find_layer(root, keep_label)
    drop = find_layer(root, drop_label)
    if keep is None or drop is None:
        return 0
    paths = layer_paths(drop)
    for p in paths:
        drop.remove(p)
        keep.append(p)
    if len(list(drop)) == 0:
        root.remove(drop)
    return len(paths)


def split_network_by_rail_band(
    root: ET.Element,
    *,
    rail_y0: float,
    rail_y1: float,
    width: float,
    height: float,
) -> bool:
    """Split piece-0 into roads + trains using clip paths on the same mesh.

    piece-0 is a single fill with holes (city fabric). Break-apart would destroy
    it; clipping keeps the mesh intact while separating a horizontal band
    (trains) from the rest (roads). Tune rail_y0/rail_y1 in Inkscape if needed.
    """
    piece = find_layer(root, "piece-0")
    if piece is None:
        return False
    paths = layer_paths(piece)
    if not paths:
        return False

    # defs with clip paths
    defs = None
    for child in list(root):
        if local_name(child.tag) == "defs":
            defs = child
            break
    if defs is None:
        defs = ET.Element(f"{{{SVG_NS}}}defs")
        root.insert(0, defs)

    clip_trains = ET.SubElement(defs, f"{{{SVG_NS}}}clipPath")
    clip_trains.set("id", "clip-network-trains")
    clip_trains.set("clipPathUnits", "userSpaceOnUse")
    train_rect = ET.SubElement(clip_trains, f"{{{SVG_NS}}}rect")
    train_rect.set("x", "0")
    train_rect.set("y", str(rail_y0))
    train_rect.set("width", str(width))
    train_rect.set("height", str(rail_y1 - rail_y0))

    clip_roads = ET.SubElement(defs, f"{{{SVG_NS}}}clipPath")
    clip_roads.set("id", "clip-network-roads")
    clip_roads.set("clipPathUnits", "userSpaceOnUse")
    # roads = above band + below band
    r1 = ET.SubElement(clip_roads, f"{{{SVG_NS}}}rect")
    r1.set("x", "0")
    r1.set("y", "0")
    r1.set("width", str(width))
    r1.set("height", str(rail_y0))
    r2 = ET.SubElement(clip_roads, f"{{{SVG_NS}}}rect")
    r2.set("x", "0")
    r2.set("y", str(rail_y1))
    r2.set("width", str(width))
    r2.set("height", str(max(0.0, height - rail_y1)))

    roads = make_layer("network-roads", "layer-network-roads")
    trains = make_layer("network-trains", "layer-network-trains")
    roads.set("clip-path", "url(#clip-network-roads)")
    trains.set("clip-path", "url(#clip-network-trains)")

    # Original path stays on roads; deep copy for trains.
    for p in paths:
        trains.append(copy.deepcopy(p))
        piece.remove(p)
        roads.append(p)

    # Guide layer with editable band rect (opacity low) for Inkscape tuning.
    guide = make_layer("guide-rail-band", "layer-guide-rail-band")
    guide.set("style", "display:none")  # hidden by default; toggle in Inkscape
    grect = ET.SubElement(guide, f"{{{SVG_NS}}}rect")
    grect.set("id", "rail-band-guide")
    grect.set("x", "0")
    grect.set("y", str(rail_y0))
    grect.set("width", str(width))
    grect.set("height", str(rail_y1 - rail_y0))
    grect.set("fill", "#00ffff")
    grect.set("opacity", "0.25")
    grect.set(
        f"{{{INKSCAPE_NS}}}label",
        f"rail band y={rail_y0:g}..{rail_y1:g} — edit then re-run with new --rail-y*",
    )

    # Replace piece-0 in-place order: insert where piece-0 was.
    idx = list(root).index(piece)
    root.remove(piece)
    root.insert(idx, roads)
    root.insert(idx + 1, trains)
    root.append(guide)
    return True


def renumber_piece_layers(root: ET.Element) -> None:
    """Keep existing piece-* labels stable; only ensure ids match labels.

    We intentionally do NOT renumber after merges so Inkscape notes / chat
    references (piece-38 etc.) stay valid for layers that remain.
    """
    for g in iter_layers(root):
        label = layer_label(g)
        if label.startswith("piece-") or label.startswith("network-"):
            g.set("id", f"layer-{label}")


def apply_wesola_fixes(
    root: ET.Element,
    *,
    split_network: bool,
    rail_y0: float,
    rail_y1: float,
    width: float,
    height: float,
) -> dict[str, int | bool]:
    stats: dict[str, int | bool] = {}

    # 2. piece-1 — tiny objects inside / hugging the shape
    stats["piece-1"] = absorb_smalls_into_piece(
        root, "piece-1", inside_margin=10, max_gap=8, max_small_area=2000
    )

    # 4. piece-38 — dots inside the hollow footprint
    stats["piece-38"] = absorb_smalls_into_piece(
        root, "piece-38", inside_margin=12, max_gap=6, max_small_area=2000
    )

    # 5. piece-63 — adjacent small fragments
    stats["piece-63"] = absorb_smalls_into_piece(
        root, "piece-63", inside_margin=8, max_gap=15, max_small_area=4000
    )

    # 6. piece-68 — nearest fragments sit ~95–150px away
    stats["piece-68"] = absorb_smalls_into_piece(
        root, "piece-68", inside_margin=8, max_gap=160, max_small_area=4000
    )

    # 3. piece-36 — overlaps piece-40 and a small cluster on the east edge
    stats["piece-36_smalls"] = absorb_smalls_into_piece(
        root, "piece-36", inside_margin=20, max_gap=25, max_small_area=4000
    )
    stats["piece-36_merge_40"] = merge_pieces(root, "piece-36", "piece-40")
    # After merging 40, absorb anything now touching the larger union.
    stats["piece-36_smalls_pass2"] = absorb_smalls_into_piece(
        root, "piece-36", inside_margin=20, max_gap=25, max_small_area=4000
    )

    # 1. piece-0 roads / trains
    if split_network:
        stats["split_network"] = split_network_by_rail_band(
            root,
            rail_y0=rail_y0,
            rail_y1=rail_y1,
            width=width,
            height=height,
        )
    else:
        stats["split_network"] = False

    renumber_piece_layers(root)

    # Drop empty small-merged
    small = find_layer(root, "small-merged")
    if small is not None and not layer_paths(small):
        root.remove(small)
        stats["small_merged_removed"] = True
    else:
        stats["small_merged_removed"] = False
        if small is not None:
            stats["small_merged_remaining"] = len(layer_paths(small))

    return stats


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument(
        "--split-network",
        action="store_true",
        help="Split piece-0 into network-roads + network-trains via Y clip band",
    )
    p.add_argument(
        "--rail-y0",
        type=float,
        default=1980.0,
        help="Top of train clip band (SVG Y). Default 1980 — tune in Inkscape.",
    )
    p.add_argument(
        "--rail-y1",
        type=float,
        default=2360.0,
        help="Bottom of train clip band (SVG Y). Default 2360.",
    )
    p.add_argument("--stats", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1

    tree = ET.parse(args.input)
    root = tree.getroot()
    width = float(root.get("width", "2048"))
    height = float(root.get("height", "2732"))

    stats = apply_wesola_fixes(
        root,
        split_network=args.split_network,
        rail_y0=args.rail_y0,
        rail_y1=args.rail_y1,
        width=width,
        height=height,
    )

    if args.stats or args.dry_run:
        print(f"input: {args.input}")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        if args.split_network:
            print(f"  rail band: y={args.rail_y0:g} .. {args.rail_y1:g}")
            print(
                "  note: piece-0 is one mesh with holes; clip split is a starting "
                "point — toggle layer guide-rail-band in Inkscape to check the band."
            )

    if args.dry_run:
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
