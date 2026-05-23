# -*- coding: utf-8 -*-
"""
***************************************************************************
* FSmakePlowBolt.py                                                     *
* ASMEB18.9.3 — Type No. 3 Head Plow Bolt                                *
* *
* This file is a supplement to the FreeCAD CAx development system.      *
* *
* This program is free software; you can redistribute it and/or modify  *
* it under the terms of the GNU Lesser General Public License (LGPL)    *
* as published by the Free Software Foundation; either version 2 of     *
* the License, or (at your option) any later version.                   *
***************************************************************************
"""
import math
import FreeCAD
import Part
from screw_maker import *


def makePlowBolt(self, fa):
    """Create a Type No. 3 Head Plow Bolt (ASME B18.9.3).

    Geometry follows the reference macro: flat 82° countersunk head with
    a flat cylindrical margin, square neck with conical taper at its base,
    and a cylindrical shaft with a chamfered tip.

    Mean (max+min)/2 values are taken from the ASMEB18.9.3def CSV row
    for the selected nominal diameter. All CSV values are in inches and
    are converted to millimetres.
    """
    L = fa.calc_len  # mm, user-selected length

    # ── Unpack dimTable (inch values from asmeb18.9.3.csv) ────────────────
    (e_max, e_min,
     a_max, a_min_sharp, a_abs_min,
     f_max,
     s_max, s_min,
     t_min,
     b_max, b_min,
     ac_min,
     r_max) = fa.dimTable

    # ── Mean dimensions (inch → mm) ───────────────────────────────────────
    d        = ((e_max + e_min) / 2.0) * 25.4   # Body / nominal diameter
    A        = ((a_max + a_min_sharp) / 2.0) * 25.4   # Head diameter
    F        = f_max * 25.4                     # Cylindrical margin thickness
    S        = ((s_max + s_min) / 2.0) * 25.4   # Total square-neck depth
    B        = ((b_max + b_min) / 2.0) * 25.4   # Width across square
    R_corner = r_max * 25.4                     # Square-corner fillet

    angle = 41.0                                # Half-angle of 82° csk
    bottom_chamfer_size = d / 10.0              # Shaft-tip chamfer

    # ── Shaft with bottom chamfer ─────────────────────────────────────────
    shaft_main = Part.makeCylinder(d / 2, L - bottom_chamfer_size)
    shaft_main.translate(FreeCAD.Vector(0, 0, -L + bottom_chamfer_size))

    shaft_chamfer = Part.makeCone(
        d / 2 - bottom_chamfer_size, d / 2, bottom_chamfer_size
    )
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -L))

    shaft = shaft_main.fuse(shaft_chamfer)

    # ── Flat countersink head (with straight cylindrical margin) ──────────
    # 1. Cylindrical margin at the top (Z = 0 down to Z = -F)
    head_margin = Part.makeCylinder(A / 2, F)
    head_margin.translate(FreeCAD.Vector(0, 0, -F))

    # 2. Conical part of the head (Z = -F down to Z = -(F + H_cone))
    H_cone = (A / 2 - d / 2) / math.tan(math.radians(angle))
    head_cone = Part.makeCone(d / 2, A / 2, H_cone)
    head_cone.translate(FreeCAD.Vector(0, 0, -(F + H_cone)))

    head_full = head_margin.fuse(head_cone)

    # ── Square neck with conical bottom taper ─────────────────────────────
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

    # ── Final assembly ────────────────────────────────────────────────────
    p_solid = shaft.fuse(neck_final).fuse(head_full)
    p_solid = p_solid.removeSplitter()

    return Part.Solid(p_solid)
