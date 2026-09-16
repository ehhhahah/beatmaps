#!/usr/bin/env python3
"""Split a flat SVG into layers by path size.

Small paths are merged into one Inkscape layer. Each large path becomes its
own layer. Empty / zero-size paths are dropped.

Designed for auto-traced workshop maps like wesola/wesola.svg (flat <path>
siblings with translate() transforms).

Example:
  mise exec -- python wesola/maps/helpers/layer_by_size.py \\
    wesola/wesola.svg -o wesola/maps/wesola_layered.svg --stats
"""

from __future__ import annotations

import argparse
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


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass(frozen=True)
class PathMeasure:
    element: ET.Element
    width: float
    height: float
    area: float
    index: int

    @property
    def max_side(self) -> float:
        return max(self.width, self.height)


def path_bbox(d: str) -> tuple[float, float]:
    """Approximate local width/height from absolute path coordinates.

    Good enough for size-sorting auto-traced maps (mostly M/C/Z). Not a
    full SVG path engine.
    """
    nums = [float(x) for x in NUMBER_RE.findall(d)]
    if len(nums) < 2:
        return 0.0, 0.0
    xs = nums[0::2]
    ys = nums[1::2]
    if not xs or not ys:
        return 0.0, 0.0
    return max(xs) - min(xs), max(ys) - min(ys)


def measure_paths(root: ET.Element) -> list[PathMeasure]:
    measured: list[PathMeasure] = []
    for index, child in enumerate(list(root)):
        if local_name(child.tag) != "path":
            continue
        d = (child.get("d") or "").strip()
        if not d:
            continue
        width, height = path_bbox(d)
        measured.append(
            PathMeasure(
                element=child,
                width=width,
                height=height,
                area=width * height,
                index=index,
            )
        )
    return measured


def is_large(m: PathMeasure, min_area: float, min_side: float) -> bool:
    return m.area >= min_area or m.max_side >= min_side


def make_layer(label: str, layer_id: str) -> ET.Element:
    group = ET.Element(f"{{{SVG_NS}}}g")
    group.set("id", layer_id)
    group.set(f"{{{INKSCAPE_NS}}}groupmode", "layer")
    group.set(f"{{{INKSCAPE_NS}}}label", label)
    return group


def layer_svg(
    input_path: Path,
    output_path: Path,
    min_area: float,
    min_side: float,
    small_label: str,
) -> dict[str, int | float]:
    tree = ET.parse(input_path)
    root = tree.getroot()

    measured = measure_paths(root)
    # Drop degenerate geometry (empty bbox) so it does not clutter layers.
    measured = [m for m in measured if m.area > 0]
    large = [m for m in measured if is_large(m, min_area, min_side)]
    small = [m for m in measured if not is_large(m, min_area, min_side)]

    # Preserve original paint order within each bucket.
    large.sort(key=lambda m: m.index)
    small.sort(key=lambda m: m.index)

    # Clear flat children; rebuild as layers.
    for child in list(root):
        root.remove(child)

    # Small layer first (underneath), then each large path as its own layer.
    if small:
        small_layer = make_layer(small_label, "layer-small")
        for m in small:
            small_layer.append(m.element)
        root.append(small_layer)

    for piece_i, m in enumerate(large):
        label = f"piece-{piece_i}"
        layer = make_layer(label, f"layer-piece-{piece_i}")
        layer.append(m.element)
        root.append(layer)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    # Count what was removed from the original flat SVG.
    original_paths = [
        child
        for child in ET.parse(input_path).getroot()
        if local_name(child.tag) == "path"
    ]
    dropped_empty = sum(1 for p in original_paths if not (p.get("d") or "").strip())
    dropped_zero = len(original_paths) - dropped_empty - len(measured)

    areas = [m.area for m in measured]
    return {
        "input_paths": len(measured),
        "small": len(small),
        "large": len(large),
        "dropped_empty": dropped_empty,
        "dropped_zero": dropped_zero,
        "min_area": min_area,
        "min_side": min_side,
        "median_area": sorted(areas)[len(areas) // 2] if areas else 0.0,
        "max_area": max(areas) if areas else 0.0,
    }


def print_stats(measured: list[PathMeasure], min_area: float, min_side: float) -> None:
    large = [m for m in measured if is_large(m, min_area, min_side)]
    small = [m for m in measured if not is_large(m, min_area, min_side)]
    areas = sorted(m.area for m in measured)
    print(f"paths measured: {len(measured)}")
    print(f"large layers:   {len(large)}  (each becomes its own layer)")
    print(f"small merged:   {len(small)}  (one shared layer)")
    if areas:
        print(
            "area: "
            f"min={areas[0]:.1f}  median={areas[len(areas)//2]:.1f}  "
            f"max={areas[-1]:.1f}"
        )
    print("largest 15:")
    for m in sorted(measured, key=lambda x: -x.area)[:15]:
        flag = "LARGE" if is_large(m, min_area, min_side) else "small"
        print(
            f"  [{flag}] area={m.area:.0f}  "
            f"{m.width:.0f}x{m.height:.0f}  index={m.index}"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Merge small SVG paths into one layer; keep each large path "
            "on its own Inkscape layer."
        )
    )
    p.add_argument("input", type=Path, help="Source SVG (flat paths)")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output SVG (default: <input_stem>_layered.svg next to input)",
    )
    p.add_argument(
        "--min-area",
        type=float,
        default=5000.0,
        help="Paths with bbox area >= this become separate layers (default: 5000)",
    )
    p.add_argument(
        "--min-side",
        type=float,
        default=80.0,
        help=(
            "Paths with max(width,height) >= this become separate layers "
            "even if area is below --min-area (default: 80)"
        ),
    )
    p.add_argument(
        "--small-label",
        default="small-merged",
        help="Inkscape label for the merged small-objects layer",
    )
    p.add_argument(
        "--stats",
        action="store_true",
        help="Print size breakdown (and still write output unless --dry-run)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print stats; do not write an output file",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path: Path = args.input
    if not input_path.is_file():
        print(f"error: input not found: {input_path}", file=sys.stderr)
        return 1

    output_path: Path = args.output or input_path.with_name(
        f"{input_path.stem}_layered.svg"
    )

    tree = ET.parse(input_path)
    measured = [m for m in measure_paths(tree.getroot()) if m.area > 0]

    if args.stats or args.dry_run:
        print(f"input: {input_path}")
        print(f"thresholds: min_area={args.min_area}  min_side={args.min_side}")
        print_stats(measured, args.min_area, args.min_side)

    if args.dry_run:
        return 0

    summary = layer_svg(
        input_path=input_path,
        output_path=output_path,
        min_area=args.min_area,
        min_side=args.min_side,
        small_label=args.small_label,
    )
    print(
        f"wrote {output_path}  "
        f"(large={summary['large']} layers, "
        f"small={summary['small']} paths merged, "
        f"dropped_empty={summary['dropped_empty']}, "
        f"dropped_zero={summary['dropped_zero']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
