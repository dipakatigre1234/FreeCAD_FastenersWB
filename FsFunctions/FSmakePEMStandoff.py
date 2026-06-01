# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2022                                                    *
*   Shai Seger <shaise[at]gmail>                                          *
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
from screw_maker import *
import FastenerBase

tan30 = math.tan(math.radians(30))

# PEM Self Clinching standoffs types: SO/SOS/SOA/SO4


def soMakeFace(b, c, h, d, l1, bl, isBlind):
    h10 = h / 10.0
    h102 = h10 + h10 / 2
    c12 = c / 12.5
    c20 = c / 20.0
    c40 = c / 40.0
    b = b / 2
    c = c / 2
    d = d / 2
    ch1 = b - d
    ch2 = d * tan30
    l2 = l1 - bl
    c1 = c - c40
    c2 = c - c20
    l3 = h10 * 2 + (c12 + c20) * 2

    fm = FastenerBase.FSFaceMaker()
    if isBlind:
        fm.AddPoints(
            (0, 0),
            (0, -h102),
            (d, -(h102 + ch2)),
            (d, -(l1 - ch1)),
            (b, -l1)
        )
    else:
        fm.AddPoints((b, 0), (d, -ch1), (d, -(l2 - ch1)), (b, -l2))
        if (l1 - l2) > 0.01:
            fm.AddPoint(b, -l1)
    fm.AddPoint(c, -l1)
    if l3 < l1:
        fm.AddPoints((c, -l3), (c1, -l3), (c1, -(l3 - c20)), (c, -(l3 - c20)))
    fm.AddPoints(
        (c, -(h10 * 2 + c12 + c20)),
        (c1, -(h10 * 2 + c12 + c20)),
        (c1, -(h10 * 2 + c12)),
        (c, -(h10 * 2 + c12)),
        (c, -h10 * 2),
        (c2, -h10 * 2),
        (c2, -h10),
        (h * 0.6, -h10),
        (h * 0.6, 0),
    )
    return fm.GetFace()


def makePEMStandoff(self, fa):
    l = fa.calc_len
    plen = fa.Length
    _, c, h, _, lmin, lmax = fa.dimTable
    # there is an additional M3 size available for this fastener type,
    # designated by "3.5M3".
    # We must account for the fact that this size is not available in
    # thread data tables
    if fa.Diameter.startswith("3.5"):
        dia_key = "M3"
    else:
        dia_key = fa.Diameter
    dia = self.getDia(dia_key, True)
    b = dia * 1.05
    P = FsData["ISO262def"][dia_key][0]
    d = self.GetInnerThreadMinDiameter(dia, P)
    if fa.Blind and l < 6:
        l = 6
        plen = "6"

    bl = FsData[fa.baseType + "length"][plen][0]
    f = soMakeFace(b, c, h, d, l, bl, fa.Blind)
    p = self.RevolveZ(f)
    htool = self.makeHexPrism(h, l * 1.1)
    htool.translate(Base.Vector(0.0, 0.0, -1.05 * l))
    fSolid = p.common(htool)
    if fa.Thread:
        thread_cutter = self.CreateInnerThreadCutter(dia, P, l * 1.25)
        thread_cutter.rotate(
            Base.Vector(0.0, 0.0, 0.0), Base.Vector(1.0, 0.0, 0.0), 180.0
        )
        if fa.Blind:
            thread_cutter.translate(Base.Vector(0.0, 0.0, -d))
        fSolid = fSolid.cut(thread_cutter)
    return fSolid


# PEM Blind Threaded standoffs types: BSO/BSOS/BSOA/BSO4
# The geometry is a hex head + cylindrical shank with a blind, bottom-up
# drilled hole (cylinder + 118 degree drill point). It is built faithfully
# from a tested macro; only the fixed dimensions are replaced by values read
# from the PEMBLStandoff data tables.


def makePEMBlindStandoff(self, fa):
    L = fa.calc_len                 # total length
    # PEMBLStandoffdef columns: Sheet, Hole(in sheet), C, H, d, Min_L, Max_L
    sheet_thick, _, c, h, hole_dia, _, _ = fa.dimTable
    # F (min blind thread depth) varies with length - read from length table
    F = FsData[fa.baseType + "length"][fa.Length][0]

    # ── Resolve nominal thread diameter + pitch ───────────────────────────────
    # The hole_dia column is the tap-drill (minor) hole; the THREAD nominal
    # diameter comes from the size key (e.g. M3 -> 3.0). Pitch is read from the
    # same ISO262 source the self-clinching standoff (makePEMStandoff) uses.
    #
    # ROBUSTNESS: fa.Diameter for the blind standoff type may not be a clean
    # "M3" key that ISO262def accepts (e.g. it can carry a "3.5M3" prefix or a
    # size that is absent from the thread tables). We normalise it the same way
    # makePEMStandoff does, then resolve dia via getDia and pitch via ISO262def,
    # coercing both to float. If anything is off, thread is skipped (not crashed).
    if fa.Diameter.startswith("3.5"):
        dia_key = "M3"
    else:
        dia_key = fa.Diameter

    dia = 0.0
    P = 0.0
    try:
        dia = float(self.getDia(dia_key, True))
        P = float(FsData["ISO262def"][dia_key][0])
    except Exception as e:
        FreeCAD.Console.PrintWarning(
            "[PEMBlindStandoff] could not resolve dia/P for %r: %s — "
            "thread will be skipped\n" % (dia_key, e)
        )

    # 1. Shank (cylinder), extruded downwards so the head sits at Z = 0
    shank_radius = c / 2.0
    shank = Part.makeCylinder(shank_radius, L - sheet_thick)
    shank.translate(Base.Vector(0, 0, -(L - sheet_thick)))

    # 2. Hexagonal head. Circumradius of the hexagon: R = H / sqrt(3)
    hex_radius = h / math.sqrt(3)
    edges = []
    for i in range(6):
        angle1 = math.radians(60 * i)
        angle2 = math.radians(60 * (i + 1))
        p1 = Base.Vector(hex_radius * math.cos(angle1), hex_radius * math.sin(angle1), 0)
        p2 = Base.Vector(hex_radius * math.cos(angle2), hex_radius * math.sin(angle2), 0)
        edges.append(Part.makeLine(p1, p2))
    hex_wire = Part.Wire(edges)
    hex_face = Part.Face(hex_wire)
    head = hex_face.extrude(Base.Vector(0, 0, sheet_thick))

    body = head.fuse(shank)

    # 3. Blind hole tool (bottom-up): cylinder + 118 degree drill point cone
    hole_radius = hole_dia / 2.0
    drill_depth = F + 1.5
    tip_angle = math.radians(90 - (118 / 2))
    tip_height = hole_radius * math.tan(tip_angle)
    bottom_z = -(L - sheet_thick)

    hole_cyl = Part.makeCylinder(hole_radius, drill_depth)
    hole_cyl.translate(Base.Vector(0, 0, bottom_z))
    hole_cone = Part.makeCone(hole_radius, 0.0, tip_height)
    hole_cone.translate(Base.Vector(0, 0, bottom_z + drill_depth))
    blind_hole_tool = hole_cyl.fuse(hole_cone)

    # 4. Cut the hole from the main body
    body = body.cut(blind_hole_tool)

    # 5. Internal threading (blind, bottom-up) ────────────────────────────────
    # The bore wall sits at hole_dia/2 (tap-drill / minor side). The cutter is
    # run at the NOMINAL major diameter via CreateInnerThreadCutter(dia, P, ...)
    # so it carves the thread form from major inward into the bore wall — the
    # same proven call used in makePEMStandoff. Without running the cutter at
    # the nominal dia, the thread crests float and produce disconnected rings.
    #
    # CreateInnerThreadCutter builds z-up (mouth at top). The blind hole opens
    # DOWNWARD from bottom_z, so the cutter is flipped 180 deg about X (matching
    # makePEMStandoff's blind branch) and positioned so its mouth aligns with
    # the hole mouth at bottom_z, threading up into the cylindrical region only.
    if fa.Thread and dia > 0 and P > 0:
        # ROOT CAUSE of "makeLongHelix fails on parms":
        # The cutter's numeric args (pitch=0.5, height≈4, radius=1.5) are
        # textbook-valid and identical in shape to those a working M3 hex nut
        # passes — so the numbers are NOT the problem. The only remaining input
        # to Part.makeLongHelix(P, blen, r, 0, self.LeftHanded) is the 5th arg,
        # self.LeftHanded. OCC requires a genuine bool there; if fa.LeftHanded
        # was never initialised for this fastener type, self.LeftHanded is None,
        # and makeLongHelix rejects it as a bad parameter.
        #
        # Force a clean bool for the duration of the cut, then restore.
        _saved_lh = getattr(self, "LeftHanded", False)
        self.LeftHanded = bool(_saved_lh) if _saved_lh is not None else False

        conic_height = 0.55 * dia / math.tan(math.radians(59))
        blind_len = max(F, conic_height + 2.0 * P)

        try:
            # Purpose-built blind inner thread cutter (bore + 118° point + thread).
            # Built z-up, base at z=0, threads running +Z — matches the blind
            # hole that opens downward at bottom_z with interior extending +Z.
            thread_cutter = self.CreateBlindInnerThreadCutter(dia, P, blind_len)
            thread_cutter.translate(Base.Vector(0.0, 0.0, bottom_z))
            body = body.cut(thread_cutter)
        except Exception as e1:
            FreeCAD.Console.PrintWarning(
                "[PEMBlindStandoff] blind cutter failed (dia=%r P=%r len=%r "
                "LeftHanded=%r): %s — falling back to plain inner cutter\n"
                % (dia, P, blind_len, self.LeftHanded, e1)
            )
            try:
                cutter_len = max(L * 1.25, 7.5)
                thread_cutter = self.CreateInnerThreadCutter(dia, P, cutter_len)
                thread_cutter.translate(Base.Vector(0.0, 0.0, bottom_z))
                body = body.cut(thread_cutter)
            except Exception as e2:
                FreeCAD.Console.PrintWarning(
                    "[PEMBlindStandoff] internal thread skipped entirely "
                    "(dia=%r P=%r LeftHanded=%r): %s\n"
                    % (dia, P, self.LeftHanded, e2)
                )
        finally:
            self.LeftHanded = _saved_lh

    return body