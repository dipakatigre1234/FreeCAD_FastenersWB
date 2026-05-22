# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2024                                                    *
*   Original code by:                                                     *
*   Alex Neufeld <alex.d.neufeld@gmail.com>                               *
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

import sys as _sys, os as _os
_wb = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _wb not in _sys.path:
    _sys.path.insert(0, _wb)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM


def makeReducedShankHexHeadBolt(self, fa):
    """Creates a bolt with a hexagonal head and a reduced shank

    supported types:
    - ISO 4015 hexagon head bolts with reduced shank
    """
    dia    = self.getDia(fa.calc_diam, False)   # nominal: M12 → 12.0 mm
    length = fa.calc_len
    if fa.baseType == "ISO4015":
        # CSV cols: P, b1, b2, c, d_a, d_s, d_w, e, k_nom, k_max, k_min, k_w, r, s_nom_max, s_min, x_max
        P_csv, b1, b2, c, _, d_s, dw, e, k, _, _, _, r, s, _, x = fa.dimTable
        if length > 125 and b2 != 0:
            b = b2
        else:
            b = b1
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    # Pitch: user override takes priority over CSV value
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch and float(raw_pitch) > 0) else float(P_csv)

    # d_eff: effective thread diameter from the metric thread CSV (class 6g etc.)
    # cut_thread() internally calls get_shank_dia(fa, dia) to get d_cutter.
    # We must draw the body profile at this same d_eff so the cutter matches exactly.
    is_asme = fa.baseType.startswith("ASME")
    d_eff = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)

    # d_s  = reduced shank diameter near head (from CSV, always smooth/unthreaded)
    # d_eff = effective body diameter at threaded end = what the thread cutter uses
    # x    = runout taper length between d_s and d_eff sections

    cham = (e - s) * math.sin(math.radians(15))

    fm = FSFaceMaker()
    fm.AddPoint(0.0,             k)
    fm.AddPoint(s / 2.0,         k)
    fm.AddPoint(s / sqrt3,       k - cham)
    fm.AddPoint(s / sqrt3,       c)
    fm.AddPoint(dw / 2.0,        c)
    fm.AddPoint(dw / 2.0,        0.0)
    fm.AddPoint(d_s / 2.0 + r,   0.0)
    fm.AddArc2(0.0, -r, 90)                          # fillet → lands at (d_s/2, -r)

    if length - b - x - r < 0.1:
        # bolt too short for a proper reduced section
        fm.AddPoint(d_s  / 2.0,  -r - 0.1)
        fm.AddPoint(d_eff / 2.0,  -r - 0.1 - x)
        thread_length = length - r - 0.1 - x
    else:
        fm.AddPoint(d_s  / 2.0,  -length + b + x)   # end of reduced shank
        fm.AddPoint(d_eff / 2.0,  -length + b)       # end of runout → start of threads
        thread_length = b

    fm.AddPoint(d_eff / 2.0,   -length + d_eff / 10)
    fm.AddPoint(d_eff * 4 / 10, -length)
    fm.AddPoint(0.0,            -length)

    shape = self.RevolveZ(fm.GetFace())
    extrude = self.makeHexPrism(s, k + length + 2)
    extrude.translate(Base.Vector(0.0, 0.0, -length - 1))
    shape = shape.common(extrude)

    if fa.Thread:
        # cut_thread internally uses get_shank_dia(fa, dia) → same d_eff as body profile
        offset_z = -(length - thread_length)
        if is_asme:
            shape = _TA.cut_thread(shape, fa, dia, thread_length, offset_z, P)
        else:
            shape = _TM.cut_thread(shape, fa, dia, thread_length, offset_z, P)
    return shape