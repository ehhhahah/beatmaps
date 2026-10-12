#!/usr/bin/env python3
"""Split Wesoła road pieces along the Inkscape ``CUTS`` layer, then renumber.

The ``CUTS`` layer in ``wesola_layered-CUTS.svg`` holds powerstroke strokes whose
``inkscape:original-d`` marks where to sever. Each cut splits the road mesh with a
hairline slit (~0.05 px, same order as existing area seams) so neighbouring pieces
abut with an invisible join — not a thick gap.

Outputs:

* ``wesola_final_map.svg`` — live-style map (original fills, sequential ids)
* ``wesola_areas_preview.svg`` — coloured preview with labels ``1..N``

Example (from repo root)::

  mise exec -- python wesola/maps/helpers/apply_cuts.py \\
    wesola/maps/wesola_layered-CUTS.svg \\
    --final wesola/maps/wesola_final_map.svg \\
    --preview wesola/maps/wesola_areas_preview.svg
"""

from __future__ import annotations

import argparse
import colorsys
import copy
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
import svgelements as se
from lxml import etree
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

SVG_NS = 'http://www.w3.org/2000/svg'
INK_NS = 'http://www.inkscape.org/namespaces/inkscape'
SODI_NS = 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
SVG = '{%s}' % SVG_NS
INK_LABEL = '{%s}label' % INK_NS
INK_MODE = '{%s}groupmode' % INK_NS
INK_ORIG = '{%s}original-d' % INK_NS

CUTS_LABEL = 'CUTS'
MIN_PART_AREA = 200.0
# Hairline slit — matches near-invisible seams between existing abutting pieces.
HAIR = 0.05
PROBE = 12.0
HALF_MAX = 100.0


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
    if g.is_empty:
        return g
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    parts = [p for p in getattr(g, 'geoms', []) if p.geom_type in ('Polygon', 'MultiPolygon')]
    return shapely.union_all(parts) if parts else Polygon()


def explode(g, min_area: float = 0.0):
    if g is None or g.is_empty:
        return []
    parts = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
    return [p for p in parts if p.area >= min_area]


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
    from shapely.strtree import STRtree
    idx = [i for i, p in enumerate(polys) if p is not None]
    if not idx:
        return []
    tree = STRtree([polys[i] for i in idx])
    parent = {}
    for i in idx:
        best = None
        for c in tree.query(polys[i].representative_point(), predicate='within'):
            j = idx[c]
            if j != i and polys[j].area > polys[i].area and (
                    best is None or polys[j].area < polys[best].area):
                best = j
        parent[i] = best
    depth: dict[int, int] = {}

    def dep(i):
        if i not in depth:
            depth[i] = 0 if parent[i] is None else dep(parent[i]) + 1
        return depth[i]

    return [(i, [j for j in idx if parent[j] == i]) for i in idx if dep(i) % 2 == 0]


def path_geom(el) -> object:
    sp = se.Path(el.get('d'), transform=el.get('transform', ''))
    sp.reify()
    subs = [se.Path(s) for s in sp.as_subpaths()]
    polys = ring_polys(subs)
    parts = []
    for shell, holes in evenodd_components(polys):
        g = polys[shell]
        for h in holes:
            g = g.difference(polys[h])
        parts.append(g)
    return polygonal(shapely.make_valid(shapely.union_all(parts))) if parts else Polygon()


def line_from_d(d: str, step: float = 0.5) -> LineString:
    sp = se.Path(d)
    sp.reify()
    return LineString(flatten_subpath(sp, step))


def line_direction(line: LineString) -> np.ndarray:
    c = np.array(line.coords)
    v = c[-1] - c[0]
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def geom_d(g, nd: int = 2) -> str:
    fmt = f'{{:.{nd}f}}'
    out = []
    for poly in explode(g):
        for ring in [poly.exterior, *poly.interiors]:
            c = ring.coords[:-1]
            if len(c) < 3:
                continue
            out.append('M' + ' '.join(fmt.format(x) + ',' + fmt.format(y) for x, y in c) + 'Z')
    return ''.join(out)


# --------------------------------------------------------------------------- data

@dataclass
class Frag:
    """One drawable fragment (whole original path, or a cut piece of one)."""
    geom: object
    fill: str
    src_id: str
    whole_el: object | None = None  # keep original path when uncut
    cut: bool = False


@dataclass
class PieceGroup:
    """A prospective segment before final numbering."""
    origin: int                 # original piece number
    is_area: bool               # True if origin was a workshop area (1–49)
    frags: list[Frag] = field(default_factory=list)

    @property
    def geom(self):
        geoms = [f.geom for f in self.frags if not f.geom.is_empty]
        return unary_union(geoms) if geoms else Polygon()


# --------------------------------------------------------------------------- cuts

def load_cuts(root):
    """Return [(id, centreline, powerstroke_fill), ...]."""
    cuts_g = next((g for g in root.iter(SVG + 'g') if g.get(INK_LABEL) == CUTS_LABEL), None)
    if cuts_g is None:
        raise SystemExit(f'no layer labelled {CUTS_LABEL!r}')
    out = []
    for el in cuts_g:
        if not isinstance(el.tag, str) or etree.QName(el).localname != 'path':
            continue
        od = el.get(INK_ORIG) or el.get('d')
        if not od:
            continue
        out.append((el.get('id') or 'cut', line_from_d(od), path_geom(el)))
    return out


def load_pieces(root) -> list[PieceGroup]:
    pieces = []
    for g in root:
        if not isinstance(g.tag, str) or etree.QName(g).localname != 'g':
            continue
        gid = g.get('id') or ''
        if not gid.startswith('layer-piece-'):
            continue
        num = int(gid.split('-')[-1])
        frags = []
        for p in g.findall(SVG + 'path'):
            geom = path_geom(p)
            if geom.is_empty or geom.area < 0.5:
                continue
            frags.append(Frag(
                geom=geom,
                fill=p.get('fill') or '#000000',
                src_id=p.get('id') or f'path-{num}',
                whole_el=p,
                cut=False,
            ))
        pieces.append(PieceGroup(origin=num, is_area=(num <= 49), frags=frags))
    pieces.sort(key=lambda p: p.origin)
    return pieces


def absorb_scraps(parts: list, scraps: list) -> list:
    """Attach tiny leftovers to the nearest large part."""
    if not parts:
        return list(scraps)
    parts = list(parts)
    for s in scraps:
        i = min(range(len(parts)), key=lambda i: parts[i].distance(s))
        parts[i] = polygonal(unary_union([parts[i], s]))
    return parts


def cut_directions(line: LineString, corridor) -> list[np.ndarray]:
    """Candidate seam directions: stroke axis, its normal, corridor PCA major axis."""
    tang = line_direction(line)
    nrm = np.array([-tang[1], tang[0]])
    dirs = [tang, nrm]
    try:
        xs, ys = corridor.exterior.xy
        pts = np.column_stack([xs, ys])
        pts = pts - pts.mean(axis=0)
        _, _, vh = np.linalg.svd(pts, full_matrices=False)
        major = vh[0]
        if np.linalg.norm(major) > 1e-9:
            dirs.append(major / np.linalg.norm(major))
            dirs.append(np.array([-major[1], major[0]]))
    except Exception:
        pass
    # de-dupe near-parallel directions
    uniq = []
    for d in dirs:
        if any(abs(np.dot(d, u)) > 0.98 for u in uniq):
            continue
        uniq.append(d)
    return uniq


def sever_hairline(geom, line: LineString, fill) -> tuple[list | None, str]:
    """Split ``geom`` with a hairline slit at the CUT mark (minimal visible gap).

    The powerstroke centreline often sits beside the road; we snap the seam through
    the road∩cut corridor and try stroke / normal / PCA directions, using the
    shortest half-length that actually disconnects.
    """
    probe = unary_union([fill, line.buffer(PROBE)]) if fill is not None and not fill.is_empty \
        else line.buffer(PROBE)
    corridor = polygonal(geom.intersection(probe))
    if corridor.is_empty or corridor.area < 5:
        return None, 'no corridor'

    mid = np.array(corridor.representative_point().coords[0])
    if not geom.intersects(Point(*mid)):
        mid = np.array(geom.intersection(corridor).representative_point().coords[0])

    best = None  # (half, lost, parts, label)
    for direc in cut_directions(line, corridor):
        for half in np.linspace(6.0, HALF_MAX, 24):
            seg = LineString([tuple(mid - direc * half), tuple(mid + direc * half)])
            blade = seg.buffer(HAIR, cap_style='square')
            rest = polygonal(geom.difference(blade))
            big = explode(rest, MIN_PART_AREA)
            scraps = [p for p in explode(rest, 0.0) if p.area < MIN_PART_AREA]
            parts = absorb_scraps(big, scraps)
            if len(parts) < 2:
                continue
            lost = geom.area - sum(p.area for p in parts)
            gap = min(parts[i].distance(parts[j])
                      for i in range(len(parts)) for j in range(i + 1, len(parts)))
            cand = (float(half), lost, parts, f'half={half:.0f} lost={lost:.2f} gap={gap:.3f}')
            if best is None or cand[0] < best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                best = cand
            break  # shortest half for this direction
    if best is None:
        return None, 'no split'
    return best[2], best[3]


def apply_cuts(pieces: list[PieceGroup], cuts) -> list[PieceGroup]:
    """Split fragments hit by each cut; return expanded piece list (pre-renumber)."""
    log = []
    groups = [PieceGroup(p.origin, p.is_area, list(p.frags)) for p in pieces]

    for cid, line, fill in cuts:
        probe = unary_union([line.buffer(8.0), fill]) if fill is not None and not fill.is_empty \
            else line.buffer(8.0)
        best = None  # (inter_area, gi, fi)
        for gi, g in enumerate(groups):
            for fi, frag in enumerate(g.frags):
                if frag.geom.is_empty:
                    continue
                inter = frag.geom.intersection(probe)
                area = inter.area if not inter.is_empty else 0.0
                if area < 5:
                    continue
                if best is None or area > best[0]:
                    best = (area, gi, fi)
        if best is None:
            log.append(f'{cid}: no hit')
            continue
        area, gi, fi = best
        frag = groups[gi].frags[fi]
        parts, msg = sever_hairline(frag.geom, line, fill)
        if parts is None:
            log.append(f'{cid}: hit piece-{groups[gi].origin}/{frag.src_id} '
                       f'inter={area:.0f} — {msg}')
            continue
        new_frags = [
            Frag(geom=p, fill=frag.fill, src_id=f'{frag.src_id}-c{j}',
                 whole_el=None, cut=True)
            for j, p in enumerate(parts)
        ]
        groups[gi].frags = groups[gi].frags[:fi] + new_frags + groups[gi].frags[fi + 1:]
        log.append(
            f'{cid}: piece-{groups[gi].origin}/{frag.src_id} '
            f'inter={area:.0f} {msg} → {[round(p.area) for p in parts]}'
        )

    by_origin: dict[int, PieceGroup] = {}
    for g in groups:
        by_origin.setdefault(g.origin, PieceGroup(g.origin, g.is_area, [])).frags.extend(g.frags)
        by_origin[g.origin].is_area = g.is_area

    out: list[PieceGroup] = []
    for origin in sorted(by_origin):
        g = by_origin[origin]
        cut_frags = [f for f in g.frags if f.cut]
        keep_frags = [f for f in g.frags if not f.cut]
        if not cut_frags:
            out.append(g)
            continue
        buckets = [PieceGroup(origin, g.is_area, [f]) for f in cut_frags]
        for f in keep_frags:
            if f.geom.is_empty:
                continue
            bi = min(range(len(buckets)), key=lambda i: buckets[i].geom.distance(f.geom))
            buckets[bi].frags.append(f)
        buckets.sort(key=lambda b: (b.geom.bounds[1], b.geom.bounds[0]))
        out.extend(buckets)

    for line in log:
        print(line)
    return out


# --------------------------------------------------------------------------- SVG write

def area_color(i: int) -> str:
    h = (i * 0.618034) % 1
    s = (0.95, 0.7)[i % 2]
    v = (0.9, 0.7, 1.0)[i % 3]
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return f'#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}'


def extra_color(i: int) -> str:
    v = (0.30, 0.48, 0.62, 0.40, 0.55)[i % 5]
    r, g, b = colorsys.hsv_to_rgb((0.6, 0.1, 0.33)[i % 3], 0.12, v)
    return f'#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}'


def text_el(x, y, txt, size, fill):
    t = etree.Element(SVG + 'text', x=f'{x:.1f}', y=f'{y:.1f}')
    t.set('style', f'font-size:{size}px;font-family:sans-serif;font-weight:bold;fill:{fill};'
                   'stroke:#ffffff;stroke-width:4;paint-order:stroke;text-anchor:middle')
    t.text = txt
    return t


def frag_elements(label: str, frag: Frag, color: str | None):
    if frag.whole_el is not None and not frag.cut:
        el = copy.deepcopy(frag.whole_el)
        el.attrib.pop('{%s}insensitive' % SODI_NS, None)
        if color:
            el.set('fill', color)
        return [el]
    el = etree.Element(SVG + 'path')
    if frag.whole_el is not None:
        for k, v in frag.whole_el.attrib.items():
            if k not in ('d', 'transform', 'id') and 'insensitive' not in k:
                el.set(k, v)
    el.set('id', f'{label}-network' if frag.cut or 'network' in frag.src_id else f'{label}-{frag.src_id}')
    el.set('d', geom_d(frag.geom))
    el.set('fill', color or frag.fill)
    el.set('fill-rule', 'evenodd')
    return [el]


def make_layer(num: int):
    g = etree.Element(SVG + 'g')
    g.set('id', f'layer-piece-{num}')
    g.set(INK_MODE, 'layer')
    g.set(INK_LABEL, f'piece-{num}')
    return g


def strip_pieces_and_cuts(root):
    """Remove piece layers + CUTS; return insertion index of first piece."""
    idx = None
    for c in list(root):
        if not isinstance(c.tag, str) or etree.QName(c).localname != 'g':
            continue
        gid = c.get('id') or ''
        lab = c.get(INK_LABEL) or ''
        if gid.startswith('layer-piece-') or lab == CUTS_LABEL:
            if idx is None:
                idx = list(root).index(c)
            root.remove(c)
    return idx if idx is not None else len(root)


def write_final(tree, groups: list[PieceGroup], out: Path):
    root = copy.deepcopy(tree.getroot())
    idx = strip_pieces_and_cuts(root)
    root.set('{%s}docname' % SODI_NS, out.name)
    for n, g in enumerate(groups, 1):
        layer = make_layer(n)
        for frag in g.frags:
            for el in frag_elements(f'piece-{n}', frag, color=None):
                layer.append(el)
        root.insert(idx, layer)
        idx += 1
    etree.ElementTree(root).write(str(out), encoding='utf-8', xml_declaration=True)


def write_preview(tree, groups: list[PieceGroup], out: Path):
    root = copy.deepcopy(tree.getroot())
    idx = strip_pieces_and_cuts(root)
    for c in list(root):
        if isinstance(c.tag, str) and (c.get('id') or '') in (
                'preview-bg', 'preview-labels', 'preview-guides', 'preview-conflicts'):
            root.remove(c)
    bg = etree.Element(SVG + 'rect', x='0', y='0', width='2048', height='2732',
                       fill='#ffffff', id='preview-bg')
    root.insert(idx, bg)
    idx += 1
    labels = etree.Element(SVG + 'g', id='preview-labels')
    labels.set(INK_MODE, 'layer')
    labels.set(INK_LABEL, 'preview-labels')
    area_i = 0
    extra_i = 0
    for n, g in enumerate(groups, 1):
        if g.is_area:
            col = area_color(area_i)
            area_i += 1
            label_fill = '#000000'
            size = 22
        else:
            col = extra_color(extra_i)
            extra_i += 1
            label_fill = '#333333'
            size = 18
        layer = make_layer(n)
        for frag in g.frags:
            for el in frag_elements(f'piece-{n}', frag, color=col):
                layer.append(el)
        root.insert(idx, layer)
        idx += 1
        geom = g.geom
        if geom.is_empty:
            continue
        pt = geom.representative_point()
        labels.append(text_el(pt.x, pt.y + (0 if g.is_area else 6), str(n), size, label_fill))
    root.append(labels)
    root.set('{%s}docname' % SODI_NS, out.name)
    etree.ElementTree(root).write(str(out), encoding='utf-8', xml_declaration=True)


# --------------------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('input', type=Path, help='SVG with layer-piece-* and CUTS layer')
    p.add_argument('--final', type=Path, required=True, help='wesola_final_map.svg')
    p.add_argument('--preview', type=Path, required=True, help='wesola_areas_preview.svg')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    tree = etree.parse(str(args.input))
    root = tree.getroot()
    cuts = load_cuts(root)
    pieces = load_pieces(root)
    print(f'loaded {len(pieces)} pieces, {len(cuts)} cuts')
    groups = apply_cuts(pieces, cuts)
    # Final order: keep origin order (already), sequential renumber on write
    n_area = sum(1 for g in groups if g.is_area)
    print(f'segments: {len(groups)} ({n_area} areas + {len(groups) - n_area} extras)')
    write_final(tree, groups, args.final)
    print(f'wrote {args.final}')
    write_preview(tree, groups, args.preview)
    print(f'wrote {args.preview}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
