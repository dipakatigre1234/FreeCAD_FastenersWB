# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2013, 2014, 2015                                        *
*   Original code by:                                                     *
*   Ulrich Brammer <ulrich1a[at]users.sourceforge.net>                    *
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
from screw_maker import *

def makeWasher(self, fa): # dynamically loaded method of class Screw
    """Creates a washer
    Supported types:
    - ISO7089 Plain washers - Normal series - Product grade A
    - ISO7090 Plain washers, chamfered - Normal series - Product grade A
    - ISO7091 Plain washers - Normal series - Product grade C
    - ISO7092 Plain washers - Small series - Product grade A
    - ISO7093-1 Plain washers - Large series - Part 1: Product grade A
    - ISO7094 Plain washers - Extra large series - Product grade C
    - ISO8738 Plain washers for clevis pins - Product grade A
    - DIN6340 Washers for clamping devices
    - DIN6796 Conical spring washers (Belleville)
    - NFE27-619 Washer
    - ASMEB18.21.1.12A Washer
    - ASMEB18.21.1.12B Washer
    - ASMEB18.21.1.12C Washer
    """

    SType = fa.baseType

    # Custom geometry: user-supplied ID / OD / thickness (and height for Belleville)
    if fa.dimTable is None:
        d1_min = float(fa.DiameterCustom)
        d2_max = float(fa.WasherOuterDiaCustom)
        thk    = float(fa.WasherThicknessCustom)
        if SType == 'DIN6796':
            s = thk
            h = float(fa.WasherHeightCustom)
        else:
            h = thk
    elif SType == 'DIN6796':
        d1_min, d2_max, s, h = fa.dimTable
    elif SType[:3] == 'ISO':
        d1_min, d2_max, h, _ = fa.dimTable
    elif SType[:3] == 'DIN':
        d1_min, d2_max, h = fa.dimTable
    elif SType[:3] == 'ASM':
        d1_min, d2_max, h = fa.dimTable
    elif SType[:3] == 'NFE':
        d1_min, d2_max, d3, h, h_min = fa.dimTable

    # ── Belleville (DIN 6796): trapezoidal cross-section ──
    if SType == 'DIN6796':
        dr = (d2_max - d1_min) / 2.0
        # Vertical projection of the perpendicular material thickness s.
        # Derivation: the top and bottom cone faces are parallel lines sloped
        # across radial span dr with vertical offset sV between them; the
        # perpendicular distance between those lines is s. Solving yields:
        #   sV = s*(dr*sqrt(h^2 + dr^2 - s^2) - s*h) / (dr^2 - s^2)
        denom = dr * dr - s * s
        if denom <= 0 or (h * h + dr * dr - s * s) <= 0:
            sV = s
        else:
            sV = s * (dr * math.sqrt(h * h + dr * dr - s * s) - s * h) / denom
        if sV <= 0 or sV >= h:
            sV = min(max(s, 1e-3), h * 0.95)

        P1 = Base.Vector(d1_min / 2.0, 0.0, h)          # top-inner
        P2 = Base.Vector(d2_max / 2.0, 0.0, sV)         # top-outer
        P3 = Base.Vector(d2_max / 2.0, 0.0, 0.0)        # bottom-outer
        P4 = Base.Vector(d1_min / 2.0, 0.0, h - sV)     # bottom-inner
        edges = [Part.makeLine(P1, P2), Part.makeLine(P2, P3),
                 Part.makeLine(P3, P4), Part.makeLine(P4, P1)]
        aWire = Part.Wire(edges)
        aFace = Part.Face(aWire)
        return self.RevolveZ(aFace)

    # ── Regular / chamfered plain washers ──
    Pnt0 = Base.Vector(d1_min / 2.0, 0.0, h)
    Pnt2 = Base.Vector(d2_max / 2.0, 0.0, h)
    Pnt3 = Base.Vector(d2_max / 2.0, 0.0, 0.0)
    Pnt4 = Base.Vector(d1_min / 2.0, 0.0, 0.0)
    if SType == 'ISO7090':
        Pnt1 = Base.Vector(d2_max / 2.0 - h / 4.0, 0.0, h)
        Pnt2 = Base.Vector(d2_max / 2.0, 0.0, h * 0.75)
        edge1 = Part.makeLine(Pnt0, Pnt1)
        edgeCham = Part.makeLine(Pnt1, Pnt2)
        edge1 = Part.Wire([edge1, edgeCham])
    elif SType == 'NFE27-619' and fa.dimTable is not None:
        Pnt0 = Base.Vector(d1_min / 2.0, 0.0, h_min)
        Pnt2 = Base.Vector(d3 / 2.0, 0.0, h)
        edge1 = Part.makeLine(Pnt0, Pnt2)
    else:
        edge1 = Part.makeLine(Pnt0, Pnt2)

    edge2 = Part.makeLine(Pnt2, Pnt3)
    edge3 = Part.makeLine(Pnt3, Pnt4)
    edge4 = Part.makeLine(Pnt4, Pnt0)

    aWire = Part.Wire([edge1, edge2, edge3, edge4])
    aFace = Part.Face(aWire)
    head = self.RevolveZ(aFace)

    return head
