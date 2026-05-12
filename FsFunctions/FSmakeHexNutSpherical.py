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
from screw_maker import *
import math
import FastenerBase
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None


def makeHexNutSpherical(self, fa):
    """Creates a hexagonal nut.
    Supported types:
    - DIN 6330 Hexagon nuts with a height of 1,5 d for conical seats
    """

    dia = self.getDia(fa.calc_diam, True)
    P, d1, d5, damax, m, s, r, csh_diam = fa.dimTable
    if _TMI is not None:
        try:
            _p_sel = _TMI.resolve_nut_pitch(fa)
            if _p_sel and _p_sel > 0:
                P = _p_sel
        except Exception:
            pass

    da = (damax + dia) / 2.
    tan30 = math.tan(math.radians(30.))
    inner_rad = (dia - 1.0825 * P) / 2.
    inner_chamfer_X = da / 2. - inner_rad
    inner_chamfer_Z = inner_chamfer_X * tan30
    # outer_chamfer_X = (emax - s) / 2
    #                 = (1.2 * s - s) / 2
    #                 = 0.1 * s
    outer_chamfer_X = .1 * s
    outer_chamfer_Z = outer_chamfer_X * tan30

    Phi_Start = math.asin(d1 / (2. * r))
    Phi_End = math.asin(.6 * s / r)
    Delta_Phi = Phi_End - Phi_Start
    Center_Z = r * math.cos(Phi_Start)

    # please see according comment in FSmakeSphericalWasher.py
    hZ = (sqrt3 * d5 + math.sqrt(36. * r**2 - 9. * d1**2) - 4. * sqrt3 * r) / 6

    fm = FastenerBase.FSFaceMaker()
    fm.StartPoint(inner_rad, inner_chamfer_Z)
    fm.AddPoint(inner_rad + inner_chamfer_X, 0.)
    fm.AddPoint(d1 / 2., 0.)
    fm.AddArc2(-d1 / 2., Center_Z, math.degrees(Delta_Phi))
    # emax = 1.2 * s
    # emax / 2. = 0.6 * s
    fm.AddPoint(.6 * s, m - outer_chamfer_Z)
    # emax / 2. - outer_chamfer_X = 0.6 * s - 0.1 *s = 0.5 * s
    fm.AddPoint(.5 * s, m)
    fm.AddPoint(inner_rad + inner_chamfer_X, m)
    fm.AddPoint(inner_rad, m - inner_chamfer_Z)

    nut_body = self.RevolveZ(fm.GetFace())
    cutoff_body = self.makeHexPrism(s, m)
    nut_body = nut_body.common(cutoff_body)

    # add modeled threads if necessary
    if fa.Thread:
        if _TMI is not None:
            try:
                nut_body = _TMI.cut_internal_thread(nut_body, fa, dia, m)
            except Exception as ex:
                FreeCAD.Console.PrintLog(
                    f"[FSmakeHexNutSpherical] metric thread sweep failed for "
                    f"{fa.baseType} {fa.calc_diam}, falling back to legacy "
                    f"thread cutter: {ex}\n"
                )
                thread_dia = dia + 0.05 * P
                thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, m + P)
                nut_body = nut_body.cut(thread_cutter)
        else:
            thread_dia = dia + 0.05 * P
            thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, m + P)
            nut_body = nut_body.cut(thread_cutter)

    nut_body.translate(Base.Vector(0., 0., -hZ))
    # incorporate placement into shape and reset placement
    nut_body = nut_body.removeSplitter()

    return nut_body
