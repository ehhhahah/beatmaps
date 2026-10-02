#!/usr/bin/env python3
"""Regroup Wesoła geometry into ``layer-piece-*`` segments by the ``obszary`` guide.

Input: an SVG with the guide group ``g644`` (label ``obszary``) plus the
current geometry layers (``layer-piece-*``, ``layer-small``,
``layer-network-roads`` / ``layer-network-trains``, which share one compound
mesh).

Two stages:

* ``preview`` — writes a copy of the input where geometry is recoloured by its
  planned segment (area colours, grey extras, magenta conflicts).
* ``build`` — writes the regrouped SVG with original fill/stroke, one
  ``layer-piece-N`` per guide area plus extra segments, without the guide and
  without the old network layers.

Heuristic per candidate shape (whole path, or fragment of the network mesh):

1. graze — only a sliver lies in an area → not assigned to it;
2. undrawn guide — most of the shape is in the area → whole shape assigned;
3. deliberate split — the area cuts a large shape / the mesh → the marked
   fragment is cut out (boolean, local), the rest stays in the pool.

Overlapping guides are resolved per pixel by normalised depth (distance to the
guide boundary / inscribed radius), so overlaps split along the "middle".

Example (from repo root)::

  mise exec -- python wesola/maps/helpers/area_regroup.py preview \\
    wesola/maps/wesola_obszared.svg -o wesola/maps/wesola_areas_preview.svg
  mise exec -- python wesola/maps/helpers/area_regroup.py build \\
    wesola/maps/wesola_obszared.svg -o wesola/maps/wesola_layered.svg

Segments are numbered 1..N without gaps: areas in guide order, then extras
top-to-bottom. Cut fragments get ids ``piece-N-network`` / ``piece-N-pathX``;
whole paths keep their source ids.
"""

from __future__ import annotations

import argparse
import colorsys
import copy
import math
import pickle
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
import svgelements as se
from lxml import etree
from shapely.geometry import LineString, Polygon, box
from shapely.strtree import STRtree

SVG_NS = 'http://www.w3.org/2000/svg'
INK_NS = 'http://www.inkscape.org/namespaces/inkscape'
SODI_NS = 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
SVG = '{%s}' % SVG_NS
INK_LABEL = '{%s}label' % INK_NS
INK_MODE = '{%s}groupmode' % INK_NS

GUIDE_GROUP = 'g644'
NETWORK_LAYERS = ('layer-network-roads', 'layer-network-trains')
NETWORK_SRC_LAYER = 'layer-network-roads'

# Assignment thresholds (fraction of a shape's own area inside an area).
F_MAJORITY = 0.5
F_UNDRAWN = 0.35
F_UNDRAWN_RIVAL = 0.15
F_SPLIT = 0.25
F_BORDERLINE = 0.2

# Network cut filters.
NET_MIN_PIECE = 15.0
NET_GRAZE_CUT_FRAC = 0.4
NET_RIM_DEPTH = 0.25
NET_RIM_CUT_FRAC = 0.15
NET_ABSORB_MAX = 900.0

# Road / rail areas: keep every in-guide fragment (no graze filter) and grow the
# cut along the mesh (geodesic px) until another segment or the limit is hit.
NET_GROW = {
    'path595': 450, 'path629': 450, 'path630': 450,
    'path633': 450, 'path635': 450,
    'path604': 30,
}
NO_GRAZE_FILTER = {'path595', 'path629', 'path630', 'path633', 'path635'}
# Growth stays inside a corridor: the area widened by GROW_PAD plus straight
# extensions from both guide tips along the guide axis (keeps out of side streets).
GROW_PAD = 12.0
GROW_TIPS = {'path595', 'path629', 'path630', 'path633', 'path635'}
TIP_MIN_HALF_WIDTH = 15.0

# Areas whose guide is drawn too tight: pool shapes within this many px count.
CLAIM_RADIUS = {'path604': 35}
CLAIM_MIN_FRAC = 0.6

# Unassigned shapes below this area are flecks (absorbed into nearest segment).
FLECK_MAX = 300.0

# Review overrides, applied after numbering (numbers stay as in the preview).
# Dropped segments give their mesh to the geodesically nearest road segment.
ROAD_AREAS = {'path595', 'path599', 'path615', 'path624', 'path629', 'path630',
              'path632', 'path633', 'path635', 'path638', 'path641'}
DROP_AREAS = {'path631'}
DROP_EXTRAS_AT = [  # a point inside each dropped extra segment
    (1905, 594), (1929, 588), (1132, 776), (1774, 957), (1811, 854),
    (1889, 1068), (1337, 2133), (1353, 2614), (1854, 2485), (1889, 2478),
]
# Roundabout centres: keep only mesh inside the island (hull of its white hole).
ISLAND_ONLY = {'path623'}
# (point inside extra, area id, px): the extra takes the area's non-mesh shapes nearby.
MOVE_TO_EXTRA = [((1899, 1695), 'path632', 40.0)]


# --------------------------------------------------------------------------- geometry

def flatten_subpath(sp: se.Path, step: float = 1.0) -> np.ndarray:
    pts = []
    for seg in sp:
        if isinstance(seg, se.Move):
            pts.append((seg.end.x, seg.end.y))
            continue
        if isinstance(seg, (se.Line, se.Close)):
            if seg.end is not None:
                pts.append((seg.end.x, seg.end.y))
            continue
        if isinstance(seg, se.CubicBezier):
            ctrl = [seg.start, seg.control1, seg.control2, seg.end]
        elif isinstance(seg, se.QuadraticBezier):
            ctrl = [seg.start, seg.control, seg.end]
        else:
            ctrl = [seg.start, seg.end]
        length = sum(math.dist((a.x, a.y), (b.x, b.y)) for a, b in zip(ctrl, ctrl[1:]))
        n = max(2, int(math.ceil(length / step)))
        pts.extend(map(tuple, seg.npoint(np.linspace(0, 1, n + 1)[1:])))
    return np.asarray(pts, dtype=float)


def polygonal(g):
    """Keep only polygonal parts of a geometry."""
    if g.is_empty:
        return g
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    parts = [p for p in getattr(g, 'geoms', []) if p.geom_type in ('Polygon', 'MultiPolygon')]
    return shapely.union_all(parts) if parts else Polygon()


def ring_polys(subpaths):
    out = []
    for sp in subpaths:
        pts = flatten_subpath(sp)
        if len(pts) < 3:
            out.append(None)
            continue
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = polygonal(shapely.make_valid(poly))
        out.append(None if poly.is_empty or poly.area < 1e-6 else poly)
    return out


def evenodd_components(polys):
    """Nesting depth → [(shell_idx, [hole_idx...])] for even-depth rings."""
    idx = [i for i, p in enumerate(polys) if p is not None]
    if not idx:
        return []
    tree = STRtree([polys[i] for i in idx])
    parent = {}
    for i in idx:
        best = None
        for c in tree.query(polys[i].representative_point(), predicate='within'):
            j = idx[c]
            if j != i and polys[j].area > polys[i].area and (best is None or polys[j].area < polys[best].area):
                best = j
        parent[i] = best
    depth: dict[int, int] = {}

    def dep(i):
        if i not in depth:
            depth[i] = 0 if parent[i] is None else dep(parent[i]) + 1
        return depth[i]

    return [(i, [j for j in idx if parent[j] == i]) for i in idx if dep(i) % 2 == 0]


@dataclass
class Shape:
    """One source path (absolute coordinates)."""
    id: str
    layer: str
    geom: object                     # shapely (evenodd fill area)
    subpaths_d: list[str]            # absolute d per subpath, curves kept
    bounds: tuple = ()


def absolute_path(el) -> se.Path:
    sp = se.Path(el.get('d'), transform=el.get('transform', ''))
    sp.reify()
    return sp


def load_svg(path: Path):
    tree = etree.parse(str(path))
    root = tree.getroot()
    guides: dict[str, object] = {}
    guide_lines: dict[str, LineString] = {}
    shapes: list[Shape] = []
    for g in root.iter(SVG + 'g'):
        gid = g.get('id') or ''
        if gid == GUIDE_GROUP:
            for p in g.iter(SVG + 'path'):
                sp = absolute_path(p)
                polys = [q for q in ring_polys([se.Path(s) for s in sp.as_subpaths()]) if q is not None]
                geom = polygonal(shapely.make_valid(shapely.union_all(polys))) if polys else Polygon()
                if geom.is_empty or geom.area < 1:
                    pts = [(seg.end.x, seg.end.y) for seg in sp if getattr(seg, 'end', None) is not None]
                    guide_lines[p.get('id')] = LineString(pts)
                guides[p.get('id')] = geom
            continue
        if not (gid == 'layer-small' or gid == NETWORK_SRC_LAYER or gid.startswith('layer-piece-')):
            continue
        for p in g.findall(SVG + 'path'):
            sp = absolute_path(p)
            subs = [se.Path(s) for s in sp.as_subpaths()]
            polys = ring_polys(subs)
            parts = []
            for shell, holes in evenodd_components(polys):
                geom = polys[shell]
                for h in holes:
                    geom = geom.difference(polys[h])
                parts.append(geom)
            geom = polygonal(shapely.make_valid(shapely.union_all(parts))) if parts else Polygon()
            bb = sp.bbox() or (0, 0, 0, 0)
            shapes.append(Shape(p.get('id'), gid, geom, [s.d() for s in subs], tuple(bb)))
    return tree, guides, guide_lines, shapes


# --------------------------------------------------------------------------- guide partition

def inscribed_radius(g) -> float:
    return max(1.0, shapely.maximum_inscribed_circle(g, 0.5).length)


def resolve_partition(guides, guide_lines):
    """Disjoint regions R_k from overlapping guides (normalised-depth winner)."""
    ids = [k for k, g in guides.items() if not g.is_empty]
    radius = {k: inscribed_radius(guides[k]) for k in ids}
    tree = STRtree([guides[k] for k in ids])
    overlaps = []
    for a_i, a in enumerate(ids):
        for b_i in tree.query(guides[a], predicate='intersects'):
            if b_i <= a_i:
                continue
            o = polygonal(guides[a].intersection(guides[ids[b_i]]))
            if o.area > 0.01:
                overlaps.append(o)
    regions = {k: guides[k] for k in ids}
    conflicts = []
    if overlaps:
        zone = shapely.union_all(overlaps).buffer(1.0)
        x0, y0, x1, y1 = zone.bounds
        xs, ys = np.meshgrid(np.arange(math.floor(x0), math.ceil(x1)) + 0.5,
                             np.arange(math.floor(y0), math.ceil(y1)) + 0.5)
        xs, ys = xs.ravel(), ys.ravel()
        inside = shapely.contains_xy(zone, xs, ys)
        xs, ys = xs[inside], ys[inside]
        pts = shapely.points(xs, ys)
        score = np.full((len(ids), len(xs)), -np.inf)
        for i, k in enumerate(ids):
            g = guides[k]
            gx0, gy0, gx1, gy1 = g.bounds
            near = (xs >= gx0 - 1) & (xs <= gx1 + 1) & (ys >= gy0 - 1) & (ys <= gy1 + 1)
            if not near.any():
                continue
            sel = np.where(near)[0]
            inn = shapely.contains_xy(g, xs[sel], ys[sel])
            sel = sel[inn]
            if len(sel):
                score[i, sel] = shapely.distance(pts[sel], g.boundary) / radius[k]
        covered = np.isfinite(score).sum(axis=0)
        multi = covered >= 2
        winner = np.argmax(score, axis=0)
        cells = {}
        for i, k in enumerate(ids):
            m = multi & (winner == i)
            if m.any():
                sq = shapely.box(xs[m] - 0.5, ys[m] - 0.5, xs[m] + 0.5, ys[m] + 0.5)
                cells[k] = shapely.coverage_union_all(sq)
        for k in ids:
            lose = [shapely.intersection(cells[j], guides[j]) for j in cells if j != k
                    and guides[j].intersects(guides[k])]
            if lose:
                regions[k] = polygonal(guides[k].difference(shapely.union_all(lose)))
        # make strictly disjoint (rare 3-way leftovers)
        taken = Polygon()
        for k in sorted(ids, key=lambda k: guides[k].area):
            r = polygonal(regions[k].difference(taken))
            if abs(r.area - regions[k].area) > 1:
                conflicts.append(f'{k}: {regions[k].area - r.area:.0f}px² multi-overlap trimmed')
            regions[k] = r
            taken = taken.union(r)
    # zero-area guides that are lines: treat as divider of the area they cross
    dividers = {}
    for k, line in guide_lines.items():
        host = max(ids, key=lambda j: regions[j].intersection(line).length)
        if regions[host].intersection(line).length <= 0:
            continue
        (ax, ay), (bx, by) = line.coords[0], line.coords[-1]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy)
        dx, dy = dx / n * 5000, dy / n * 5000
        long = LineString([(ax - dx, ay - dy), (bx + dx, by + dy)])
        cutter = long.buffer(0.01, cap_style='flat')
        halves = list(polygonal(regions[host].difference(cutter)).geoms) \
            if polygonal(regions[host].difference(cutter)).geom_type == 'MultiPolygon' else [regions[host]]
        # side of each piece relative to the line (cross product sign)
        side = defaultdict(list)
        for h in halves:
            c = h.centroid
            s = (bx - ax) * (c.y - ay) - (by - ay) * (c.x - ax)
            side[s > 0].append(h)
        if len(side) == 2:
            a_half = shapely.union_all(side[True])
            b_half = shapely.union_all(side[False])
            # divider gets the half west of the line (smaller mean x)
            if a_half.centroid.x < b_half.centroid.x:
                regions[k], regions[host] = a_half, b_half
            else:
                regions[k], regions[host] = b_half, a_half
            dividers[k] = host
    return regions, radius, dividers, conflicts


# --------------------------------------------------------------------------- assignment

@dataclass
class Piece:
    """A fragment of geometry destined for a segment."""
    shape_id: str
    geom: object
    kind: str            # whole | split | cut | absorbed
    whole: bool = True   # True → emit original path data


@dataclass
class Plan:
    area_pieces: dict = field(default_factory=lambda: defaultdict(list))   # guide id → [Piece]
    pool: list = field(default_factory=list)                               # unassigned Pieces
    flags: list = field(default_factory=list)                              # (shape_id, geom, reason)
    log: dict = field(default_factory=lambda: defaultdict(list))


def assign_shapes(shapes, regions, plan: Plan):
    ids = list(regions)
    rtree = STRtree([regions[k] for k in ids])
    for s in shapes:
        if s.layer == NETWORK_SRC_LAYER:
            continue
        if s.geom.is_empty or s.geom.area < 0.5:
            # degenerate (invisible) path: follow the region of its bbox centre
            cx, cy = (s.bounds[0] + s.bounds[2]) / 2, (s.bounds[1] + s.bounds[3]) / 2
            hit = [ids[i] for i in rtree.query(shapely.Point(cx, cy), predicate='within')]
            p = Piece(s.id, shapely.Point(cx, cy).buffer(0.5), 'degenerate')
            (plan.area_pieces[hit[0]] if hit else plan.pool).append(p)
            continue
        A = s.geom.area
        fr = []
        for i in rtree.query(s.geom, predicate='intersects'):
            k = ids[i]
            a = s.geom.intersection(regions[k]).area
            if a > 0:
                fr.append((a / A, k))
        fr.sort(reverse=True)
        f1, k1 = fr[0] if fr else (0.0, None)
        f2 = fr[1][0] if len(fr) > 1 else 0.0
        if f1 >= F_MAJORITY:
            plan.area_pieces[k1].append(Piece(s.id, s.geom, 'whole'))
            if f2 >= F_BORDERLINE:
                plan.log['majority_with_rival'].append((s.id, k1, round(f1, 2), fr[1][1], round(f2, 2)))
        elif f1 >= F_UNDRAWN and f2 < F_UNDRAWN_RIVAL:
            plan.area_pieces[k1].append(Piece(s.id, s.geom, 'whole'))
            plan.log['undrawn'].append((s.id, k1, round(f1, 2)))
        elif f2 >= F_SPLIT:
            parts = [(f, k) for f, k in fr if f >= F_BORDERLINE]
            rest = s.geom
            got = {}
            for f, k in parts:
                got[k] = polygonal(s.geom.intersection(regions[k]))
                rest = rest.difference(regions[k])
            rest = polygonal(rest)
            for r in getattr(rest, 'geoms', [rest]) if not rest.is_empty else []:
                k = min(got, key=lambda k: got[k].distance(r))
                got[k] = got[k].union(r)
            for k, g in got.items():
                plan.area_pieces[k].append(Piece(s.id, g, 'split', whole=False))
            plan.log['split'].append((s.id, [(k, round(f, 2)) for f, k in parts]))
        else:
            claimed = None
            for k, rad in CLAIM_RADIUS.items():
                zone = regions[k].buffer(rad)
                others = [regions[j] for j in ids if j != k and regions[j].intersects(s.geom)]
                if s.geom.intersection(zone).area / A >= CLAIM_MIN_FRAC and \
                        all(s.geom.intersection(o).area / A < F_BORDERLINE for o in others):
                    claimed = k
                    break
            if claimed:
                plan.area_pieces[claimed].append(Piece(s.id, s.geom, 'whole'))
                plan.log['claimed'].append((s.id, claimed, round(f1, 2)))
                continue
            plan.pool.append(Piece(s.id, s.geom, 'whole'))
            if f1 >= F_BORDERLINE:
                plan.flags.append((s.id, s.geom, f'borderline {k1} {f1:.2f}'))
                plan.log['borderline_rejected'].append((s.id, k1, round(f1, 2)))
            elif f1 > 0:
                plan.log['graze'].append((s.id, k1, round(f1, 3)))


def explode(g):
    g = polygonal(g)
    if g.is_empty:
        return []
    return list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]


def cut_network(net, regions, radius, plan: Plan):
    """Cut the mesh by each area region; drop rim grazes outside road areas."""
    kept = {}
    for k, R in regions.items():
        if R.is_empty or not net.intersects(R):
            continue
        rb = R.boundary.buffer(0.3)
        keep, graze_area = [], 0.0
        for P in explode(net.intersection(R)):
            if P.area < NET_MIN_PIECE:
                graze_area += P.area
                continue
            if k not in NO_GRAZE_FILTER:
                per = P.boundary.length
                cut_frac = P.boundary.intersection(rb).length / per if per else 1
                coords = shapely.get_coordinates(P)
                depth = float(shapely.distance(shapely.points(coords), R.boundary).max()) / radius.get(k, 1)
                if cut_frac >= NET_GRAZE_CUT_FRAC or (depth < NET_RIM_DEPTH and cut_frac >= NET_RIM_CUT_FRAC):
                    graze_area += P.area
                    continue
            keep.append(P)
        if keep:
            kept[k] = shapely.union_all(keep)
        if graze_area >= 1:
            plan.log['net_graze'].append((k, round(graze_area)))
    taken = shapely.union_all(list(kept.values())) if kept else Polygon()
    return kept, polygonal(net.difference(taken))


def rasterize(geom, origin, size):
    from PIL import Image, ImageDraw
    ox, oy = origin
    img = Image.new('L', size, 0)
    dr = ImageDraw.Draw(img)
    for poly in sorted(explode(geom), key=lambda p: -p.area):
        dr.polygon([(x - ox, y - oy) for x, y in poly.exterior.coords], fill=1)
        for ring in poly.interiors:
            dr.polygon([(x - ox, y - oy) for x, y in ring.coords], fill=0)
    return np.array(img) > 0


def mask_to_geom(m, ox, oy):
    d = np.diff(np.pad(m, ((0, 0), (1, 1))).astype(np.int8), axis=1)
    rows, starts = np.where(d == 1)
    _, ends = np.where(d == -1)
    if not len(rows):
        return Polygon()
    boxes = shapely.box(ox + starts, oy + rows, ox + ends, oy + rows + 1)
    return shapely.coverage_union_all(boxes)


def _shift(a, dy, dx):
    out = np.zeros_like(a)
    H, W = a.shape
    out[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)] = \
        a[max(-dy, 0):H + min(-dy, 0), max(-dx, 0):W + min(-dx, 0)]
    return out


def tip_extensions(G, radius, length):
    """Straight tubes continuing the guide beyond its two farthest-apart tips."""
    hull = shapely.get_coordinates(G.convex_hull.exterior)
    d = np.linalg.norm(hull[:, None, :] - hull[None, :, :], axis=2)
    i, j = np.unravel_index(np.argmax(d), d.shape)
    diam = d[i, j]
    half_w = max(TIP_MIN_HALF_WIDTH, radius * 1.2)
    tubes = []
    for tip in (hull[i], hull[j]):
        near = G.intersection(shapely.Point(tip).buffer(min(150.0, diam / 3)))
        if near.is_empty:
            continue
        c = np.array(near.centroid.coords[0])
        v = tip - c
        n = np.linalg.norm(v)
        if n < 1e-6:
            continue
        v /= n
        tubes.append(LineString([tip - v * radius, tip + v * length]).buffer(half_w, cap_style='flat'))
    return tubes


def grow_network(kept, residual, regions, radius, plan: Plan):
    """Geodesic growth of road cuts along the remaining mesh (8-connected px)."""
    growers = [k for k in NET_GROW if k in kept]
    if not growers or residual.is_empty:
        return kept, residual
    corridors = {}
    for k in growers:
        parts = [regions[k].buffer(GROW_PAD)]
        if k in GROW_TIPS:
            parts += tip_extensions(regions[k], radius[k], NET_GROW[k])
        corridors[k] = shapely.union_all(parts)
    x0, y0, x1, y1 = shapely.union_all(list(corridors.values())).bounds
    ox, oy = math.floor(x0) - 2, math.floor(y0) - 2
    W, H = math.ceil(x1) - ox + 3, math.ceil(y1) - oy + 3
    mask = rasterize(residual, (ox, oy), (W, H))
    lab = np.zeros((H, W), np.int16)
    allowed = np.zeros((H, W), np.uint16)
    for i, k in enumerate(growers, 1):
        lab[rasterize(kept[k], (ox, oy), (W, H)) & (lab == 0)] = i
        allowed |= (rasterize(corridors[k], (ox, oy), (W, H)).astype(np.uint16) << (i - 1))
    limits = np.array([0] + [NET_GROW[k] for k in growers])
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    for step in range(1, int(limits.max()) + 1):
        act = np.where(limits[lab] >= step, lab, 0)
        changed = False
        for dy, dx in dirs:
            sh = _shift(act, dy, dx)
            take = (sh > 0) & mask & (lab == 0)
            take &= ((allowed >> np.maximum(sh - 1, 0).astype(np.uint16)) & 1).astype(bool)
            if take.any():
                lab[take] = sh[take]
                changed = True
        if not changed:
            break
    grown_all = []
    for i, k in enumerate(growers, 1):
        g = mask_to_geom((lab == i) & mask, ox, oy)
        if g.is_empty:
            continue
        g = polygonal(g.intersection(residual))
        kept[k] = kept[k].union(g)
        grown_all.append(g)
        plan.log['net_grown'].append((k, round(g.area)))
    if grown_all:
        residual = polygonal(residual.difference(shapely.union_all(grown_all)))
    return kept, residual


def absorb_residual(kept, residual, plan: Plan):
    """Small mesh leftovers touching a cut go to the cut with the most contact."""
    keys = list(kept)
    tree = STRtree([kept[k] for k in keys])
    add = defaultdict(list)
    rest = []
    for r in explode(residual):
        if r.area <= NET_ABSORB_MAX:
            touch = [(r.buffer(0.6).intersection(kept[keys[i]]).area, keys[i])
                     for i in tree.query(r, predicate='dwithin', distance=0.6)]
            if touch:
                k = max(touch)[1]
                add[k].append(r)
                plan.log['net_absorbed'].append((k, round(r.area)))
                continue
        rest.append(r)
    for k, parts in add.items():
        kept[k] = kept[k].union(shapely.union_all(parts))
    return kept, rest


# --------------------------------------------------------------------------- segments

@dataclass
class Segment:
    num: int
    guide: str | None            # guide id, or None for extras
    pieces: list

    @property
    def label(self):
        return f'piece-{self.num}'


def guide_num(k: str) -> int:
    return int(''.join(ch for ch in k if ch.isdigit()))


def build_segments(regions, plan: Plan, kept, residual_rest, net_id):
    area_ids = sorted(regions, key=guide_num)
    segs = []
    for n, k in enumerate(area_ids, 1):
        pieces = list(plan.area_pieces.get(k, []))
        if k in kept and not kept[k].is_empty:
            pieces.append(Piece(net_id, kept[k], 'cut', whole=False))
        segs.append(Segment(n, k, pieces))
    objects, flecks = [], []
    for p in plan.pool:
        (objects if p.geom.area >= FLECK_MAX else flecks).append(p)
    for r in residual_rest:
        (objects if r.area >= FLECK_MAX else flecks).append(Piece(net_id, r, 'net-extra', whole=False))
    # overlapping / touching objects form one extra segment
    parent = list(range(len(objects)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tree = STRtree([o.geom for o in objects])
    for i, o in enumerate(objects):
        for j in tree.query(o.geom, predicate='dwithin', distance=0.5):
            if j != i:
                parent[find(i)] = find(int(j))
    groups = defaultdict(list)
    for i, o in enumerate(objects):
        groups[find(i)].append(o)

    def order(g):
        c = shapely.union_all([p.geom for p in g]).centroid
        return (round(c.y / 150), c.x)

    n = len(segs)
    for g in sorted(groups.values(), key=order):
        n += 1
        segs.append(Segment(n, None, g))
    # flecks → nearest segment
    owners, geoms = [], []
    for si, s in enumerate(segs):
        for p in s.pieces:
            owners.append(si)
            geoms.append(p.geom)
    tree = STRtree(geoms)
    for f in flecks:
        si = owners[int(tree.query_nearest(f.geom)[0])]
        f.kind = 'fleck' if f.kind != 'net-extra' else 'net-fleck'
        segs[si].pieces.append(f)
        plan.log['fleck'].append((f.shape_id, segs[si].label))
    # merge mesh fragments per segment into one path
    for s in segs:
        net_parts = [p for p in s.pieces if p.shape_id == net_id and not p.whole]
        if len(net_parts) > 1:
            other = [p for p in s.pieces if p not in net_parts]
            s.pieces = other + [Piece(net_id, shapely.union_all([p.geom for p in net_parts]), 'cut', whole=False)]
    return segs


def seg_geom(s: Segment):
    return shapely.union_all([p.geom for p in s.pieces]) if s.pieces else Polygon()


def mesh_piece(s: Segment, net_id):
    return next((p for p in s.pieces if p.shape_id == net_id and not p.whole), None)


def is_road(s: Segment, net_id):
    if s.guide:
        return s.guide in ROAD_AREAS
    return bool(s.pieces) and all(p.shape_id == net_id for p in s.pieces)


def add_mesh(s: Segment, g, net_id):
    p = mesh_piece(s, net_id)
    if p is None:
        s.pieces.append(Piece(net_id, g, 'cut', whole=False))
    else:
        p.geom = polygonal(p.geom.union(g))


def redistribute_to_roads(freed, segs, net_id, plan: Plan):
    """Give freed mesh to adjacent road segments by geodesic nearest (8-connected px)."""
    roads = [s for s in segs if is_road(s, net_id) and mesh_piece(s, net_id) is not None]
    allfreed = shapely.union_all(freed)
    for group in explode(allfreed.buffer(1.0)):
        comp = polygonal(allfreed.intersection(group))
        x0, y0, x1, y1 = comp.bounds
        ox, oy = math.floor(x0) - 4, math.floor(y0) - 4
        W, H = math.ceil(x1) - ox + 5, math.ceil(y1) - oy + 5
        frame = box(ox, oy, ox + W, oy + H)
        mask = rasterize(comp.buffer(0.7), (ox, oy), (W, H))
        near = [s for s in roads if mesh_piece(s, net_id).geom.intersects(frame)]
        lab = np.zeros((H, W), np.int16)
        for i, s in enumerate(near, 1):
            seed = rasterize(mesh_piece(s, net_id).geom.intersection(frame), (ox, oy), (W, H))
            lab[seed & ~mask & (lab == 0)] = i
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
        while True:
            act = lab.copy()
            changed = False
            for dy, dx in dirs:
                sh = _shift(act, dy, dx)
                take = (sh > 0) & mask & (lab == 0)
                if take.any():
                    lab[take] = sh[take]
                    changed = True
            if not changed:
                break
        given = []
        for i, s in enumerate(near, 1):
            g = mask_to_geom((lab == i) & mask, ox, oy)
            if g.is_empty:
                continue
            g = polygonal(g.intersection(comp))
            add_mesh(s, g, net_id)
            given.append(g)
            plan.log['redistributed'].append((s.label, round(g.area)))
        rest = polygonal(comp.difference(shapely.union_all(given))) if given else comp
        for r in explode(rest):
            if r.area < 0.01:
                continue
            target = min(roads, key=lambda s: mesh_piece(s, net_id).geom.distance(r))
            add_mesh(target, r, net_id)


def apply_overrides(segs, regions, net_geom, net_id, plan: Plan):
    freed, loose = [], []

    def drop(s, why):
        for p in s.pieces:
            (freed if p.shape_id == net_id and not p.whole else loose).append(p)
        s.pieces = []
        plan.log['dropped'].append((s.label, why))

    for s in segs:
        if s.guide in DROP_AREAS:
            drop(s, f'area {guide_num(s.guide)}')
    for x, y in DROP_EXTRAS_AT:
        pt = shapely.Point(x, y)
        cands = [s for s in segs if not s.guide and s.pieces]
        s = min(cands, key=lambda s: seg_geom(s).distance(pt))
        if seg_geom(s).distance(pt) < 3:
            drop(s, f'extra at {x},{y}')
        else:
            plan.log['drop_miss'].append((x, y))
    for s in segs:
        if s.guide not in ISLAND_ONLY:
            continue
        p = mesh_piece(s, net_id)
        if p is None:
            continue
        R = regions[s.guide]
        holes = [Polygon(r) for poly in explode(net_geom) for r in poly.interiors]
        holes = [h for h in holes if h.intersects(R)]
        if not holes:
            continue
        island = max(holes, key=lambda h: h.intersection(R).area).convex_hull.buffer(1.5)
        outside = polygonal(p.geom.difference(island))
        p.geom = polygonal(p.geom.intersection(island))
        if not outside.is_empty:
            freed.append(Piece(net_id, outside, 'cut', whole=False))
            plan.log['island_trim'].append((s.label, round(outside.area)))
    for (x, y), area_id, dist in MOVE_TO_EXTRA:
        pt = shapely.Point(x, y)
        extra = min((s for s in segs if not s.guide and s.pieces), key=lambda s: seg_geom(s).distance(pt))
        src = next(s for s in segs if s.guide == area_id)
        eg = seg_geom(extra)
        move = [p for p in src.pieces if p.shape_id != net_id and p.geom.distance(eg) <= dist]
        src.pieces = [p for p in src.pieces if p not in move]
        extra.pieces += move
        plan.log['moved'].append((src.label, extra.label, [p.shape_id for p in move]))
    if freed:
        redistribute_to_roads([p.geom for p in freed], segs, net_id, plan)
    if loose:
        live = [s for s in segs if s.pieces]
        for p in loose:
            min(live, key=lambda s: seg_geom(s).distance(p.geom)).pieces.append(p)
    segs = [s for s in segs if s.pieces]
    for n, s in enumerate(segs, 1):
        s.num = n
    return segs


# --------------------------------------------------------------------------- SVG output

def geom_d(g, nd=2):
    fmt = f'{{:.{nd}f}}'
    out = []
    for poly in explode(g):
        for ring in [poly.exterior, *poly.interiors]:
            c = ring.coords[:-1]
            if len(c) < 3:
                continue
            out.append('M' + ' '.join(fmt.format(x) + ',' + fmt.format(y) for x, y in c) + 'Z')
    return ''.join(out)


def strip_insensitive(el):
    el.attrib.pop('{%s}insensitive' % SODI_NS, None)


def piece_elements(seg: Segment, p: Piece, src_els, color=None):
    if p.whole and p.shape_id in src_els:
        el = copy.deepcopy(src_els[p.shape_id])
        strip_insensitive(el)
        if color:
            el.set('fill', color)
        return [el]
    base = src_els.get(p.shape_id)
    el = etree.Element(SVG + 'path')
    if base is not None:
        for k, v in base.attrib.items():
            if k not in ('d', 'transform', 'id') and 'insensitive' not in k:
                el.set(k, v)
    is_mesh = p.kind in ('cut', 'net-extra', 'net-fleck')
    el.set('id', f'{seg.label}-network' if is_mesh else f'{seg.label}-{p.shape_id}')
    el.set('d', geom_d(p.geom))
    el.set('fill', color or (base.get('fill') if base is not None else '#000000') or '#000000')
    el.set('fill-rule', 'evenodd')
    return [el]


def make_layer(seg: Segment):
    g = etree.Element(SVG + 'g')
    g.set('id', f'layer-{seg.label}')
    g.set(INK_MODE, 'layer')
    g.set(INK_LABEL, seg.label)
    return g


def source_elements(root):
    return {p.get('id'): p for p in root.iter(SVG + 'path')}


def strip_geometry_layers(root):
    """Remove guide + old geometry layers; return insertion index."""
    idx = None
    for c in list(root):
        if not isinstance(c.tag, str) or etree.QName(c).localname != 'g':
            continue
        gid = c.get('id') or ''
        if gid == GUIDE_GROUP or gid == 'layer-small' or gid in NETWORK_LAYERS or gid.startswith('layer-piece-'):
            if idx is None:
                idx = list(root).index(c)
            root.remove(c)
    return idx if idx is not None else len(root)


def area_color(i):
    h = (i * 0.618034) % 1
    s = (0.95, 0.7)[i % 2]
    v = (0.9, 0.7, 1.0)[i % 3]
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'


def extra_color(i):
    v = (0.30, 0.48, 0.62, 0.40, 0.55)[i % 5]
    r, g, b = colorsys.hsv_to_rgb((0.6, 0.1, 0.33)[i % 3], 0.12, v)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'


def text_el(x, y, txt, size, fill):
    t = etree.Element(SVG + 'text', x=f'{x:.1f}', y=f'{y:.1f}')
    t.set('style', f'font-size:{size}px;font-family:sans-serif;font-weight:bold;fill:{fill};'
                   'stroke:#ffffff;stroke-width:4;paint-order:stroke;text-anchor:middle')
    t.text = txt
    return t


def write_preview(tree, guides_raw, regions, segs, plan: Plan, out: Path):
    root = copy.deepcopy(tree.getroot())
    src_els = source_elements(tree.getroot())
    idx = strip_geometry_layers(root)
    for c in list(root):
        if isinstance(c.tag, str) and (c.get('id') or '') == 'layer-guide-rail-band':
            root.remove(c)
    bg = etree.Element(SVG + 'rect', x='0', y='0', width='2048', height='2732', fill='#ffffff', id='preview-bg')
    root.insert(idx, bg)
    idx += 1
    labels = etree.Element(SVG + 'g', id='preview-labels')
    labels.set(INK_MODE, 'layer')
    labels.set(INK_LABEL, 'preview-labels')
    for s in segs:
        col = area_color(s.num - 1) if s.guide else extra_color(s.num)
        layer = make_layer(s)
        for p in s.pieces:
            for el in piece_elements(s, p, src_els, col):
                layer.append(el)
        root.insert(idx, layer)
        idx += 1
        if s.guide:
            reg = regions[s.guide]
            pt = reg.representative_point() if not reg.is_empty else shapely.Point(0, 0)
            labels.append(text_el(pt.x, pt.y, f'{s.num}·{guide_num(s.guide)}', 22, '#000000'))
        else:
            pt = shapely.union_all([p.geom for p in s.pieces if p.kind not in ('fleck', 'net-fleck')]).representative_point()
            labels.append(text_el(pt.x, pt.y + 6, f'X{s.num}', 18, '#333333'))
    outl = etree.Element(SVG + 'g', id='preview-guides')
    outl.set(INK_MODE, 'layer')
    outl.set(INK_LABEL, 'obszary (outline)')
    for s in segs:
        if not s.guide or regions[s.guide].is_empty:
            continue
        col = area_color(s.num - 1)
        el = etree.SubElement(outl, SVG + 'path', id=f'outline-{guide_num(s.guide)}')
        el.set('d', geom_d(regions[s.guide], 1))
        el.set('style', f'fill:{col};fill-opacity:0.10;stroke:{col};'
                        'stroke-width:1.5;stroke-dasharray:5,3')
    flags = etree.Element(SVG + 'g', id='preview-conflicts')
    flags.set(INK_MODE, 'layer')
    flags.set(INK_LABEL, 'conflicts (magenta)')
    for sid, g, why in plan.flags:
        el = etree.SubElement(flags, SVG + 'path', id=f'flag-{sid}')
        el.set('d', geom_d(g.buffer(3), 1))
        el.set('style', 'fill:none;stroke:#ff00ff;stroke-width:3')
        el.set(INK_LABEL, why)
    root.append(outl)
    root.append(flags)
    root.append(labels)
    etree.ElementTree(root).write(str(out), encoding='utf-8', xml_declaration=True)


def write_build(tree, segs, out: Path):
    root = copy.deepcopy(tree.getroot())
    src_els = source_elements(tree.getroot())
    idx = strip_geometry_layers(root)
    # leftovers of the old Y-band network split
    for el in list(root.iter()):
        if isinstance(el.tag, str) and el.get('id') in ('layer-guide-rail-band', 'clip-network-roads',
                                                         'clip-network-trains'):
            el.getparent().remove(el)
    root.set('{%s}docname' % SODI_NS, out.name)
    for s in segs:
        layer = make_layer(s)
        for p in s.pieces:
            for el in piece_elements(s, p, src_els):
                layer.append(el)
        root.insert(idx, layer)
        idx += 1
    etree.ElementTree(root).write(str(out), encoding='utf-8', xml_declaration=True)


def report(segs, net_id):
    lines = []
    for s in segs:
        src = f'obszar {guide_num(s.guide)}' if s.guide else 'extra'
        n_paths = len(s.pieces)
        kinds = defaultdict(int)
        for p in s.pieces:
            kinds[p.kind] += 1
        extra = []
        if any(p.shape_id == net_id for p in s.pieces):
            extra.append('mesh-split')
        extra += [f'split:{p.shape_id}' for p in s.pieces if p.kind == 'split']
        lines.append(f'{s.label:>9}  {src:<10} paths={n_paths:<3} {dict(kinds)} {" ".join(extra)}')
    return '\n'.join(lines)


# --------------------------------------------------------------------------- CLI

def analyse(src: Path, cache: Path | None):
    if cache and cache.is_file():
        with open(cache, 'rb') as f:
            tree_bytes, guides, guide_lines, shapes = pickle.load(f)
        tree = etree.ElementTree(etree.fromstring(tree_bytes))
    else:
        tree, guides, guide_lines, shapes = load_svg(src)
        if cache:
            with open(cache, 'wb') as f:
                pickle.dump((etree.tostring(tree), guides, guide_lines, shapes), f)
    return tree, guides, guide_lines, shapes


def plan_segments(src: Path, cache: Path | None):
    tree, guides, guide_lines, shapes = analyse(src, cache)
    regions, radius, dividers, conflicts = resolve_partition(guides, guide_lines)
    plan = Plan()
    plan.log['dividers'] = [dividers]
    plan.log['overlap_trim'] = conflicts
    assign_shapes(shapes, regions, plan)
    net = next(s for s in shapes if s.layer == NETWORK_SRC_LAYER)
    kept, residual = cut_network(net.geom, regions, radius, plan)
    kept, residual = grow_network(kept, residual, regions, radius, plan)
    kept, rest = absorb_residual(kept, residual, plan)
    segs = build_segments(regions, plan, kept, rest, net.id)
    segs = apply_overrides(segs, regions, net.geom, net.id, plan)
    return tree, guides, regions, segs, plan, net.id


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('stage', choices=['preview', 'build'])
    p.add_argument('input', type=Path)
    p.add_argument('-o', '--output', type=Path, required=True)
    p.add_argument('--cache', type=Path, help='pickle cache of parsed geometry (speeds up iteration)')
    p.add_argument('--log', action='store_true', help='print heuristic decisions')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    tree, guides, regions, segs, plan, net_id = plan_segments(args.input, args.cache)
    if args.log:
        for key, v in plan.log.items():
            print(f'{key} ({len(v)}): {v}')
    if args.stage == 'preview':
        write_preview(tree, guides, regions, segs, plan, args.output)
    else:
        write_build(tree, segs, args.output)
    print(report(segs, net_id))
    n_area = sum(1 for s in segs if s.guide)
    print(f'segments: {len(segs)} ({n_area} areas + {len(segs) - n_area} extras)')
    print(f'wrote {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
