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


def makeDIN188Tbolt(self, fa):
    """Create a DIN 188 T-head bolt (double-nib neck).

    Geometry is a 1:1 port of the DIN 188 master macro.  It differs from
    DIN 186 in the NECK: instead of a full four-flat square neck, DIN 188
    has a round core with two opposing diagonal nibs (quadrants 2 and 4).
    The M10-specific constants in that macro are replaced by values pulled
    from FsData via fa.dimTable; values the standard gives as max/min pairs
    (ds, k, h, n, m) are averaged to their mean.  Length is user-selectable
    and an optional ISO metric thread is cut on the lower b portion.

    DIN188def.csv "DIN188def" column order (fa.dimTable):
      P, b1, b2, b3, ds_max, ds_min, k_max, k_min, h_max, h_min,
      n_max, n_min, m_max, m_min, r1, r2

    Coordinate origin (matches the macro):
      z = 0           underside of the T-head (neck start)
      z = 0 … +k      T-head
      z = 0 … -total_neck_h   round core + double nib + 15° taper
      z = -L          shaft tip
    """
    SType = fa.baseType
    if SType != "DIN188":
        raise NotImplementedError(f"Unknown T-bolt type: {SType}")
    if fa.dimTable is None:
        raise ValueError("DIN188 T-bolt requires a standard diameter")

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
    h = (h_max + h_min) / 2.0        # straight neck height
    n = (n_max + n_min) / 2.0        # neck width
    m = (m_max + m_min) / 2.0        # T-head length

    taper_angle = 15.0
    tol = 1e-3
    bottom_chamfer = E * 0.1

    n_half = n / 2.0
    m_half = m / 2.0
    h_half = h / 2.0

    # ── Pitch + thread length (banded by length) ──────────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    pitch = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    L_t = b1 if length <= 120 else (b2 if length <= 200 else b3)
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        L_t = float(raw_tlen)

    # ── 2. Neck: round core + two opposing filleted nibs, then 15° taper ──
    R_actual = (n_half - r2) * math.sqrt(2.0) + r2
    taper_h  = (R_actual - (E / 2.0)) * math.tan(math.radians(taper_angle))
    total_neck_h = h + taper_h
    z_bot = -total_neck_h

    core_full = Part.makeCylinder(
        E / 2.0, total_neck_h, FreeCAD.Vector(0, 0, z_bot), FreeCAD.Vector(0, 0, 1))

    nib_q2 = Part.makeBox(n_half, n_half, total_neck_h, FreeCAD.Vector(-n_half, 0, z_bot))
    e_q2 = [e for e in nib_q2.Edges
            if abs(e.BoundBox.XMin - (-n_half)) < tol
            and abs(e.BoundBox.YMax - n_half) < tol
            and e.BoundBox.ZLength > (total_neck_h - tol)]
    if e_q2 and r2 > 1e-4:
        try:
            nib_q2 = nib_q2.makeFillet(r2, e_q2)
        except Exception:
            pass

    nib_q4 = Part.makeBox(n_half, n_half, total_neck_h, FreeCAD.Vector(0, -n_half, z_bot))
    e_q4 = [e for e in nib_q4.Edges
            if abs(e.BoundBox.XMax - n_half) < tol
            and abs(e.BoundBox.YMin - (-n_half)) < tol
            and e.BoundBox.ZLength > (total_neck_h - tol)]
    if e_q4 and r2 > 1e-4:
        try:
            nib_q4 = nib_q4.makeFillet(r2, e_q4)
        except Exception:
            pass

    neck_straight_raw = core_full.fuse(nib_q2).fuse(nib_q4)

    cone_taper  = Part.makeCone(
        E / 2.0, R_actual, taper_h, FreeCAD.Vector(0, 0, z_bot), FreeCAD.Vector(0, 0, 1))
    cyl_protect = Part.makeCylinder(
        R_actual + 5.0, h, FreeCAD.Vector(0, 0, -h), FreeCAD.Vector(0, 0, 1))
    taper_envelope = cone_taper.fuse(cyl_protect)

    neck_final = neck_straight_raw.common(taper_envelope).removeSplitter()

    # ── 3. T-head: box minus 1:20 side drafts minus 45° top chamfers ──────
    n_head = n + 0.01                 # micro-step around the flush-face fillet bug
    n_head_half = n_head / 2.0

    head_box = Part.makeBox(m, n_head, k, FreeCAD.Vector(-m_half, -n_head_half, 0))

    draft_in = (k + 5.0) / 20.0
    w_R = Part.Face(Part.makePolygon([
        FreeCAD.Vector(0, n_head_half, 0),
        FreeCAD.Vector(0, 100, 0),
        FreeCAD.Vector(0, 100, k + 5),
        FreeCAD.Vector(0, n_head_half - draft_in, k + 5),
        FreeCAD.Vector(0, n_head_half, 0),
    ])).extrude(FreeCAD.Vector(m * 2, 0, 0))
    w_R.translate(FreeCAD.Vector(-m, 0, 0))

    w_L = Part.Face(Part.makePolygon([
        FreeCAD.Vector(0, -n_head_half, 0),
        FreeCAD.Vector(0, -100, 0),
        FreeCAD.Vector(0, -100, k + 5),
        FreeCAD.Vector(0, -n_head_half + draft_in, k + 5),
        FreeCAD.Vector(0, -n_head_half, 0),
    ])).extrude(FreeCAD.Vector(m * 2, 0, 0))
    w_L.translate(FreeCAD.Vector(-m, 0, 0))

    chamf_dist = k - h_half
    c_F = Part.Face(Part.makePolygon([
        FreeCAD.Vector(m_half, 0, h_half),
        FreeCAD.Vector(100, 0, h_half),
        FreeCAD.Vector(100, 0, k + 5),
        FreeCAD.Vector(m_half - chamf_dist, 0, k + 5),
        FreeCAD.Vector(m_half, 0, h_half),
    ])).extrude(FreeCAD.Vector(0, n_head * 2, 0))
    c_F.translate(FreeCAD.Vector(0, -n_head, 0))

    c_B = Part.Face(Part.makePolygon([
        FreeCAD.Vector(-m_half, 0, h_half),
        FreeCAD.Vector(-100, 0, h_half),
        FreeCAD.Vector(-100, 0, k + 5),
        FreeCAD.Vector(-m_half + chamf_dist, 0, k + 5),
        FreeCAD.Vector(-m_half, 0, h_half),
    ])).extrude(FreeCAD.Vector(0, n_head * 2, 0))
    c_B.translate(FreeCAD.Vector(0, -n_head, 0))

    head_final = head_box.cut(w_R).cut(w_L).cut(c_F).cut(c_B).removeSplitter()

    # ── 4. Shaft + assembly ───────────────────────────────────────────────
    shank_length = length - total_neck_h - bottom_chamfer

    shaft_main = Part.makeCylinder(
        E / 2.0, shank_length, FreeCAD.Vector(0, 0, -length + bottom_chamfer), FreeCAD.Vector(0, 0, 1))
    shaft_chamfer = Part.makeCone(
        E / 2.0 - bottom_chamfer, E / 2.0, bottom_chamfer,
        FreeCAD.Vector(0, 0, -length), FreeCAD.Vector(0, 0, 1))

    bolt_raw = head_final.fuse(neck_final).fuse(shaft_main).fuse(shaft_chamfer).removeSplitter()

    # ── 5. Under-head r1 fillet (z=0 edges within the neck footprint) ─────
    inner_edges = []
    for e in bolt_raw.Edges:
        bb = e.BoundBox
        if abs(bb.ZMax) < tol and abs(bb.ZMin) < tol:
            if bb.XMax <= (n_half + tol) and bb.XMin >= -(n_half + tol) \
               and bb.YMax <= (n_half + tol) and bb.YMin >= -(n_half + tol):
                inner_edges.append(e)

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
    L_t = max(0.0, min(L_t, shank_length + bottom_chamfer))
    if getattr(fa, "Thread", False) and L_t > 1e-6 and pitch > 0:
        thread_cutter = self.CreateBlindThreadCutter(E, pitch, L_t)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -(length - L_t)))
        bolt_final = bolt_final.cut(thread_cutter)

    return Part.Solid(bolt_final)
