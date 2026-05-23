# -*- coding: utf-8 -*-
"""
***************************************************************************
*   FSmakePlowBolt.py                                                     *
*   ASMEB18.9.3 — Type No. 3 Head Plow Bolt                                *
*   ASMEB18.9.7 — Type No. 7 Head Plow Bolt (reverse-key head)             *
*                                                                         *
*   This file is a supplement to the FreeCAD CAx development system.      *
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU Lesser General Public License (LGPL)    *
*   as published by the Free Software Foundation; either version 2 of     *
*   the License, or (at your option) any later version.                   *
***************************************************************************
"""
from screw_maker import *


def makePlowBolt(self, fa):
    """Create a Type-3 or Type-7 Head Plow Bolt.

    Both bolts share the same chamfered cylindrical shaft. The head and
    neck/key feature differ:

      - ASMEB18.9.3  Type 3: 82° flat countersunk head with a chamfered
                     top edge and a square neck (with conical taper) on
                     the bottom of the head.
      - ASMEB18.9.7  Type 7: cylindrical flat margin (height F) over a
                     countersunk cone (height S-F), with a reverse key
                     protruding from the top.

    Mean (max+min)/2 values are read from the relevant CSV row for the
    selected nominal diameter. All CSV values are inches; converted to mm.
    """
    SType = fa.baseType
    L     = fa.calc_len   # mm, user-selected length

    if SType == "ASMEB18.9.3":
        return _makeType3PlowBolt(self, fa, L)
    elif SType == "ASMEB18.9.4":
        return _makeType4PlowBolt(self, fa, L)
    elif SType == "ASMEB18.9.5":
        return _makeType5PlowBolt(self, fa, L)
    elif SType == "ASMEB18.9.6":
        return _makeType6PlowBolt(self, fa, L)
    elif SType == "ASMEB18.9.7":
        return _makeType7PlowBolt(self, fa, L)
    else:
        raise NotImplementedError(f"Unknown plow bolt type: {SType}")


# ─────────────────────────────────────────────────────────────────────────
# UNC TPI table for plow bolts (ASME B18.9 standard threads)
# ─────────────────────────────────────────────────────────────────────────
_PLOW_UNC_TPI = {
    "5/16in": 18,
    "3/8in":  16,
    "7/16in": 14,
    "1/2in":  13,
    "9/16in": 12,
    "5/8in":  11,
    "3/4in":  10,
    "7/8in":   9,
    "1in":     8,
}


def _apply_plow_threads(screw, fa, p_solid, d_body, length):
    """Cut UNC threads on the bottom portion of the shaft.

    Thread length follows ASME B18.9 Table 7 — Minimum Thread Lengths of
    Plow Bolts:  L_t = 2D + 0.25in, where D is the **nominal** bolt
    diameter (not the body diameter `e`). For short bolts where the
    computed L_t would exceed the available shaft, the thread runs all
    the way up to the head ("T to H" — threaded to head).

    Honors dashboard overrides: calc_pitch, calc_tpi, calc_thread_length.
    """
    if not getattr(fa, "Thread", False):
        return p_solid

    diam_key = str(fa.calc_diam)
    tpi_tbl = _PLOW_UNC_TPI.get(diam_key)
    if tpi_tbl is None:
        FreeCAD.Console.PrintWarning(
            f"PlowBolt: no UNC TPI for {diam_key}, skipping threads\n"
        )
        return p_solid

    P_tbl = 25.4 / tpi_tbl

    # Nominal diameter D in mm (from DiaList, e.g. 1/2in -> 12.7mm).
    # The ASME Table 7 formula 2D + 0.25in uses nominal D, not body dia.
    D_nominal = screw.getDia(fa.calc_diam, False)

    # ASME B18.9 Table 7: L_t = 2D + 0.25 in (=6.35 mm) for all bolt lengths.
    L_t = 2.0 * D_nominal + 6.35

    # Dashboard overrides
    raw_pitch = getattr(fa, "calc_pitch", None)
    pitch = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        L_t = min(float(raw_tlen), length)
    else:
        # "T to H" rule: if 2D+0.25 ≥ available shaft, thread up to the head.
        L_t = min(L_t, length)

    tpi = getattr(fa, "calc_tpi", None)
    if not tpi or tpi <= 0:
        tpi = tpi_tbl
    thread_dia = d_body - (0.15 / tpi)

    FreeCAD.Console.PrintMessage(
        f"[PlowBolt] Threading (ASME B18.9 Table 7): "
        f"D_nom={D_nominal:.4f}mm, body={d_body:.4f}mm, "
        f"thread_dia={thread_dia:.4f}mm, TPI={tpi}, "
        f"pitch={pitch:.4f}mm, thread_length={L_t:.2f}mm "
        f"(2D+0.25in = {2.0 * D_nominal + 6.35:.2f}mm)\n"
    )

    thread_cutter = screw.CreateBlindThreadCutter(thread_dia, pitch, L_t)
    thread_cutter.translate(FreeCAD.Vector(0.0, 0.0, -1 * (length - L_t)))
    return p_solid.cut(thread_cutter)


# ─────────────────────────────────────────────────────────────────────────
# Type 3
# ─────────────────────────────────────────────────────────────────────────
def _makeType3PlowBolt(self, fa, L):
    # Unpack ASMEB18.9.3def: e_max,e_min,a_max,a_min_sharp,a_abs_min,
    # f_max,s_max,s_min,t_min,b_max,b_min,ac_min,r_max
    (e_max, e_min,
     a_max, a_min_sharp, a_abs_min,
     f_max,
     s_max, s_min,
     t_min,
     b_max, b_min,
     ac_min,
     r_max) = fa.dimTable

    d        = ((e_max + e_min) / 2.0) * 25.4
    A        = ((a_max + a_min_sharp) / 2.0) * 25.4
    S        = ((s_max + s_min) / 2.0) * 25.4
    B        = ((b_max + b_min) / 2.0) * 25.4
    R_corner = r_max * 25.4

    angle = 41.0
    bottom_chamfer_size = d / 10.0
    top_chamfer_size    = d / 15.0

    # Shaft with bottom chamfer
    shaft_main = Part.makeCylinder(d / 2, L - bottom_chamfer_size)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer_size))
    shaft_chamfer = Part.makeCone(
        d / 2 - bottom_chamfer_size, d / 2, bottom_chamfer_size
    )
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))
    shaft = shaft_main.fuse(shaft_chamfer)

    # Flat countersink head with top chamfer
    H_cone = (A / 2 - d / 2) / math.tan(math.radians(angle))
    head_cone = Part.makeCone(d / 2, A / 2, H_cone)
    head_cone.translate(FreeCAD.Vector(0, 0, -H_cone))
    top_edges = [
        edge for edge in head_cone.Edges
        if abs(edge.CenterOfMass.z) < 0.001
    ]
    if top_edges:
        head_cone = head_cone.makeChamfer(top_chamfer_size, top_edges)

    # Square neck with conical bottom taper
    R_diag  = (B / math.sqrt(2)) + 0.5
    H_taper = R_diag - d / 2
    neck_cyl = Part.makeCylinder(R_diag, S - H_taper)
    neck_cyl.translate(FreeCAD.Vector(0, 0, -S + H_taper))
    neck_taper = Part.makeCone(d / 2, R_diag, H_taper)
    neck_taper.translate(FreeCAD.Vector(0, 0, -S))
    neck_raw = neck_cyl.fuse(neck_taper)

    outerBox = Part.makeBox(A * 4, A * 4, S * 3)
    outerBox.translate(FreeCAD.Vector(-A * 2, -A * 2, -S * 2))
    innerBox = Part.makeBox(B, B, S * 4)
    innerBox.translate(FreeCAD.Vector(-B / 2, -B / 2, -S * 2.5))
    vertical_edges = [
        edge for edge in innerBox.Edges
        if abs(edge.BoundBox.ZLength - S * 4) < 0.01
    ]
    if vertical_edges:
        innerBox = innerBox.makeFillet(R_corner, vertical_edges)
    tool = outerBox.cut(innerBox)
    neck_final = neck_raw.cut(tool)

    p_solid = shaft.fuse(neck_final).fuse(head_cone)
    p_solid = p_solid.removeSplitter()

    p_solid = _apply_plow_threads(self, fa, p_solid, d, L)
    return Part.Solid(p_solid)


# ─────────────────────────────────────────────────────────────────────────
# Type 4 — Repair Head Plow Bolt (square pyramid head with flat margin)
# ─────────────────────────────────────────────────────────────────────────
def _makeType4PlowBolt(self, fa, L):
    # Same column layout as ASMEB18.9.3def
    (e_max, e_min,
     a_max, a_min_sharp, a_abs_min,
     f_max,
     s_max, s_min,
     t_min,
     b_max, b_min,
     ac_min,
     r_max) = fa.dimTable

    d = ((e_max + e_min) / 2.0) * 25.4
    A = ((a_max + a_min_sharp) / 2.0) * 25.4   # Width of square head
    F = f_max * 25.4                           # Feed (flat margin) thickness

    angle_included = 82.0
    angle_rad      = math.radians(angle_included / 2.0)
    H_apex         = (A / 2.0) / math.tan(angle_rad)

    bottom_chamfer_size = d / 10.0

    # Shaft with bottom chamfer
    shaft_main = Part.makeCylinder(d / 2, L - bottom_chamfer_size)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer_size))
    shaft_chamfer = Part.makeCone(
        d / 2 - bottom_chamfer_size, d / 2, bottom_chamfer_size
    )
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))
    shaft = shaft_main.fuse(shaft_chamfer)

    # Square head margin (Feed thickness F)
    head_flat = Part.makeBox(A, A, F)
    head_flat.translate(FreeCAD.Vector(-A / 2, -A / 2, -F))

    # Deep tapered pyramid frustum (lofted square wires)
    def _square_wire(width, z):
        w = width / 2.0
        p1 = FreeCAD.Vector(-w, -w, z)
        p2 = FreeCAD.Vector( w, -w, z)
        p3 = FreeCAD.Vector( w,  w, z)
        p4 = FreeCAD.Vector(-w,  w, z)
        return Part.makePolygon([p1, p2, p3, p4, p1])

    top_wire    = _square_wire(A,    -F)
    bottom_wire = _square_wire(0.01, -F - H_apex)
    pyramid_taper = Part.makeLoft([top_wire, bottom_wire], True)

    # Final assembly
    p_solid = shaft.fuse(pyramid_taper).fuse(head_flat)
    p_solid = p_solid.removeSplitter()

    p_solid = _apply_plow_threads(self, fa, p_solid, d, L)
    return Part.Solid(p_solid)


# ─────────────────────────────────────────────────────────────────────────
# Type 5 — Clipped Head Plow Bolt
# Three-zone revolved head (top chamfer, 22° countersink, 40° bottom taper),
# then clipped to width B across two parallel flats.
# ─────────────────────────────────────────────────────────────────────────
def _makeType5PlowBolt(self, fa, L):
    # ASMEB18.9.5def: e_max,e_min,a_max,a_min,c_max,c_min,h_max,h_min
    (e_max, e_min,
     a_max, a_min,
     c_max, c_min,
     h_max, h_min) = fa.dimTable

    d = ((e_max + e_min) / 2.0) * 25.4
    A = ((a_max + a_min) / 2.0) * 25.4   # Outer head diameter
    B = ((c_max + c_min) / 2.0) * 25.4   # Width across clipped flats
    H = ((h_max + h_min) / 2.0) * 25.4   # Total head height

    P_angle_deg       = 40.0   # Bottom taper angle (per spec)
    countersink_angle = 22.0   # Top countersink (fixed)
    top_chamfer       = 0.03 * 25.4

    R_top = A / 2.0
    R_bot = d / 2.0

    tan_alpha = math.tan(math.radians(countersink_angle / 2.0))
    tan_P     = math.tan(math.radians(P_angle_deg))

    # Solve for the Z and R at which the 22° countersink meets the 40° taper.
    numerator   = R_top - R_bot - (H * tan_P) + (top_chamfer * tan_alpha)
    denominator = tan_P - tan_alpha
    Z_int = numerator / denominator
    R_int = R_top + (Z_int + top_chamfer) * tan_alpha

    # ── 2D revolve profile ────────────────────────────────────────────────
    p0 = FreeCAD.Vector(0,                       0, 0)
    p1 = FreeCAD.Vector(R_top - top_chamfer,     0, 0)
    p2 = FreeCAD.Vector(R_top,                   0, -top_chamfer)
    p3 = FreeCAD.Vector(R_int,                   0, Z_int)
    p4 = FreeCAD.Vector(R_bot,                   0, -H)
    p5 = FreeCAD.Vector(0,                       0, -H)

    wire = Part.makePolygon([p0, p1, p2, p3, p4, p5, p0])
    face = Part.Face(wire)
    head_solid = face.revolve(
        FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360
    )

    # ── Clip two parallel flats to width B ────────────────────────────────
    box_len = A * 3
    box_h   = H * 3
    clip_box = Part.makeBox(box_len, B, box_h)
    clip_box.translate(FreeCAD.Vector(-box_len / 2.0, -B / 2.0, -H * 1.5))
    head_clipped = head_solid.common(clip_box)

    # ── Shaft + entry chamfer ─────────────────────────────────────────────
    bot_chamfer_height = 0.05 * 25.4
    bot_chamfer_depth  = 0.03 * 25.4

    shaft_length = L - H - bot_chamfer_height
    shaft = Part.makeCylinder(d / 2.0, shaft_length)
    shaft.translate(FreeCAD.Vector(0, 0, -L + bot_chamfer_height))

    chamfer = Part.makeCone(
        (d / 2.0) - bot_chamfer_depth, d / 2.0, bot_chamfer_height
    )
    chamfer.translate(FreeCAD.Vector(0, 0, -L))

    p_solid = head_clipped.fuse(shaft).fuse(chamfer).removeSplitter()

    p_solid = _apply_plow_threads(self, fa, p_solid, d, L)
    return Part.Solid(p_solid)


# ─────────────────────────────────────────────────────────────────────────
# Type 6 — Head Plow Bolt (cone+margin head with side triangular key)
# ─────────────────────────────────────────────────────────────────────────
def _makeType6PlowBolt(self, fa, L):
    # Same column layout as ASMEB18.9.7def
    (e_max, e_min,
     a_max, a_min_sharp, a_abs_min,
     f_max,
     s_max, s_min,
     g_max, g_min) = fa.dimTable

    d = ((e_max + e_min) / 2.0) * 25.4
    A = ((a_max + a_min_sharp) / 2.0) * 25.4   # Head diameter
    F = f_max * 25.4                            # Margin (feed) thickness
    H = ((g_max + g_min) / 2.0) * 25.4          # Total head height (incl. cone)
    J = ((s_max + s_min) / 2.0) * 25.4          # Triangular key width
    P = 0.100 * 25.4                            # Key radial protrusion (fixed)

    # Chamfer parameters from macro
    chamfer_height = 0.05 * 25.4
    chamfer_depth  = 0.03 * 25.4

    # Head conical geometry (42° included angle)
    angle_included  = 42.0
    half_angle      = math.radians(angle_included / 2.0)
    conical_height  = H - F
    R_bottom        = (A / 2.0) - (conical_height * math.tan(half_angle))

    # ── Shaft + entry chamfer ─────────────────────────────────────────────
    shaft = Part.makeCylinder(d / 2, L - chamfer_height)
    shaft.translate(FreeCAD.Vector(0, 0, -(L - chamfer_height)))

    chamfer = Part.makeCone(d / 2 - chamfer_depth, d / 2, chamfer_height)
    chamfer.translate(FreeCAD.Vector(0, 0, -L))

    # ── Head: flat cylindrical margin + tapered cone underneath ───────────
    head_flat = Part.makeCylinder(A / 2, F)
    head_flat.translate(FreeCAD.Vector(0, 0, -F))

    head_cone = Part.makeCone(R_bottom, A / 2, conical_height)
    head_cone.translate(FreeCAD.Vector(0, 0, -H))

    main_body = shaft.fuse(chamfer).fuse(head_cone).fuse(head_flat)

    # ── Triangular key (lofted from bottom triangle to top triangle) ──────
    overlap = 0.05 * 25.4  # small overlap so the key fuses cleanly into head

    # Bottom triangle at Z = -H (touches cone bottom radius)
    p1_b = FreeCAD.Vector(-(R_bottom + P),      0,         -H)
    p2_b = FreeCAD.Vector(-(R_bottom - overlap),  J / 2.0, -H)
    p3_b = FreeCAD.Vector(-(R_bottom - overlap), -J / 2.0, -H)
    bottom_wire = Part.makePolygon([p1_b, p2_b, p3_b, p1_b])

    # Top triangle at Z = 0 (touches outer head radius)
    p1_t = FreeCAD.Vector(-(A / 2.0 + P),      0,         0)
    p2_t = FreeCAD.Vector(-(A / 2.0 - overlap),  J / 2.0, 0)
    p3_t = FreeCAD.Vector(-(A / 2.0 - overlap), -J / 2.0, 0)
    top_wire = Part.makePolygon([p1_t, p2_t, p3_t, p1_t])

    key_solid = Part.makeLoft([bottom_wire, top_wire], True)

    # ── Final fusion + thread cut ─────────────────────────────────────────
    p_solid = main_body.fuse(key_solid).removeSplitter()

    p_solid = _apply_plow_threads(self, fa, p_solid, d, L)
    return Part.Solid(p_solid)


# ─────────────────────────────────────────────────────────────────────────
# Type 7
# ─────────────────────────────────────────────────────────────────────────
def _makeType7PlowBolt(self, fa, L):
    # Unpack ASMEB18.9.7def: e_max,e_min,a_max,a_min_sharp,a_abs_min,
    # f_max,s_max,s_min,g_max,g_min
    (e_max, e_min,
     a_max, a_min_sharp, a_abs_min,
     f_max,
     s_max, s_min,
     g_max, g_min) = fa.dimTable

    d = ((e_max + e_min) / 2.0) * 25.4
    A = ((a_max + a_min_sharp) / 2.0) * 25.4
    S = ((s_max + s_min) / 2.0) * 25.4
    G = ((g_max + g_min) / 2.0) * 25.4
    F = f_max * 25.4
    W_k = 0.151 * 25.4   # Key width, fixed (per macro)

    bottom_chamfer_size = d / 10.0
    inner_seam_fillet   = 0.020 * 25.4

    # Shaft with bottom chamfer
    shaft_main = Part.makeCylinder(d / 2, L - bottom_chamfer_size)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer_size))
    shaft_chamfer = Part.makeCone(
        d / 2 - bottom_chamfer_size, d / 2, bottom_chamfer_size
    )
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))
    shaft = shaft_main.fuse(shaft_chamfer)

    # Countersunk head with parallel flat margin
    head_flat = Part.makeCylinder(A / 2, F)
    head_flat.translate(FreeCAD.Vector(0, 0, -F))
    head_cone = Part.makeCone(d / 2, A / 2, S - F)
    head_cone.translate(FreeCAD.Vector(0, 0, -S))

    # Reverse key (rotated 90° so seam lies on smooth face)
    key_cyl = Part.makeCylinder(A / 2, F)
    key_cyl.translate(FreeCAD.Vector(0, 0, -F))
    key_cyl.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90)

    taper_height = G - F
    bottom_radius_3deg = A / 2 - taper_height * math.tan(math.radians(3))
    key_cone = Part.makeCone(bottom_radius_3deg, A / 2, taper_height)
    key_cone.translate(FreeCAD.Vector(0, 0, -G))
    key_cone.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90)

    key_outer_profile = key_cyl.fuse(key_cone)
    key_outer_profile = key_outer_profile.removeSplitter()

    key_box = Part.makeBox(A, W_k, G)
    key_box.translate(FreeCAD.Vector(0, -W_k / 2, -G))
    key_solid = key_outer_profile.common(key_box)

    # Fuse everything
    p_solid = shaft.fuse(head_cone).fuse(head_flat).fuse(key_solid)
    p_solid = p_solid.removeSplitter()

    # Selective fillets on the key seams
    cone_r_at_G = (A / 2) - ((A / 2 - d / 2) * (G - F) / (S - F))
    threshold_X = (cone_r_at_G + A / 2) / 2.0

    edges_to_fillet = []
    for edge in p_solid.Edges:
        bbox = edge.BoundBox

        # Target 1: Left & right vertical inner seams
        if bbox.YLength < 0.05 and bbox.ZLength > 0.5:
            if abs(abs(bbox.YMin) - W_k / 2) < 0.05:
                if bbox.XMax < threshold_X:
                    edges_to_fillet.append(edge)

        # Target 2: Bottom horizontal INNER shelf seam
        if bbox.ZLength < 0.05 and bbox.YLength > (W_k * 0.5):
            if abs(bbox.ZMin - (-G)) < 0.05:
                if bbox.XMax < threshold_X:
                    edges_to_fillet.append(edge)

        # Target 3: Bottom horizontal OUTER lip
        if bbox.ZLength < 0.05 and bbox.YLength > (W_k * 0.5):
            if abs(bbox.ZMin - (-G)) < 0.05:
                if bbox.XMax > threshold_X:
                    edges_to_fillet.append(edge)

    if edges_to_fillet:
        try:
            p_solid = p_solid.makeFillet(inner_seam_fillet, edges_to_fillet)
        except Exception:
            FreeCAD.Console.PrintWarning(
                "PlowBolt Type 7: fillet failed (topology too tight)\n"
            )

    p_solid = _apply_plow_threads(self, fa, p_solid, d, L)
    return Part.Solid(p_solid)
