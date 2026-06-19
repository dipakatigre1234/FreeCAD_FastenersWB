# -*- coding: utf-8 -*-
"""
***************************************************************************
*   FSmakeTbolt.py                                                         *
*                                                                          *
*   DIN 186 — T-head bolt (Hammerschraube / T-Kopfschraube)                *
*                                                                          *
*   Geometry is a 1:1 port of the DIN 186 master macro.  The M10-specific  *
*   constants in that macro are replaced by values pulled from FsData via  *
*   fa.dimTable; values the standard gives as max/min pairs (ds, k, h, n,  *
*   m) are averaged to their mean.  Length is user-selectable and an       *
*   optional ISO metric thread is cut on the lower b portion of the shank. *
*                                                                          *
*   DIN186def.csv  "DIN186def" column order (fa.dimTable):                 *
*     P, b1, b2, b3, ds_max, ds_min, k_max, k_min, h_max, h_min,           *
*     n_max, n_min, m_max, m_min, r1, r2                                   *
*   where                                                                  *
*     P            : thread pitch (coarse)                                 *
*     b1, b2, b3   : thread length for l<=120 / 120<l<=200 / l>200         *
*     ds           : shank/body diameter        (macro: E)                 *
*     k            : total T-head height        (macro: k)                 *
*     h            : square-neck straight height (macro: h)                *
*     n            : head & neck width          (macro: n)                 *
*     m            : T-head length              (macro: m)                 *
*     r1           : under-head fillet radius                              *
*     r2           : square-neck corner fillet radius                      *
***************************************************************************
"""
from screw_maker import *


def makeTbolt(self, fa):
    """Create a DIN 186 T-head bolt.

    Coordinate origin (matches the macro):
      z = 0                      underside of the T-head (neck start)
      z = 0 … +k                 T-head (extruded profile)
      z = 0 … -total_neck_depth  square neck + 15° taper
      z = -L                     shaft tip
    """
    SType = fa.baseType
    if SType != "DIN186":
        raise NotImplementedError(f"Unknown T-bolt type: {SType}")
    if fa.dimTable is None:
        raise ValueError("DIN186 T-bolt requires a standard diameter")

    length = fa.calc_len

    # ── CSV dimensions ────────────────────────────────────────────────────
    (P_tbl, b1, b2, b3,
     ds_max, ds_min,
     k_max, k_min,
     h_max, h_min,
     n_max, n_min,
     m_max, m_min,
     r1, r2) = (float(v) for v in fa.dimTable)

    # Mean values for the max/min pairs (per the standard's tolerance band)
    E = (ds_max + ds_min) / 2.0      # body / shank diameter (macro: E)
    k = (k_max + k_min) / 2.0        # total T-head height
    h = (h_max + h_min) / 2.0        # square-neck straight height
    n = (n_max + n_min) / 2.0        # head & neck width
    m = (m_max + m_min) / 2.0        # T-head length

    taper_15 = 15.0
    tol = 1e-3
    bottom_chamfer = E * 0.1

    # ── Pitch + thread length (banded by length) ──────────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    pitch = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    L_t = b1 if length <= 120 else (b2 if length <= 200 else b3)
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        L_t = float(raw_tlen)

    # ── 2. T-head geometry (2D profile extruded along Y) ──────────────────
    h_half = h / 2.0
    m_half = m / 2.0
    x_int  = m_half + h_half - k     # flat-top / 45° end-chamfer intersection

    p0 = FreeCAD.Vector(0,       0, 0)
    p1 = FreeCAD.Vector(m_half,  0, 0)
    p2 = FreeCAD.Vector(m_half,  0, h_half)
    p3 = FreeCAD.Vector(x_int,   0, k)
    p4 = FreeCAD.Vector(0,       0, k)
    p5 = FreeCAD.Vector(-x_int,  0, k)
    p6 = FreeCAD.Vector(-m_half, 0, h_half)
    p7 = FreeCAD.Vector(-m_half, 0, 0)

    face = Part.Face(Part.makePolygon([p0, p1, p2, p3, p4, p5, p6, p7, p0]))
    face.translate(FreeCAD.Vector(0, -n / 2.0, 0))
    head_raw = face.extrude(FreeCAD.Vector(0, n, 0))

    # ── 3. Square neck with 15° horizontal taper ──────────────────────────
    R_actual = (n / 2.0 - r2) * math.sqrt(2.0) + r2

    neck_cyl = Part.makeCylinder(R_actual, h)
    neck_cyl.translate(FreeCAD.Vector(0, 0, -h))

    taper_height    = (R_actual - (E / 2.0)) * math.tan(math.radians(taper_15))
    total_neck_depth = h + taper_height

    neck_taper = Part.makeCone(E / 2.0, R_actual, taper_height)
    neck_taper.translate(FreeCAD.Vector(0, 0, -total_neck_depth))

    neck_raw = neck_cyl.fuse(neck_taper)

    # Square-flat cutting tool (block minus rounded-corner square hole)
    box_margin = m * 2.0
    tool_h     = total_neck_depth * 4.0

    outerBox = Part.makeBox(box_margin, box_margin, tool_h)
    outerBox.translate(FreeCAD.Vector(-box_margin / 2.0, -box_margin / 2.0, -tool_h / 2.0))

    innerBox = Part.makeBox(n, n, tool_h + 2.0)
    innerBox.translate(FreeCAD.Vector(-n / 2.0, -n / 2.0, -tool_h / 2.0 - 1.0))

    v_edges = [e for e in innerBox.Edges
               if abs(e.BoundBox.ZLength - (tool_h + 2.0)) < tol]
    if len(v_edges) == 4 and r2 > 1e-4:
        try:
            innerBox = innerBox.makeFillet(r2, v_edges)
        except Exception:
            pass

    tool       = outerBox.cut(innerBox)
    neck_final = neck_raw.cut(tool)

    # ── 4. Shaft ──────────────────────────────────────────────────────────
    shank_length = length - total_neck_depth - bottom_chamfer

    shaft_main = Part.makeCylinder(E / 2.0, shank_length)
    shaft_main.translate(FreeCAD.Vector(0, 0, -length + bottom_chamfer))

    shaft_chamfer = Part.makeCone(E / 2.0 - bottom_chamfer, E / 2.0, bottom_chamfer)
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -length))

    shaft = shaft_main.fuse(shaft_chamfer)

    # ── 5. Final assembly + under-head r1 fillet ──────────────────────────
    bolt_raw = shaft.fuse(neck_final).fuse(head_raw).removeSplitter()

    inner_edges = [e for e in bolt_raw.Edges
                   if abs(e.BoundBox.ZMax) < tol and abs(e.BoundBox.ZMin) < tol]

    bolt_final = bolt_raw
    if inner_edges and r1 > 1e-4:
        for rr in (r1, r1 * 0.75, r1 * 0.5, r1 * 0.25):
            try:
                bolt_final = bolt_raw.makeFillet(rr, inner_edges)
                break
            except Exception:
                continue
    bolt_final = bolt_final.removeSplitter()

    # ── 6. Optional ISO metric thread on the lower b portion ──────────────
    # Thread cannot run into the tapered neck — clamp to the plain shaft.
    L_t = max(0.0, min(L_t, shank_length + bottom_chamfer))
    if getattr(fa, "Thread", False) and L_t > 1e-6 and pitch > 0:
        thread_cutter = self.CreateBlindThreadCutter(E, pitch, L_t)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -(length - L_t)))
        bolt_final = bolt_final.cut(thread_cutter)

    return Part.Solid(bolt_final)
