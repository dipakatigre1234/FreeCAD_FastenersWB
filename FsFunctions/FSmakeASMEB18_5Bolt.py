# -*- coding: utf-8 -*-
"""
***************************************************************************
*   ASME B18.5 round-head / carriage-bolt family makers                   *
*                                                                         *
*   This file is a supplement to the FreeCAD CAx development system.      *
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU Lesser General Public License (LGPL)    *
*   as published by the Free Software Foundation; either version 2 of     *
*   the License, or (at your option) any later version.                   *
*   for detail see the LICENCE text file.                                 *
***************************************************************************

Geometry for ASME B18.5 Tables 1, 3-10 is a 1:1 port of the per-table
master macros.  The single-size constants of each macro are replaced by
values pulled from FsData via ``fa.dimTable``; every dimension the standard
gives as a max/min pair is averaged to its mean (``_m``).  Length is
user-selectable and an optional UNC thread is cut on the lower shank.

Dispatcher: every ASMEB18.5.x baseType routes to makeASMEB18_5Bolt, which
forwards to the matching _make_* geometry function.

dimTable column order is fixed by the matching FsData/asmeb18.5.x def.csv
header; the unpacking in each function must stay in sync with that header.
Note: B18.5.2 (round-head square-neck) is already provided by
FSmakeCarriageBolt.py and is intentionally not handled here.
"""
from screw_maker import *

import FastenerBase


def _m(a, b):
    """Mean of a max/min tolerance pair."""
    return (a + b) / 2.0


def _add_thread(self, fa, p_solid, shank_dia, tpi, length, plain_shank_len):
    """Optionally cut a blind UNC thread on the lower shank.

    Mirrors the threading scheme of _makeCarriageBoltMain: the thread is
    placed at the very bottom of the shank and never runs into the head or
    neck (clamped to plain_shank_len). Failures degrade gracefully — the
    un-threaded solid is returned rather than aborting the whole fastener.
    """
    if not getattr(fa, "Thread", False):
        return p_solid
    try:
        pitch = 25.4 / tpi
        raw_pitch = getattr(fa, "calc_pitch", None)
        if raw_pitch is not None and raw_pitch > 0.0:
            pitch = raw_pitch
        L_t = (shank_dia * 2 + 6.35) if length <= 152.4 else (shank_dia * 2 + 12.7)
        raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
        if raw_tlen > 0.0:
            L_t = float(raw_tlen)
        L_t = max(0.0, min(L_t, plain_shank_len))
        if L_t <= 1e-6 or pitch <= 0:
            return p_solid
        cutter = self.CreateBlindThreadCutter(shank_dia, pitch, L_t)
        cutter.translate(Base.Vector(0.0, 0.0, -1 * (length - L_t)))
        return p_solid.cut(cutter)
    except Exception as ex:
        FreeCAD.Console.PrintMessage(f"[B18.5] thread skipped: {ex}\n")
        return p_solid


def _shaft(E, L):
    """Plain chamfered shank, axis on -Z, top face at z=0 (shared by all macros)."""
    bottom_chamfer = E * 0.1
    shaft_main = Part.makeCylinder(E / 2.0, L - bottom_chamfer)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer))
    shaft_chamfer = Part.makeCone(E / 2.0 - bottom_chamfer, E / 2.0, bottom_chamfer)
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))
    return shaft_main.fuse(shaft_chamfer)


def _dome_head(A, H):
    """Spherical-cap (round) head sitting on the z=0..z=H band (macro Tables 1/3/4/5/6)."""
    R_s = (A ** 2 / (8.0 * H)) + (H / 2.0)
    sphere_centre = FreeCAD.Vector(0, 0, -(R_s - H))
    dome_full = Part.makeSphere(R_s, sphere_centre)
    clip_margin = A * 2
    clip_below = Part.makeBox(clip_margin, clip_margin, R_s * 2,
                              FreeCAD.Vector(-clip_margin / 2.0, -clip_margin / 2.0, -R_s * 2))
    head = dome_full.cut(clip_below)
    clip_above = Part.makeBox(clip_margin, clip_margin, R_s * 2,
                              FreeCAD.Vector(-clip_margin / 2.0, -clip_margin / 2.0, H))
    head = head.cut(clip_above)
    return head


def _fillet_underhead_and_rim(bolt_raw, E, A, R, tol=1e-3):
    """Inner fillet at the shaft/head joint (radius E/2 arc) and outer dome-rim
    fillet (radius A/2 arc), both on the z=0 bearing plane — verbatim from the
    round-head macros, with graceful fall-through on OCC fillet failures."""
    try:
        inner_edges = []
        for e in bolt_raw.Edges:
            bb = e.BoundBox
            z_mid = (bb.ZMin + bb.ZMax) / 2.0
            if abs(z_mid) < tol and hasattr(e, 'Curve') and hasattr(e.Curve, 'Radius'):
                if abs(e.Curve.Radius - (E / 2.0)) < tol:
                    inner_edges.append(e)
        bolt_step2 = bolt_raw.makeFillet(R, inner_edges) if inner_edges else bolt_raw
    except Exception as ex:
        FreeCAD.Console.PrintMessage(f"[B18.5] inner fillet failed: {ex}\n")
        bolt_step2 = bolt_raw
    try:
        outer_edges = []
        for e in bolt_step2.Edges:
            bb = e.BoundBox
            z_mid = (bb.ZMin + bb.ZMax) / 2.0
            if abs(z_mid) < tol and hasattr(e, 'Curve') and hasattr(e.Curve, 'Radius'):
                if abs(e.Curve.Radius - (A / 2.0)) < tol:
                    outer_edges.append(e)
        bolt_final = bolt_step2.makeFillet(R, outer_edges) if outer_edges else bolt_step2
    except Exception as ex:
        FreeCAD.Console.PrintMessage(f"[B18.5] outer rim fillet failed: {ex}\n")
        bolt_final = bolt_step2
    return bolt_final.removeSplitter()


# =====================================================================
#  Dispatcher
# =====================================================================
def makeASMEB18_5Bolt(self, fa):
    """ASME B18.5 round-head / carriage-bolt family dispatcher."""
    if fa.dimTable is None:
        raise ValueError(f"{fa.baseType} requires a standard diameter")
    bt = fa.baseType
    fn = _DISPATCH.get(bt)
    if fn is None:
        raise NotImplementedError(f"Unknown ASME B18.5 type: {bt}")
    return fn(self, fa)


# =====================================================================
#  Table 1 — Round Head Bolts
# =====================================================================
def _make_5_1_roundhead(self, fa):
    L = fa.calc_len
    tpi, E_max, E_min, A_max, A_min, H_max, H_min, R = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4
    H = _m(H_max, H_min) * 25.4
    R = R * 25.4

    shaft = _shaft(E, L)
    head = _dome_head(A, H)
    bolt = shaft.fuse(head)
    bolt = _fillet_underhead_and_rim(bolt, E, A, R)
    bolt = _add_thread(self, fa, bolt, E, tpi, L, L)
    return Part.Solid(bolt)


# =====================================================================
#  Tables 3 & 6 — Round-head square-neck (short neck) / Step bolts
#  Same square-neck + dome-head macro geometry, different dim tables.
# =====================================================================
def _make_square_neck(self, fa):
    L = fa.calc_len
    (tpi, E_max, E_min, A_max, A_min, H_max, H_min,
     O_max, O_min, AC, P_max, P_min, S, Q, R) = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4
    H = _m(H_max, H_min) * 25.4
    O = _m(O_max, O_min) * 25.4
    P = _m(P_max, P_min) * 25.4
    S = S * 25.4
    Q = Q * 25.4
    R = R * 25.4
    tol = 1e-3

    R_actual = (O / 2.0 - Q) * math.sqrt(2) + Q   # circumradius of rounded square

    shaft = _shaft(E, L)

    # Square neck: straight rounded-square cylinder + 45deg taper to the shaft
    neck_cyl = Part.makeCylinder(R_actual, S)
    neck_cyl.translate(FreeCAD.Vector(0, 0, -S))
    neck_taper = Part.makeCone(E / 2.0, R_actual, P - S)
    neck_taper.translate(FreeCAD.Vector(0, 0, -P))
    neck_raw = neck_cyl.fuse(neck_taper)

    box_margin = A * 2
    tool_z_min = -P * 3
    tool_h = P * 6
    outerBox = Part.makeBox(box_margin, box_margin, tool_h)
    outerBox.translate(FreeCAD.Vector(-box_margin / 2.0, -box_margin / 2.0, tool_z_min))
    inner_h = tool_h * 1.5
    innerBox = Part.makeBox(O, O, inner_h)
    innerBox.translate(FreeCAD.Vector(-O / 2.0, -O / 2.0, tool_z_min - (tool_h * 0.25)))
    v_edges = [e for e in innerBox.Edges if abs(e.BoundBox.ZLength - inner_h) < tol]
    if len(v_edges) == 4 and Q > 1e-4:
        innerBox = innerBox.makeFillet(Q, v_edges)
    tool = outerBox.cut(innerBox)
    neck_final = neck_raw.cut(tool)

    head = _dome_head(A, H)

    bolt = shaft.fuse(neck_final).fuse(head)
    bolt = bolt.removeSplitter()

    # Inner fillet at the neck/bearing joint, outer fillet on the dome rim
    inner_edges, outer_edges = [], []
    for e in bolt.Edges:
        bb = e.BoundBox
        if abs(bb.ZMax) < tol and abs(bb.ZMin) < tol:
            if hasattr(e, 'Curve') and hasattr(e.Curve, 'Radius') and \
               abs(e.Curve.Radius - (A / 2.0)) < tol:
                outer_edges.append(e)
            else:
                inner_edges.append(e)
    try:
        bolt = bolt.makeFillet(R, inner_edges) if inner_edges else bolt
    except Exception as ex:
        FreeCAD.Console.PrintMessage(f"[B18.5] neck fillet failed: {ex}\n")
    try:
        bolt = bolt.makeFillet(R, outer_edges) if outer_edges else bolt
    except Exception as ex:
        FreeCAD.Console.PrintMessage(f"[B18.5] rim fillet failed: {ex}\n")
    bolt = bolt.removeSplitter()

    bolt = _add_thread(self, fa, bolt, E, tpi, L, L - P)
    return Part.Solid(bolt)


# =====================================================================
#  Table 4 — Round Head Ribbed Neck Bolts
# =====================================================================
def _make_5_4_ribbedneck(self, fa):
    L = fa.calc_len
    (tpi, E_max, E_min, A_max, A_min, H_max, H_min,
     M_short, M_long, N, O_in, P_short, P_mid, P_long, R) = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4
    H = _m(H_max, H_min) * 25.4
    R = R * 25.4
    # length-banded selection (table columns: <=7/8in, 1in&1-1/8in, >=1-1/4in)
    M = (M_long if L >= 25.4 else M_short) * 25.4
    if L >= 31.75:
        P = P_long * 25.4
    elif L >= 25.4:
        P = P_mid * 25.4
    else:
        P = P_short * 25.4
    N = int(round(N))
    O = O_in * 25.4
    tol = 1e-3

    shaft = _shaft(E, L)

    radial_diff = (O - E) / 2.0
    overlap = radial_diff * 0.20
    base_r = (E / 2.0) - overlap
    tip_r = O / 2.0
    y_base = tip_r - base_r          # 90deg included rib => Y-width == radial depth
    chamfer_len = tip_r - base_r

    p1 = FreeCAD.Vector(tip_r, 0, 0)
    p2 = FreeCAD.Vector(base_r, y_base, 0)
    p3 = FreeCAD.Vector(base_r, -y_base, 0)
    rib_face = Part.Face(Part.makePolygon([p1, p2, p3, p1]))
    rib_length = P - M
    rib_solid = rib_face.extrude(FreeCAD.Vector(0, 0, -rib_length))
    rib_solid.translate(FreeCAD.Vector(0, 0, -M))

    ribs = None
    for i in range(N):
        r = rib_solid.copy()
        r.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), i * (360.0 / N))
        ribs = r if ribs is None else ribs.fuse(r)

    env_mid = Part.makeCylinder(tip_r, rib_length - (2 * chamfer_len))
    env_mid.translate(FreeCAD.Vector(0, 0, -P + chamfer_len))
    env_top = Part.makeCone(tip_r, base_r, chamfer_len)
    env_top.translate(FreeCAD.Vector(0, 0, -M - chamfer_len))
    env_bot = Part.makeCone(base_r, tip_r, chamfer_len)
    env_bot.translate(FreeCAD.Vector(0, 0, -P))
    envelope = env_mid.fuse(env_top).fuse(env_bot)
    final_ribs = ribs.common(envelope)

    head = _dome_head(A, H)
    bolt = shaft.fuse(final_ribs).fuse(head)
    bolt = _fillet_underhead_and_rim(bolt, E, A, R)
    bolt = _add_thread(self, fa, bolt, E, tpi, L, L - P)
    return Part.Solid(bolt)


# =====================================================================
#  Table 5 — Round Head Fin Neck Bolts
# =====================================================================
def _make_5_5_finneck(self, fa):
    L = fa.calc_len
    (tpi, E_max, E_min, A_max, A_min, H_max, H_min,
     M_max, M_min, O_max, O_min, P_max, P_min, R) = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4
    H = _m(H_max, H_min) * 25.4
    M = _m(M_max, M_min) * 25.4    # fin thickness
    O = _m(O_max, O_min) * 25.4    # distance across fins
    P = _m(P_max, P_min) * 25.4    # fin depth
    R = R * 25.4

    shaft = _shaft(E, L)

    radial_diff = (O - E) / 2.0
    overlap = radial_diff * 0.10
    base_r = (E / 2.0) - overlap
    tip_r = O / 2.0

    v_tl = FreeCAD.Vector(base_r, M / 2.0, 0)
    v_tr = FreeCAD.Vector(base_r, -M / 2.0, 0)
    v_bot = FreeCAD.Vector(base_r, 0, -P)
    v_tip = FreeCAD.Vector(tip_r, 0, 0)
    f1 = Part.Face(Part.makePolygon([v_tl, v_tip, v_tr, v_tl]))
    f2 = Part.Face(Part.makePolygon([v_tl, v_tr, v_bot, v_tl]))
    f3 = Part.Face(Part.makePolygon([v_tl, v_bot, v_tip, v_tl]))
    f4 = Part.Face(Part.makePolygon([v_tr, v_tip, v_bot, v_tr]))
    fin_solid = Part.makeSolid(Part.makeShell([f1, f2, f3, f4]))
    fin2 = fin_solid.copy()
    fin2.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 180)
    fins = fin_solid.fuse(fin2)

    head = _dome_head(A, H)
    bolt = shaft.fuse(fins).fuse(head)
    bolt = _fillet_underhead_and_rim(bolt, E, A, R)
    bolt = _add_thread(self, fa, bolt, E, tpi, L, L - P)
    return Part.Solid(bolt)


# =====================================================================
#  Table 7 — Countersunk Bolts and Slotted Countersunk Bolts
# =====================================================================
def _make_5_7_countersunk(self, fa):
    L = fa.calc_len
    (tpi, E_max, E_min, A_max, A_min, F,
     H_max, H_min, J_max, J_min, T_max, T_min) = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4    # max edge-sharp head dia
    F = F * 25.4                    # cylindrical flat on min dia head
    J = _m(J_max, J_min) * 25.4    # slot width
    T = _m(T_max, T_min) * 25.4    # slot depth
    alpha = 82.0                    # 82deg head (macro default; 78deg alt available)
    has_slot = True                 # slot dims supplied; matches master macro
    bottom_chamfer = E * 0.1

    half_angle = math.radians(alpha / 2.0)
    cone_depth = ((A / 2.0) - (E / 2.0)) / math.tan(half_angle)
    H_calc = F + cone_depth

    head_flat = Part.makeCylinder(A / 2.0, F)
    head_flat.translate(FreeCAD.Vector(0, 0, -F))
    head_cone = Part.makeCone(E / 2.0, A / 2.0, cone_depth)
    head_cone.translate(FreeCAD.Vector(0, 0, -H_calc))
    head = head_flat.fuse(head_cone)

    if has_slot and J > 1e-4 and T > 1e-4:
        slot = Part.makeBox(A * 1.5, J, T * 2)
        slot.translate(FreeCAD.Vector(-A * 0.75, -J / 2.0, -T))
        head = head.cut(slot)

    shank_length = L - H_calc - bottom_chamfer
    shaft_main = Part.makeCylinder(E / 2.0, shank_length)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer))
    shaft_chamfer = Part.makeCone(E / 2.0 - bottom_chamfer, E / 2.0, bottom_chamfer)
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))
    shaft = shaft_main.fuse(shaft_chamfer)

    bolt = head.fuse(shaft).removeSplitter()
    bolt = _add_thread(self, fa, bolt, E, tpi, L, L - H_calc)
    return Part.Solid(bolt)


# =====================================================================
#  Table 8 — 114-deg Countersunk Square Neck Bolts
# =====================================================================
def _make_5_8_cs_squareneck(self, fa):
    L = fa.calc_len
    (tpi, E_max, E_min, A_max, A_min, F, H_max, H_min,
     O_max, O_min, AC, P_max, P_min, S, Q) = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4
    F = F * 25.4
    O = _m(O_max, O_min) * 25.4
    P = _m(P_max, P_min) * 25.4     # depth from end of countersink to shank start
    S = S * 25.4                     # height from top face to end of square corner
    Q = Q * 25.4
    alpha = 114.0
    tol = 1e-3
    bottom_chamfer = E * 0.1

    half_angle = math.radians(alpha / 2.0)
    cone_depth = ((A / 2.0) - (E / 2.0)) / math.tan(half_angle)
    H_calc = F + cone_depth
    total_neck_depth = H_calc + P
    R_actual = (O / 2.0 - Q) * math.sqrt(2) + Q

    head_flat = Part.makeCylinder(A / 2.0, F)
    head_flat.translate(FreeCAD.Vector(0, 0, -F))
    head_cone = Part.makeCone(E / 2.0, A / 2.0, cone_depth)
    head_cone.translate(FreeCAD.Vector(0, 0, -H_calc))
    head_raw = head_flat.fuse(head_cone)

    neck_cyl = Part.makeCylinder(R_actual, S)
    neck_cyl.translate(FreeCAD.Vector(0, 0, -S))
    taper_height = total_neck_depth - S
    neck_taper = Part.makeCone(E / 2.0, R_actual, taper_height)
    neck_taper.translate(FreeCAD.Vector(0, 0, -total_neck_depth))
    neck_raw = neck_cyl.fuse(neck_taper)

    box_margin = A * 2
    tool_h = total_neck_depth * 4
    outerBox = Part.makeBox(box_margin, box_margin, tool_h)
    outerBox.translate(FreeCAD.Vector(-box_margin / 2.0, -box_margin / 2.0, -total_neck_depth * 2))
    innerBox = Part.makeBox(O, O, tool_h + 2.0)
    innerBox.translate(FreeCAD.Vector(-O / 2.0, -O / 2.0, -total_neck_depth * 2 - 1.0))
    v_edges = [e for e in innerBox.Edges if abs(e.BoundBox.ZLength - (tool_h + 2.0)) < tol]
    if len(v_edges) == 4 and Q > 1e-4:
        innerBox = innerBox.makeFillet(Q, v_edges)
    tool = outerBox.cut(innerBox)
    neck_final = neck_raw.cut(tool)

    shank_length = L - total_neck_depth - bottom_chamfer
    shaft_main = Part.makeCylinder(E / 2.0, shank_length)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer))
    shaft_chamfer = Part.makeCone(E / 2.0 - bottom_chamfer, E / 2.0, bottom_chamfer)
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))
    shaft = shaft_main.fuse(shaft_chamfer)

    bolt = shaft.fuse(neck_final).fuse(head_raw).removeSplitter()
    bolt = _add_thread(self, fa, bolt, E, tpi, L, L - total_neck_depth)
    return Part.Solid(bolt)


# =====================================================================
#  Table 9 — Flat Countersunk Head Elevator Bolts
# =====================================================================
def _make_5_9_elevator(self, fa):
    L = fa.calc_len
    (tpi, E_max, E_min, A_max, A_min, Cangle, F, H_max, H_min,
     O_max, O_min, AC, P_max, P_min, S, Q, R) = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4     # max edge-sharp head dia
    F = F * 25.4
    H = _m(H_max, H_min) * 25.4
    O = _m(O_max, O_min) * 25.4
    P = _m(P_max, P_min) * 25.4
    Q = Q * 25.4
    R = R * 25.4
    taper_15 = 15.0
    tol = 1e-3
    bottom_chamfer = E * 0.1

    R_actual = (O / 2.0 - Q) * math.sqrt(2) + Q
    chamfer_drop = F / 2.0
    flat_end_depth = H + P
    tan_15 = math.tan(math.radians(taper_15))
    dz_corner_to_flat = (R_actual - (O / 2.0)) * tan_15
    taper_height = (R_actual - (E / 2.0)) * tan_15
    z_cone_top = -flat_end_depth + dz_corner_to_flat
    z_cone_bot = z_cone_top - taper_height

    # Head: revolved flat-countersunk profile (45deg approx outer rim)
    p1 = FreeCAD.Vector(0, 0, 0)
    p2 = FreeCAD.Vector(A / 2.0, 0, 0)
    p3 = FreeCAD.Vector(A / 2.0, 0, -F)
    p4 = FreeCAD.Vector(A / 2.0 - chamfer_drop, 0, -F - chamfer_drop)
    p5 = FreeCAD.Vector(E / 2.0, 0, -H)
    p6 = FreeCAD.Vector(0, 0, -H)
    face = Part.Face(Part.makePolygon([p1, p2, p3, p4, p5, p6, p1]))
    head_raw = face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360)

    neck_cyl = Part.makeCylinder(R_actual, abs(z_cone_top))
    neck_cyl.translate(FreeCAD.Vector(0, 0, z_cone_top))
    neck_taper = Part.makeCone(E / 2.0, R_actual, taper_height)
    neck_taper.translate(FreeCAD.Vector(0, 0, z_cone_bot))
    neck_raw = neck_cyl.fuse(neck_taper)

    box_margin = A * 2
    tool_h = abs(z_cone_bot) * 4
    outerBox = Part.makeBox(box_margin, box_margin, tool_h)
    outerBox.translate(FreeCAD.Vector(-box_margin / 2.0, -box_margin / 2.0, -tool_h / 2.0))
    innerBox = Part.makeBox(O, O, tool_h + 2.0)
    innerBox.translate(FreeCAD.Vector(-O / 2.0, -O / 2.0, -tool_h / 2.0 - 1.0))
    v_edges = [e for e in innerBox.Edges if abs(e.BoundBox.ZLength - (tool_h + 2.0)) < tol]
    if len(v_edges) == 4 and Q > 1e-4:
        innerBox = innerBox.makeFillet(Q, v_edges)
    tool = outerBox.cut(innerBox)
    neck_final = neck_raw.cut(tool)

    shank_length = L - abs(z_cone_bot) - bottom_chamfer
    shaft_main = Part.makeCylinder(E / 2.0, shank_length)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer))
    shaft_chamfer = Part.makeCone(E / 2.0 - bottom_chamfer, E / 2.0, bottom_chamfer)
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))
    shaft = shaft_main.fuse(shaft_chamfer)

    bolt = shaft.fuse(neck_final).fuse(head_raw).removeSplitter()

    # 'R' fillet at the under-head square/neck intersection
    inner_edges = []
    for e in bolt.Edges:
        bb = e.BoundBox
        z_mid = (bb.ZMin + bb.ZMax) / 2.0
        if -H < z_mid < -tol and bb.XMax < (O + tol) and bb.ZLength < (H - tol):
            inner_edges.append(e)
    try:
        bolt = bolt.makeFillet(R, inner_edges) if inner_edges else bolt
    except Exception as ex:
        FreeCAD.Console.PrintMessage(f"[B18.5] elevator fillet failed: {ex}\n")
    bolt = bolt.removeSplitter()

    bolt = _add_thread(self, fa, bolt, E, tpi, L, L - abs(z_cone_bot))
    return Part.Solid(bolt)


# =====================================================================
#  Table 10 — T-Head Bolts
# =====================================================================
def _make_5_10_thead(self, fa):
    L = fa.calc_len
    (tpi, E_max, E_min, A_max, A_min, B_max, B_min,
     H_max, H_min, K, R) = (float(v) for v in fa.dimTable)
    E = _m(E_max, E_min) * 25.4
    A = _m(A_max, A_min) * 25.4     # head length
    B = _m(B_max, B_min) * 25.4     # head width
    H = _m(H_max, H_min) * 25.4     # head height
    K = K * 25.4                     # basic head radius
    R = R * 25.4
    tol = 1e-3

    shaft = _shaft(E, L)

    head_box = Part.makeBox(A, B, H)
    head_box.translate(FreeCAD.Vector(-A / 2.0, -B / 2.0, 0))
    sphere_center = FreeCAD.Vector(0, 0, H - K)
    head_sphere = Part.makeSphere(K, sphere_center)
    head_final = head_box.common(head_sphere)

    bolt = shaft.fuse(head_final).removeSplitter()

    inner_edges = []
    for e in bolt.Edges:
        bb = e.BoundBox
        if abs(bb.ZMax) < tol and abs(bb.ZMin) < tol:
            if hasattr(e, 'Curve') and hasattr(e.Curve, 'Radius') and \
               abs(e.Curve.Radius - (E / 2.0)) < tol:
                inner_edges.append(e)
    try:
        bolt = bolt.makeFillet(R, inner_edges) if inner_edges else bolt
    except Exception as ex:
        FreeCAD.Console.PrintMessage(f"[B18.5] T-head fillet failed: {ex}\n")
    bolt = bolt.removeSplitter()

    bolt = _add_thread(self, fa, bolt, E, tpi, L, L)
    return Part.Solid(bolt)


_DISPATCH = {
    "ASMEB18.5.1":  _make_5_1_roundhead,
    "ASMEB18.5.3":  _make_square_neck,
    "ASMEB18.5.4":  _make_5_4_ribbedneck,
    "ASMEB18.5.5":  _make_5_5_finneck,
    "ASMEB18.5.6":  _make_square_neck,
    "ASMEB18.5.7":  _make_5_7_countersunk,
    "ASMEB18.5.8":  _make_5_8_cs_squareneck,
    "ASMEB18.5.9":  _make_5_9_elevator,
    "ASMEB18.5.10": _make_5_10_thead,
}
