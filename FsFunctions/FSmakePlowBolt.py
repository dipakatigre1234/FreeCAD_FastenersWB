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
        return _makeType3PlowBolt(fa, L)
    elif SType == "ASMEB18.9.7":
        return _makeType7PlowBolt(fa, L)
    else:
        raise NotImplementedError(f"Unknown plow bolt type: {SType}")


# ─────────────────────────────────────────────────────────────────────────
# Type 3
# ─────────────────────────────────────────────────────────────────────────
def _makeType3PlowBolt(fa, L):
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
    return Part.Solid(p_solid)


# ─────────────────────────────────────────────────────────────────────────
# Type 7
# ─────────────────────────────────────────────────────────────────────────
def _makeType7PlowBolt(fa, L):
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

    return Part.Solid(p_solid)
