# -*- coding: utf-8 -*-
"""
ASME B18.21.1 Helical Spring Lock Washers

- ASMEB18.21.1.1  (regular series,    Table 1)
- ASMEB18.21.1.2  (heavy series,      Table 2)
- ASMEB18.21.1.3  (extra duty series, Table 3)

Geometry:
  Trapezoidal cross-section (inner edge thicker than outer, 10% taper)
  swept along a single-turn helix.  A 2-degree sector is cut to produce
  two clean separate flat gap faces.  Small fillets on the top face only
  at inner bore and outer rim edges.

CSV columns (A_max, A_min, B_max, T_min, W_min, BW_min):
  A_max / A_min  — bore diameter tolerance band
  B_max          — outer diameter (max)
  T_min          — mean section thickness = (t_inner + t_outer) / 2
"""

import math
from screw_maker import *


def makeHelicalSpringWasher(self, fa):
    """Entry point called from ScrewMaker for ASMEB18.21.1.1 / .2 / .3."""
    return _make_helical_washer(fa)


def _make_helical_washer(fa):
    # ── Read CSV dimensions ───────────────────────────────────────────────
    t = fa.dimTable
    if len(t) < 4:
        raise ValueError(
            "Helical spring lock washer: need at least 4 CSV columns "
            "(A_max, A_min, B_max, T_min)"
        )
    A_max = t[0]
    A_min = t[1]
    B_max = t[2]
    T     = t[3]   # mean section thickness

    # ── Derived radii ─────────────────────────────────────────────────────
    A_mean  = (A_max + A_min) / 2.0
    r_bore  = A_mean / 2.0
    r_outer = B_max  / 2.0
    r_mean  = (r_bore + r_outer) / 2.0

    if r_outer <= r_bore + 0.05:
        raise ValueError("B_max must be larger than A_mean for a valid washer")

    # ── Cross-section thickness ───────────────────────────────────────────
    # T = (t_i + t_o) / 2,  t_o = 0.9 * t_i  →  t_i = T / 0.95
    t_i = T / 0.95
    t_o = 0.9 * t_i

    # ── Trapezoidal cross-section wire ────────────────────────────────────
    p_bi = Base.Vector(r_bore,  0.0, 0.0)
    p_bo = Base.Vector(r_outer, 0.0, 0.0)
    p_to = Base.Vector(r_outer, 0.0, t_o)
    p_ti = Base.Vector(r_bore,  0.0, t_i)

    section_wire = Part.Wire([
        Part.LineSegment(p_bi, p_bo).toShape(),
        Part.LineSegment(p_bo, p_to).toShape(),
        Part.LineSegment(p_to, p_ti).toShape(),
        Part.LineSegment(p_ti, p_bi).toShape(),
    ])

    # ── Full 360° helix, pitch = t_i ─────────────────────────────────────
    helix = Part.makeHelix(t_i, t_i, r_mean)

    # ── Sweep to solid ────────────────────────────────────────────────────
    washer = Part.Wire(helix).makePipeShell([section_wire], True, True)
    try:
        washer = washer.removeSplitter()
    except Exception:
        pass

    # ── Cut 2° sector gap to cleanly separate the two end faces ──────────
    # Both end-caps lie on Y=0 (+X side) at different Z heights and share
    # a point at (r_bore, 0, t_i).  Cutting a 2° revolved sector centred
    # on +X removes the shared zone, leaving two separate flat faces.
    try:
        gap_deg = 2.0
        r_cut   = r_outer + 2.0
        z_bot   = -t_i * 0.5
        z_top_c = t_i * 2.5        # above high-end cap top at 2*t_i

        rp1 = Base.Vector(0.0,   0.0, z_bot)
        rp2 = Base.Vector(r_cut, 0.0, z_bot)
        rp3 = Base.Vector(r_cut, 0.0, z_top_c)
        rp4 = Base.Vector(0.0,   0.0, z_top_c)

        rect_face = Part.Face(Part.Wire([
            Part.makeLine(rp1, rp2),
            Part.makeLine(rp2, rp3),
            Part.makeLine(rp3, rp4),
            Part.makeLine(rp4, rp1),
        ]))

        mat = Base.Matrix()
        mat.rotateZ(math.radians(-gap_deg / 2.0))
        rect_face = rect_face.transformGeometry(mat)

        gap_tool = rect_face.revolve(
            Base.Vector(0, 0, 0),
            Base.Vector(0, 0, 1),
            gap_deg
        )
        washer = washer.cut(gap_tool)
        washer = washer.removeSplitter()
    except Exception:
        pass

    # ── Top-face fillets — inner bore (larger) and outer rim (smaller) ────
    # Detect arc edges by curve radius, restricted to the high-end top face
    # (BoundBox.ZMax within T*0.15 of washer ZMax).
    try:
        r_fillet_inner = T * 0.05   # inner — slightly larger
        r_fillet_outer = T * 0.03   # outer — smaller

        bb       = washer.BoundBox
        z_top    = bb.ZMax
        z_thresh = z_top - T * 0.15

        tol_r = min(r_bore, r_outer - r_bore) * 0.15

        def _is_circle(e):
            try:
                return e.Curve.TypeId == "Part::GeomCircle"
            except Exception:
                return False

        inner_edges = [
            e for e in washer.Edges
            if _is_circle(e)
            and abs(e.Curve.Radius - r_bore) < tol_r
            and e.BoundBox.ZMax >= z_thresh
        ]
        if inner_edges:
            washer = washer.makeFillet(r_fillet_inner, inner_edges)

        bb2      = washer.BoundBox
        z_top2   = bb2.ZMax
        z_thresh2 = z_top2 - T * 0.15
        outer_edges = [
            e for e in washer.Edges
            if _is_circle(e)
            and abs(e.Curve.Radius - r_outer) < tol_r
            and e.BoundBox.ZMax >= z_thresh2
        ]
        if outer_edges:
            washer = washer.makeFillet(r_fillet_outer, outer_edges)
    except Exception:
        pass

    return washer
