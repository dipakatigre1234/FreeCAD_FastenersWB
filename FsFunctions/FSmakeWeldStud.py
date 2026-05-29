# -*- coding: utf-8 -*-
"""
***************************************************************************
*   FSmakeWeldStud.py                                                      *
*                                                                          *
*   ISO 13918 Table 11 — Welding Stud  (Type PT, M3 – M10)               *
*                                                                          *
*   Geometry (matches macro exactly — 7-point 2D profile revolved 360°):  *
*     Weld cone  : z = -h_cone … z = 0                                    *
*     Collar     : z = 0       … z = h1                                   *
*     Shank      : z = h1      … z = l1   (threaded section)              *
*                                                                          *
*   Coordinate origin: bottom rim of collar (bearing / workpiece face).   *
*   Total extent: from z = -h_cone (weld tip) to z = l1 (shank top).     *
*                                                                          *
*   h_cone is computed from the collar diameter d2 and cone half-angle:   *
*     h_cone = (d2 / 2) / tan(alpha / 2)                                 *
*                                                                          *
*   Threading: ISO metric (FSThreadingMetric), on the shank only.         *
*   cut_thread starts at z = l1 (shank top) and sweeps downward to z=h1. *
***************************************************************************
"""
import math
from screw_maker import *
import FSThreadingMetric as _TM


def makeWeldStud(self, fa):
    """Create an ISO 13918 Table 11 welding stud.

    CSV dimTable column order (after 'Dia' key):
        d_2, d_2_tol, l_1_tol, h_5_max, h_1_min, h_1_max, alpha, alpha_tol
    """
    if fa.baseType != "ISO13918":
        raise NotImplementedError(f"Unknown weld stud type: {fa.baseType}")

    # ── Unpack CSV dimTable ───────────────────────────────────────────────────
    (d2_raw, d2_tol, l1_tol, h5_max,
     h1_min, h1_max, alpha_raw, alpha_tol) = fa.dimTable

    # Nominal thread / shank diameter from DiaList (e.g. 6.0 mm for M6)
    d1 = self.getDia(fa.calc_diam, False)

    # User-selected total length: collar-bottom rim → shank top (mm)
    l1 = fa.calc_len

    d2    = float(d2_raw)                                  # Collar diameter (mm)
    h1    = (float(h1_min) + float(h1_max)) / 2.0         # Collar height midpoint (mm)
    alpha = float(alpha_raw)                               # Weld cone angle (degrees)

    # Slightly deviated shank diameter so thread cuts are visible on surface
    d_eff = _TM.get_shank_dia(fa, d1)

    # ── Weld cone depth ───────────────────────────────────────────────────────
    # tan(alpha/2) = (d2/2) / h_cone  →  h_cone = (d2/2) / tan(alpha/2)
    half_alpha_rad = math.radians(alpha / 2.0)
    h_cone = (d2 / 2.0) / math.tan(half_alpha_rad)

    # ── 2D profile — right-hand half, revolved 360° around Z ─────────────────
    #
    #  p1 ─ cone tip          (0,       -h_cone)
    #  p2 ─ collar bot rim    (d2/2,     0      )
    #  p3 ─ collar top rim    (d2/2,     h1     )
    #  p4 ─ shank base        (d_eff/2,  h1     )   step down from d2 to d_eff
    #  p5 ─ shank top rim     (d_eff/2,  l1     )
    #  p6 ─ shank top centre  (0,        l1     )
    #  p7 ─ close loop        (0,       -h_cone )
    #
    p1 = FreeCAD.Vector(0,         0, -h_cone)
    p2 = FreeCAD.Vector(d2 / 2,    0,  0)
    p3 = FreeCAD.Vector(d2 / 2,    0,  h1)
    p4 = FreeCAD.Vector(d_eff / 2, 0,  h1)
    p5 = FreeCAD.Vector(d_eff / 2, 0,  l1)
    p6 = FreeCAD.Vector(0,         0,  l1)
    p7 = FreeCAD.Vector(0,         0, -h_cone)   # closes the profile

    pts   = [p1, p2, p3, p4, p5, p6, p7]
    edges = [Part.makeLine(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]

    wire  = Part.Wire(edges)
    face  = Part.Face(wire)
    shape = face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360)

    # ── ISO metric threading on shank (z = h1 → l1) ──────────────────────────
    #
    #  cut_thread creates a cutter at offset_z and sweeps DOWNWARD by tl mm.
    #  Setting offset_z = l1  and  tl = l1 - h1  cuts from the shank top down
    #  to the collar top, leaving the collar and cone unthreaded.
    #
    if getattr(fa, "Thread", False):
        tl       = l1 - h1          # Thread length = shank height above collar
        offset_z = l1               # Start at shank top, sweep downward
        shape    = _TM.cut_thread(shape, fa, d_eff, tl, offset_z)

    return Part.Solid(shape)
