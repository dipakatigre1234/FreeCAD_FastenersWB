# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2024                                                    *
*   Original code by:                                                     *
*   hasecilu <hasecilu[at]tuta.io>                                        *
*                                                                         *
*   This file is a supplement to the FreeCAD CAx development system.      *
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU Lesser General Public License (LGPL)    *
*   as published by the Free Software Foundation; either version 2 of     *
*   the License, or (at your option) any later version.                   *
*   for detail see the LICENCE text file.                                 *
*                                                                         *
*   This software is distributed in the hope that it will be useful,      *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
*   GNU Library General Public License for more details.                  *
*                                                                         *
*   You should have received a copy of the GNU Library General Public     *
*   License along with this macro; if not, write to the Free Software     *
*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
*   USA                                                                   *
*                                                                         *
***************************************************************************
"""

import math
import Part
from FreeCAD import Base
from screw_maker import FsData
from FastenerBase import FSFaceMaker

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)
import FSThreadingMetric as _TM


def makeThumbScrew(self, fa):
    """Create a thumb screw.

    Supported types:
    - DIN 464: Knurled thumb screws, high type
    - DIN 465: Knurled thumb screws
    - DIN 653: Flat knurled thumb screws
    - WOOTZ_ADJ_BREMS: Custom adjustment screw (knurled head, stepped shank,
                       DIN 6799 4mm retaining-clip groove, hemispherical tip)
    """
    SType = fa.baseType

    # Fixed-geometry types: return immediately before any CSV/dim lookups.
    if SType == "WOOTZ_ADJ_BREMS":
        return _makeAdjustmentScrew(self, fa)

    length = fa.calc_len
    dia = self.getDia(fa.calc_diam, False)
    P = FsData["ISO262def"][fa.Diameter][0]

    # Match the newer FsMake files: dashboard pitch override wins.
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) else P
    d_eff = _TM.get_shank_dia(fa, dia)

    if SType in ["DIN464", "DIN465"]:
        _, c, dk, _, _, ds, _, h, _, _, k, _, n, _, _, r, t, _, _, knurl = fa.dimTable
        kn0 = h - k
        kn = k
        # NOTE: The required undercut needed is "Gewindefreistich DIN 76 - A" Regelfall
        # roundness for P from 1 to 2 is 0.6 => rr = 0.6
        g = self.getDia1(dia, P)
        rr = 0.6
        f1 = 3 * P
        f2 = 4.5 * P
        fm = FSFaceMaker()
        fm.AddPoint(0.0, h)
        if fa.Diameter in ["M1", "M1.2", "M1.4", "M1.6", "M2"]:
            fm.AddPoint(dk / 2, h)
            fm.AddPoint(dk / 2, h - k)
        else:
            fm.AddPoint(dk / 2 - c, h)
            fm.AddPoint(dk / 2, h - c)
            fm.AddPoint(dk / 2, h - k + c)
            fm.AddPoint(dk / 2 - c, h - k)
        fm.AddPoint(ds / 2 + r, h - k)
        fm.AddArc2(0.0, -r, 90)
        fm.AddPoint(ds / 2, 0.0)
        fm.AddPoint(g / 2 + rr, 0.0)
        fm.AddArc2(0.0, -rr, 90)
        fm.AddPoint(g / 2, -f1)
        fm.AddPoint(d_eff / 2, -f2)
        fm.AddPoint(d_eff / 2, -length + d_eff / 10)
        fm.AddPoint(d_eff / 2 - d_eff / 10, -length)
        fm.AddPoint(0.0, -length)
        thread_dz = -f1
        thread_l = length - f1
    elif SType == "DIN653":
        _, c, dk, _, _, ds, _, e, k, _, r, knurl = fa.dimTable
        kn0 = e
        kn = k
        # NOTE: The required undercut needed is "Gewindefreistich DIN 76 - A" Regelfall
        g = self.getDia1(dia, P)
        rr = (dia - g) / 2  # 0.6 from table doesn't work
        f1 = 3 * P
        f2 = 4.5 * P
        fm = FSFaceMaker()
        # Head
        if fa.Diameter in ["M1", "M1.2", "M1.4", "M1.6", "M2"]:
            if fa.Diameter != "M2":
                kn0 = 0
                fm.AddPoint(0.0, k)
                fm.AddPoint(dk / 2, k)
                fm.AddPoint(dk / 2, 0)
            else:
                fm.AddPoint(0.0, k + e)
                fm.AddPoint(dk / 2, k + e)
                fm.AddPoint(dk / 2, e)
        else:
            fm.AddPoint(0.0, k + e)
            fm.AddPoint(dk / 2 - c, k + e)
            fm.AddPoint(dk / 2, k + e - c)
            fm.AddPoint(dk / 2, e + c)
            fm.AddPoint(dk / 2 - c, e)
        # Shoulder
        if fa.Diameter not in ["M1", "M1.2", "M1.4", "M1.6"]:
            fm.AddPoint(ds / 2 + r, e)
            fm.AddArc2(0.0, -r, 90)
            fm.AddPoint(ds / 2, 0.0)
        # Shaft
        if fa.Diameter in ["M1", "M1.2", "M1.4", "M1.6"]:
            fm.AddPoint(d_eff / 2 + r, 0.0)
            fm.AddArc2(0.0, -r, 90)
            fm.AddPoint(d_eff / 2, -length + d_eff / 10)
            fm.AddPoint(d_eff * 4 / 10, -length)
            fm.AddPoint(0.0, -length)
            thread_dz = 0
            thread_l = length
        else:
            fm.AddArc2(0.0, -rr, 90)
            fm.AddPoint(g / 2, -f1)
            fm.AddPoint(d_eff / 2, -f2)
            fm.AddPoint(d_eff / 2, -length + d_eff / 10)
            fm.AddPoint(d_eff / 2 - d_eff / 10, -length)
            fm.AddPoint(0.0, -length)
            thread_dz = -f1
            thread_l = length - f1
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    screw = self.RevolveZ(fm.GetFace())

    # Make recess
    if SType == "DIN465":
        recess = self.makeSlotRecess(n, t, dk)
        recess.translate(Base.Vector(0.0, 0.0, h))
        screw = screw.cut(recess)

    # produce a modelled knurling & thread if necessary
    if fa.Thread:
        knurling_cutter = straightCutter(dk, 0.975 * dk, kn0, kn)
        screw = screw.cut(knurling_cutter)
        screw = _TM.cut_thread(screw, fa, d_eff, thread_l, thread_dz, P)

    return screw


def straightCutter(outDia: float, inDia: float, zbase: float, height: float):
    """Cut a circular array of triangular prisms to obtain a straight knurling."""
    # TODO: Make Screw.CreateKnurlCutter() accepts straight knurling
    # Knurling should be DIN 82 RAA

    # create base triangle, angle is 90 deg
    d2 = outDia - inDia / 2.0
    y2 = d2 - inDia / 2.0
    p1 = Base.Vector(inDia / 2.0, 0, 0)
    p2 = Base.Vector(d2, y2, 0)
    p3 = Base.Vector(d2, -y2, 0)
    l1 = Part.makeLine(p1, p2)
    l2 = Part.makeLine(p2, p3)
    l3 = Part.makeLine(p3, p1)
    w = Part.Wire([l1, l2, l3])
    face = Part.Face(w)
    cutElement = face.extrude(Base.Vector(0.0, 0.0, height))
    cutElement.translate(Base.Vector(0.0, 0, zbase))

    # FIXME: Ideally the number of elements should be greater
    # to avoid having "gaps" between cuts. Good enough for now.
    cutElements = [cutElement]
    ang = math.atan(y2 / d2) * 114.6  # 2 * 180 / pi
    numCuts = int(360.0 / ang)
    elementAng = 360 / numCuts

    for i in range(1, numCuts):
        nextElement = cutElement.copy().rotate(
            Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), i * elementAng
        )
        cutElements.append(nextElement)
    cutTool = Part.Compound(cutElements)
    return cutTool


# =============================================================================
#  WOOTZ — Adjustment Screw "Skrue Justering Sl. Brems" (P/N 717090)
#
#  Geometry (all mm):
#    Head : OD=20, H=4, chamfer 1x45 top+bottom, R1 under-head fillet
#    Shank: D=6 (M6), total length ~33mm from head underside to sphere apex
#    Tip  : D5 cylinder (1.7mm), groove D4.2 x 0.8mm, 0.5x45 chamfer to D6
#           R5 spherical cap at tip apex
#
#  Origin: sphere apex at z = tip_z = -33.0.  Head top at z = +head_thick.
# =============================================================================

# Fixed dimensions
_ADJ_HEAD_OD      = 20.0   # head outside diameter
_ADJ_HEAD_H       = 4.0    # head height
_ADJ_HEAD_CHAMFER = 1.0    # chamfer size (1x45 deg on top and bottom)
_ADJ_FILLET_R     = 1.0    # R1 under-head fillet radius
_ADJ_SHAFT_D      = 6.0    # main shank diameter (M6)
_ADJ_TIP_Z        = -33.0  # absolute z of sphere apex
_ADJ_SPHERE_R     = 5.0    # R5 spherical tip radius
_ADJ_TIP_CYL_D    = 5.0    # tip cylinder diameter
_ADJ_GROOVE_W     = 0.80   # DIN 6799 clip groove axial width
_ADJ_GROOVE_ID    = 4.20   # clip groove diameter
_ADJ_CHAMFER_W    = 0.50   # axial width of 0.5x45 chamfer groove->shank


def _makeAdjustmentScrew(_screw_maker, fa):
    """Build WOOTZ_ADJ_BREMS using direct Part.Arc edges + face.revolve().

    Profile traces from sphere apex upward to head top, then closes along axis.
    Matches the reference macro exactly.  M6 thread applied when fa.Thread=True.
    """
    head_OD      = _ADJ_HEAD_OD
    head_thick   = _ADJ_HEAD_H
    c            = _ADJ_HEAD_CHAMFER
    fillet_R     = _ADJ_FILLET_R
    shaft_D      = _ADJ_SHAFT_D
    tip_z        = _ADJ_TIP_Z
    sphere_R     = _ADJ_SPHERE_R
    tip_cyl_D    = _ADJ_TIP_CYL_D
    groove_W     = _ADJ_GROOVE_W
    groove_ID    = _ADJ_GROOVE_ID
    chamfer_W    = _ADJ_CHAMFER_W

    # Section z-coordinates (same formulas as the reference macro)
    groove_bot_z       = tip_z + 1.7
    sphere_center_z    = tip_z + sphere_R
    sphere_intersect_z = sphere_center_z - math.sqrt(
        sphere_R ** 2 - (tip_cyl_D / 2.0) ** 2
    )
    groove_top_z  = groove_bot_z + groove_W
    chamfer_top_z = groove_top_z + chamfer_W

    def pt(x, z):
        return Base.Vector(x, 0.0, z)

    edges = []

    # E1: R5 spherical cap — apex (0, tip_z) to (r_tip, sphere_intersect_z)
    mid_ang = math.radians(15.0)
    mid_x   = sphere_R * math.sin(mid_ang)
    mid_z   = sphere_center_z - sphere_R * math.cos(mid_ang)
    edges.append(Part.Arc(
        pt(0.0,            tip_z),
        pt(mid_x,          mid_z),
        pt(tip_cyl_D / 2,  sphere_intersect_z),
    ).toShape())

    # E2: Tip cylinder wall
    edges.append(Part.makeLine(
        pt(tip_cyl_D / 2, sphere_intersect_z),
        pt(tip_cyl_D / 2, groove_bot_z),
    ))

    # E3: Step inward to groove diameter
    edges.append(Part.makeLine(
        pt(tip_cyl_D / 2, groove_bot_z),
        pt(groove_ID / 2,  groove_bot_z),
    ))

    # E4: Groove cylinder wall
    edges.append(Part.makeLine(
        pt(groove_ID / 2, groove_bot_z),
        pt(groove_ID / 2, groove_top_z),
    ))

    # E5: Step outward from groove to chamfer base (tip_cyl_D)
    edges.append(Part.makeLine(
        pt(groove_ID / 2,  groove_top_z),
        pt(tip_cyl_D / 2,  groove_top_z),
    ))

    # E6: 0.5x45 chamfer up to main shank diameter
    edges.append(Part.makeLine(
        pt(tip_cyl_D / 2, groove_top_z),
        pt(shaft_D / 2,   chamfer_top_z),
    ))

    # E7: Main shank up to fillet start
    edges.append(Part.makeLine(
        pt(shaft_D / 2, chamfer_top_z),
        pt(shaft_D / 2, -fillet_R),
    ))

    # E8: R1 under-head fillet arc
    fc_x   = shaft_D / 2.0 + fillet_R
    fc_z   = -fillet_R
    fm_ang = math.radians(135.0)
    fm_x   = fc_x + fillet_R * math.cos(fm_ang)
    fm_z   = fc_z + fillet_R * math.sin(fm_ang)
    edges.append(Part.Arc(
        pt(shaft_D / 2,            -fillet_R),
        pt(fm_x,                    fm_z),
        pt(shaft_D / 2 + fillet_R,  0.0),
    ).toShape())

    # E9: Head underside flat
    edges.append(Part.makeLine(
        pt(shaft_D / 2 + fillet_R,   0.0),
        pt(head_OD / 2 - c,          0.0),
    ))

    # E10: Bottom head chamfer
    edges.append(Part.makeLine(
        pt(head_OD / 2 - c, 0.0),
        pt(head_OD / 2,     c),
    ))

    # E11: Cylindrical knurl face
    edges.append(Part.makeLine(
        pt(head_OD / 2, c),
        pt(head_OD / 2, head_thick - c),
    ))

    # E12: Top head chamfer
    edges.append(Part.makeLine(
        pt(head_OD / 2,     head_thick - c),
        pt(head_OD / 2 - c, head_thick),
    ))

    # E13: Top face
    edges.append(Part.makeLine(
        pt(head_OD / 2 - c, head_thick),
        pt(0.0,              head_thick),
    ))

    # E14: Axis closure back to tip apex
    edges.append(Part.makeLine(
        pt(0.0, head_thick),
        pt(0.0, tip_z),
    ))

    # Revolve 360 deg around Z axis
    wire  = Part.Wire(edges)
    face  = Part.Face(wire)
    screw = face.revolve(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 360)

    # Straight knurling — match macro exactly: full head height, zbase=0
    # The triangular prisms only intersect the cylindrical face so the chamfers
    # stay untouched naturally.
    try:
        knurl_tool = straightCutter(
            outDia=head_OD,
            inDia=19.4,
            zbase=0.0,
            height=head_thick,
        )
        screw = screw.cut(knurl_tool)
    except Exception:
        pass

    # ── M6 metric thread on main shank ───────────────────────────────────
    # Follows the same pattern as FSmakeHexHeadBolt.py:
    #   d_eff   = _TM.get_shank_dia(fa, nominal_dia)   — deviated shank OD
    #   tl_cut  = thread length from calc_thread_length (0 = full shank)
    #   offset_z = z where thread region starts (most-negative end of thread)
    #
    # Shank runs from chamfer_top_z (near tip, negative) up to 0 (head face).
    # Full shank length = abs(chamfer_top_z).
    # Thread measured from the HEAD downward toward tip (same as bolt standard).
    if getattr(fa, "Thread", False):
        try:
            P_m6     = 1.0                        # M6 pitch 1.0 mm
            d_eff    = _TM.get_shank_dia(fa, shaft_D)
            full_tl  = abs(chamfer_top_z)         # full shank ~30.5 mm

            # calc_thread_length is set by FastenersCmd from Thread_Length field
            raw_tl   = getattr(fa, "calc_thread_length", 0.0) or 0.0
            tl_cut   = min(float(raw_tl), full_tl) if float(raw_tl) > 0.0 else full_tl

            # offset_z = bottom (most negative) end of the threaded zone.
            # Thread starts at head face (z=0) and goes down tl_cut mm.
            offset_z = -tl_cut                    # e.g. -30.5 for full thread

            screw = _TM.cut_thread(screw, fa, d_eff, tl_cut, offset_z, P_m6)
        except Exception:
            pass

    return screw
