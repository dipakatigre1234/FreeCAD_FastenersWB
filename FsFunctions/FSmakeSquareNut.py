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


def makeSquareNut(self, fa):
    """Creates a nut with 4 wrenching flats, that may optionally have a
    chamfer on its top face.
    Supported types:
    - DIN 557 square nuts
    - DIN 562 square thin nuts
    - ASME B18.2.2 square nuts
    - ASME B18.2.2 square machine screw nuts (small sizes)
    """
    SType = fa.baseType
    dia = self.getDia(fa.calc_diam, True)
    if SType == 'DIN557':
        s, m, di, dw, P = fa.dimTable
        top_chamfer = True
    elif SType == 'DIN562':
        s, m, di, P = fa.dimTable
        top_chamfer = False
    elif SType == "ASMEB18.2.2.1B":
        # CSV columns: P, da, e_max, e_min, m_max, m_min, s_max, s_min (mm)
        P, da, e_max, e_min, m_max, m_min, s_max, s_min = fa.dimTable
        m = (m_max + m_min) / 2
        s = (s_max + s_min) / 2
        top_chamfer = False
    elif SType == "ASMEB18.2.2.2":
        # CSV columns: TPI, F_max, F_min, H_max, H_min (inches)
        TPI, F_max, F_min, H_max, H_min = fa.dimTable
        P = 1 / TPI * 25.4
        s = ((F_max + F_min) / 2) * 25.4
        dw = s
        m = ((H_max + H_min) / 2) * 25.4
        top_chamfer = True
    # create the nut body using a recantular prism primitive
    nut = Part.makeBox(s, s, m, Base.Vector(-s / 2, -s / 2, 0.0))
    # subtract the internal bore from the nut using a revolved solid
    do = dia * 1.1
    inner_rad = dia / 2 - P * 0.625 * sqrt3 / 2
    inner_cham_ht = tan15 * (do / 2 - inner_rad)
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(0.0, 0.0)
    fm.AddPoint(do / 2, 0.0)
    fm.AddPoint(inner_rad, inner_cham_ht)
    fm.AddPoint(inner_rad, m - inner_cham_ht)
    fm.AddPoint(do / 2, m)
    fm.AddPoint(0.0, m)
    hole = self.RevolveZ(fm.GetFace())
    nut = nut.cut(hole)
    # add a chamfer on one side of the outer corners if needed
    if top_chamfer:
        cham_solid = Part.makeCone(dw / 2 + m * sqrt3, dw / 2, m)
        nut = nut.common(cham_solid)
    # cut modeled threads if needed
    if fa.Thread:
        thread_cutter = self.CreateInnerThreadCutter(dia, P, m + P)
        nut = nut.cut(thread_cutter)
    return nut
