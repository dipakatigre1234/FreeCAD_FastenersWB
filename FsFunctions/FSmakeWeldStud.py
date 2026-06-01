# -*- coding: utf-8 -*-
"""
***************************************************************************
*   FSmakeWeldStud.py                                                      *
*                                                                          *
*   ISO 13918 Table 11 — Welding Stud  (Type PT, M3 – M10)               *
*   ISO 13918 Table A  — Internally Threaded Welding Stud (M3 – M6)      *
*                                                                          *
*   ISO 13918 PT (makeWeldStud):                                           *
*     Weld cone  : z = -h_cone … z = 0                                    *
*     Collar     : z = 0       … z = h1                                   *
*     Shank      : z = h1      … z = l1   (externally threaded)           *
*                                                                          *
*   ISO 13918A (makeWeldStudA):                                            *
*     Weld knob  : z = -l3     … z = 0    (small projection, d4 dia)     *
*     Collar     : z = 0       … z = h1                                   *
*     Shaft      : z = h1      … z = l    (d1 dia, plain outer surface)  *
*     Shallow cone at bottom of collar (alpha ≈ 174°, per standard)      *
*     Internal threaded bore : from top face downward, depth b, dia d6   *
*                                                                          *
*   Coordinate origin: bottom rim of collar (datum A / workpiece face).   *
***************************************************************************
"""
import math
from screw_maker import *
import FSThreadingMetric as _TM
import FSThreadingMetricInternal as _TMI


def makeWeldStud(self, fa):
    """Create an ISO 13918 welding stud (Table 11 PT or Table A internally threaded)."""
    if fa.baseType == "ISO13918A":
        return makeWeldStudA(self, fa)
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
    p7 = FreeCAD.Vector(0,         0, -h_cone)

    pts   = [p1, p2, p3, p4, p5, p6, p7]
    edges = [Part.makeLine(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]

    wire  = Part.Wire(edges)
    face  = Part.Face(wire)
    shape = face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360)

    # ── ISO metric threading on shank (z = h1 → l1) ──────────────────────────
    #
    # Threads run from the free end (z = l1) downward.
    # tl is reduced by one pitch so the helix runout (ht = (tl//P+1)*P in
    # make_metric_thread_cutter) lands at h1 rather than below it.
    # The hard clip at z=h1 removes any floating-point overshoot.
    #
    if getattr(fa, "Thread", False):
        P        = _TM.resolve_metric_pitch(fa)
        max_tl   = l1 - h1
        user_tl  = float(getattr(fa, "calc_thread_length", 0.0) or 0.0)
        tl_raw   = min(user_tl, max_tl) if user_tl > 0.0 else max_tl
        tl       = max(tl_raw - P, P)

        d_cutter   = _TM.get_shank_dia(fa, d_eff)
        root_round = str(getattr(fa, "Thread_Root", "Flat") or "Flat").strip() == "Round"

        tc = _TM.make_metric_thread_cutter(d_cutter, P, tl, root_round=root_round)
        tc.translate(FreeCAD.Base.Vector(0, 0, l1))

        clip_r   = d2 + 2.0
        clip_h   = l1 - h1 + 2.0
        clip_box = Part.makeBox(2 * clip_r, 2 * clip_r, clip_h,
                                FreeCAD.Base.Vector(-clip_r, -clip_r, h1))
        tc    = tc.common(clip_box)
        shape = shape.cut(tc)

    return Part.Solid(shape)


def makeWeldStudA(self, fa):
    """Create an ISO 13918 Table A internally threaded welding stud.

    CSV dimTable column order (after 'Dia' key):
        l, l_tol_plus, b, d2, d2_tol_pm, d1, d1_tol_pm,
        d4, d4_tol_pm, l3, l3_tol_pm, h1_min, h1_max,
        alpha, alpha_tol_pm, d6

    Geometry (z origin = bottom rim of collar / datum A):
      Weld knob   z = -l3  …  z = 0   (cylinder, dia d4)
      Collar      z =  0   …  z = h1  (cylinder, dia d2, with shallow cone at base)
      Shaft       z =  h1  …  z = l   (cylinder, dia d1)
      Bore        from z = l downward by depth b, dia d6 (internal metric thread)
    """
    if fa.baseType != "ISO13918A":
        raise NotImplementedError(f"Unknown weld stud type: {fa.baseType}")

    # ── Unpack CSV dimTable ───────────────────────────────────────────────────
    (l_nom, l_tol_plus,
     b_raw,
     d2_raw, d2_tol_pm,
     d1_raw, d1_tol_pm,
     d4_raw, d4_tol_pm,
     l3_raw, l3_tol_pm,
     h1_min, h1_max,
     alpha_raw, alpha_tol_pm,
     d6_raw) = fa.dimTable

    # User-selected total length (collar-bottom rim → shaft top)
    l  = fa.calc_len

    d1    = float(d1_raw)                                # Shaft outer diameter (mm)
    d2    = float(d2_raw)                                # Collar diameter (mm)
    d4    = float(d4_raw)                                # Weld knob diameter (mm)
    d6    = float(d6_raw)                                # Internal thread nominal dia (mm)
    b     = float(b_raw)                                 # Internal thread depth (mm)
    l3    = float(l3_raw)                                # Weld knob length (mm)
    h1    = (float(h1_min) + float(h1_max)) / 2.0       # Collar height midpoint (mm)
    alpha = float(alpha_raw)                             # Weld cone included angle (deg)

    # max_thread_depth: bore and threading must not enter the collar
    max_thread_depth = l - h1
    b = min(b, max_thread_depth)

    # ── Alpha cone geometry ───────────────────────────────────────────────────
    # The collar underside is a concave dome. alpha is the INCLUDED angle of
    # the cone measured at the apex (≈174°), so the half-angle off the axis
    # is (180° - alpha) / 2 ≈ 3°.
    # The cone rises from the nib top (r=d4/2, z=0) outward to the collar
    # rim (r=d2/2). The rise height is:
    #   cone_rise = (d2/2 - d4/2) * tan(half_angle_from_horizontal)
    # Because the angle is measured from horizontal (datum A plane):
    #   half_angle_from_horiz = (180° - alpha) / 2
    #   cone_rise = (d2/2 - d4/2) * tan(half_angle_from_horiz)
    half_angle_rad = math.radians((180.0 - alpha) / 2.0)
    cone_rise = (d2 / 2.0 - d4 / 2.0) * math.tan(half_angle_rad)
    cone_rise = max(cone_rise, 0.02)   # at least a sliver

    # ── 2D profile — right-hand half, revolved 360° around Z ─────────────────
    #
    # Datum A (z = 0) is the outer bottom rim of the collar.
    #
    #  pa ─ nib tip           r=0,      z = -l3          axis bottom
    #  pb ─ nib base          r=d4/2,   z = -l3          nib bottom outer
    #  pc ─ nib top           r=d4/2,   z = 0            nib meets collar face
    #  pd ─ cone root (rim)   r=d2/2,   z = cone_rise    collar outer bottom rim
    #                                                     (cone is concave upward)
    #  pe ─ collar top rim    r=d2/2,   z = h1
    #  pf ─ shaft base        r=d1/2,   z = h1           step in d2→d1
    #  pg ─ shaft top rim     r=d1/2,   z = l
    #  ph ─ shaft top centre  r=0,      z = l            closes at axis
    #  (close back down axis to pa)
    #
    # Note: pd is at z = cone_rise (above datum A) because the cone is a
    # concave dish — the outer rim is HIGHER than the nib-top junction.
    # The flat collar wall runs from pd upward to pe at z = h1.
    # h1 is measured from datum A, so pe.z = h1  (not h1 + cone_rise).
    # This means the straight collar wall height is (h1 - cone_rise).
    # Guard against degenerate case where cone_rise >= h1.
    collar_wall_h = h1 - cone_rise
    if collar_wall_h < 0.05:
        cone_rise = h1 * 0.5
        collar_wall_h = h1 - cone_rise

    pa = FreeCAD.Vector(0,       0, -l3)
    pb = FreeCAD.Vector(d4 / 2,  0, -l3)
    pc = FreeCAD.Vector(d4 / 2,  0,  0)
    pd = FreeCAD.Vector(d2 / 2,  0,  cone_rise)
    pe = FreeCAD.Vector(d2 / 2,  0,  h1)
    pf = FreeCAD.Vector(d1 / 2,  0,  h1)
    pg = FreeCAD.Vector(d1 / 2,  0,  l)
    ph = FreeCAD.Vector(0,       0,  l)
    px = FreeCAD.Vector(0,       0, -l3)   # closes back to pa

    # When d1 == d2 (e.g. M6: shaft and collar same diameter) pe and pf are
    # identical — skip that degenerate zero-length edge.
    if abs(d1 - d2) < 1e-6:
        pts = [pa, pb, pc, pd, pe, pg, ph, px]
    else:
        pts = [pa, pb, pc, pd, pe, pf, pg, ph, px]
    edges = [Part.makeLine(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    wire  = Part.Wire(edges)
    face  = Part.Face(wire)
    shape = face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360)

    # ── Resolve internal thread pitch (shared by bore + cutter) ───────────────
    #
    # Pitch source priority (mirrors makeHexNut metric path):
    #   1. Thread_Pitch_Nut (dashboard, via _TMI.resolve_nut_pitch)
    #   2. coarsest ISO metric pitch for d6 from CSV fallback table
    #
    _d6_str = "M%g" % d6
    _saved_diam  = fa.calc_diam
    fa.calc_diam = _d6_str
    P = _TMI.resolve_nut_pitch(fa)
    fa.calc_diam = _saved_diam
    if not P or P <= 0:
        _coarse = {"3": 0.5, "4": 0.7, "5": 0.8, "6": 1.0}
        P = _coarse.get(str(int(d6)), 1.0)

    # ── Bore minor radius (CSV-driven, same as makeHexNut) ────────────────────
    #
    # CRITICAL FIX: the pre-cut bore wall MUST sit at the MINOR diameter, not
    # at the nominal d6/2.  In makeHexNut the bore wall = D1max/2 (minor radius)
    # and the cutter (run at dia + 0.05*P) then carves the thread form between
    # minor and major.  Cutting the bore at the nominal d6/2 (≈0.54 mm too wide
    # for M6) leaves the thread crests floating in empty space — which produced
    # the disconnected ring artifact instead of a continuous helix.
    #
    # Resolve minor radius from metric_internal_thread_dia.csv (D1max). Fall
    # back to the ISO geometric minor diameter:  d6/2 - (5/8)·H,  H = P·cos30.
    #
    _bore_r = None
    if _TMI is not None:
        try:
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "6H") or "6H")
            _bore_eff = _TMI.bore_dia_from_table(fa, _d6_str, str(P), _cls_s)
            if _bore_eff and _bore_eff > 0:
                _bore_r = _bore_eff / 2.0
        except Exception:
            _bore_r = None
    if _bore_r is None:
        H = P * cos30
        _bore_r = d6 / 2.0 - H * 5.0 / 8.0

    # ── Countersunk entry at bore mouth (top face, z = l) ────────────────────
    # 45° chamfer, depth = 0.6 × pitch.  Outer radius taken from the MINOR
    # radius (bore wall) so the chamfer blends with the actual bore, not the
    # oversized nominal hole.
    csk_depth  = 0.6 * P                 # axial depth of 45° chamfer
    csk_r_top  = _bore_r + csk_depth     # outer radius at top face
    # Countersink: small end (_bore_r) at z=l-csk_depth, large end at z=l.
    # makeCone(r1,r2,h) builds upward; r1 at bottom, r2 at top.
    csk_cone = Part.makeCone(_bore_r, csk_r_top, csk_depth)
    csk_cone.translate(FreeCAD.Vector(0, 0, l - csk_depth))
    shape = shape.cut(csk_cone)

    # ── Bore + threading ──────────────────────────────────────────────────────
    #
    # Bore mouth at z=l (top face), blind end at z=l-b (downward).
    # Thread cutter is z-up: z=0=blind, z=thread_depth=mouth.
    # Translate cutter by (l - thread_depth) so its mouth aligns with z=l.
    #
    user_tl      = float(getattr(fa, "calc_thread_length", 0.0) or 0.0)
    thread_depth = min(user_tl, b) if user_tl > 0.0 else b

    if getattr(fa, "Thread", False):
        # Pre-cut plain bore at the MINOR radius (solid walls for the cutter
        # to bite into) — identical strategy to makeHexNut's revolve profile.
        bore_cyl = Part.makeCylinder(_bore_r, b)
        bore_cyl.translate(FreeCAD.Vector(0, 0, l - b))
        shape = shape.cut(bore_cyl)

        # Thread cutter runs at (d6 + 0.05·P)/... just above major dia, exactly
        # as makeHexNut does: CreateInnerThreadCutter(dia + 0.05*P, P, depth+P).
        # It carves the thread form from major inward into the minor-dia wall.
        thread_dia    = d6 + 0.05 * P
        thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, thread_depth + P)
        thread_cutter.translate(FreeCAD.Base.Vector(0, 0, l - thread_depth))
        shape = shape.cut(thread_cutter)
    else:
        # Thread off — plain smooth bore full depth, at nominal d6/2 so the
        # clearance hole reads as the tap-drill-free nominal size.
        bore_cyl = Part.makeCylinder(d6 / 2.0, b)
        bore_cyl.translate(FreeCAD.Vector(0, 0, l - b))
        shape = shape.cut(bore_cyl)

    return Part.Solid(shape)