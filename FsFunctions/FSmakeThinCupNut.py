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
import FastenerBase
import sys as _sys_nut, os as _os_nut
_wb_nut = _os_nut.path.dirname(_os_nut.path.dirname(_os_nut.path.abspath(__file__)))
if _wb_nut not in _sys_nut.path:
    _sys_nut.path.insert(0, _wb_nut)
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None


def makeThinCupNut(self, fa):
    """DIN917 Cap nuts, thin style"""
    dia = self.getDia(fa.calc_diam, True)
    # DIN917def columns (updated):
    # P, g2, h_max, h_min, r, s_max, s_min, t_max, t_min, w
    P = fa.dimTable[0]
    g2 = fa.dimTable[1]
    h = (fa.dimTable[2] + fa.dimTable[3]) / 2
    r = fa.dimTable[4]
    s = (fa.dimTable[5] + fa.dimTable[6]) / 2
    t = (fa.dimTable[7] + fa.dimTable[8]) / 2
    w = fa.dimTable[9]

    # Resolve metric nut pitch like updated HexNut:
    # prefer Thread_Pitch_Nut, then calc_pitch, else dimTable P.
    if _TMI is not None:
        _p_nut_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
        if _p_nut_s:
            try:
                P = float(_p_nut_s)
            except Exception:
                pass
        elif fa.calc_pitch is not None and fa.calc_pitch > 0.0:
            P = fa.calc_pitch

    H = P * cos30 * 5.0 / 8.0
    e = s / sqrt3 * 2.0
    cham_i = H * math.tan(math.radians(15.0))
    cham_o = (e - s) * math.tan(math.radians(15.0))
    # Body bore radius from metric internal thread table (D1max + deviation).
    _bore_r = None
    if _TMI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _p_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "") or "6H")
            if not _p_s:
                _p_mm = _TMI.resolve_nut_pitch(fa)
                _p_s = str(_p_mm) if _p_mm else ""
            if _p_s:
                _bore_eff = _TMI.bore_dia_from_table(fa, _dia_s, _p_s, _cls_s)
                _bore_r = _bore_eff / 2.0
        except Exception:
            _bore_r = None

    if _bore_r is None:
        _bore_r = dia / 2.0 - H

    d = _bore_r

    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(d, 0.0)
    fm.AddPoint(s / 2.0, 0.0)
    fm.AddPoint(e / 2.0, cham_o)
    fm.AddPoint(e / 2.0, h - r + math.sqrt(r * r - e * e / 4.0))
    fm.AddArc(
        e / 4.0,
        h - r + math.sqrt(r * r - e * e / 16.0),
        0.0,
        h
    )
    fm.AddPoint(0.0, h-w)
    fm.AddPoint(0.0, d * tan15)
    head = self.RevolveZ(fm.GetFace())
    extrude = self.makeHexPrism(s, h)
    nut = head.common(extrude)

    if fa.Thread:
        # Prefer the metric internal thread sweep (same approach as other nut makers).
        # This avoids residual material artifacts between thread turns.
        if _TMI is not None:
            try:
                nut = _TMI.cut_internal_thread(nut, fa, dia, t)
                return nut
            except Exception as ex:
                FreeCAD.Console.PrintLog(
                    f"[FSmakeThinCupNut] metric thread sweep failed for "
                    f"{fa.baseType} {fa.calc_diam}, falling back to legacy "
                    f"thread cutter: {ex}\n"
                )
        thread_dia = dia + 0.05 * P
        thread_depth = max(t - P, 0.1)
        threadCutter = self.CreateBlindInnerThreadCutter(thread_dia, P, thread_depth)
    else:
        fm.Reset()
        fm.AddPoint(0.0, 0.0)
        fm.AddPoint(d - H, 0.0)
        fm.AddPoint(d - H, t - P)
        fm.AddPoint(0.0, t - P + (d - H) / math.tan(math.radians(59)))
        threadCutter = self.RevolveZ(fm.GetFace())
    nut = nut.cut(threadCutter)
    return nut
