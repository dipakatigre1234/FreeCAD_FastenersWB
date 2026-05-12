# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2024                                                    *
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
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None


def _metric_thread_pitch_for_nut(fa, p_default):
    if _TMI is not None:
        try:
            p = _TMI.resolve_nut_pitch(fa)
            if p and p > 0:
                return p
        except Exception:
            pass
    try:
        cp = float(getattr(fa, "calc_pitch", 0) or 0)
        if cp > 0:
            return cp
    except Exception:
        pass
    return p_default


def _metric_bore_dia_for_nut(self, fa, dia, p):
    if _TMI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _p_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "6H") or "6H")
            if not _p_s:
                _p_s = str(_metric_thread_pitch_for_nut(fa, p))
            if _p_s:
                return _TMI.bore_dia_from_table(fa, _dia_s, _p_s, _cls_s)
        except Exception:
            pass
    return self.GetInnerThreadMinDiameter(dia, p, 0.0)


def makeAllMetalLockNut(self, fa):
    """Creates a distorted thread lock nut
    Supported types:
    - ISO 7719 all metal lock nuts
    - ISO 7720 all metal lock nuts, style 2
    - ISO 10513 all metal lock nuts with fine pitch thread
    """
    dia = self.getDia(fa.calc_diam, True)
    if fa.baseType == "ISO10513":
        # ISO10513def columns:
        # P, d_a_max, d_a_min, d_w_min, e_min, h_max, h_min, m_w_min, s_max, s_min
        P = fa.dimTable[0]
        h = (fa.dimTable[5] + fa.dimTable[6]) / 2
        m_w = fa.dimTable[7]
        s = (fa.dimTable[8] + fa.dimTable[9]) / 2
    elif fa.baseType in ["ISO7719", "ISO7720"]:
        P, _, _, _, _, h, _, m_w, s, _ = fa.dimTable
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")
    P = _metric_thread_pitch_for_nut(fa, P)
    bore_dia = _metric_bore_dia_for_nut(self, fa, dia, P)
    # main hexagonal body of the nut
    shape = self.makeHexPrism(s, h)

    # internal bore
    fm = FSFaceMaker()
    id = bore_dia
    bore_cham_ht = (dia * 1.05 - id) / 2 * tan15
    fm.AddPoint(0.0, 0.0)
    fm.AddPoint(dia * 1.05 / 2, 0.0)
    fm.AddPoint(id / 2, bore_cham_ht)
    fm.AddPoint(id / 2, h - bore_cham_ht)
    fm.AddPoint(dia * 1.05 / 2, h)
    fm.AddPoint(0.0, h)
    bore_cutter = self.RevolveZ(fm.GetFace())
    shape = shape.cut(bore_cutter)
    # outer chamfer on the hex
    fm.Reset()
    fm.AddPoint((s / sqrt3 + 1.05 * dia / 2) / 2, h)
    fm.AddPoint(s / sqrt3, h)
    fm.AddPoint(s / sqrt3, m_w)
    top_cham_cutter = self.RevolveZ(fm.GetFace())
    shape = shape.cut(top_cham_cutter)
    # bottom chamfer
    fm.Reset()
    fm.AddPoint(s / 2, 0.0)
    fm.AddPoint(s / sqrt3, 0.0)
    cham_ht = s * (1 / sqrt3 - 0.5) * math.tan(math.radians(22.5))
    fm.AddPoint(s / sqrt3, cham_ht)
    top_cham_cutter = self.RevolveZ(fm.GetFace())
    shape = shape.cut(top_cham_cutter)
    # add modelled threads if needed
    if fa.Thread:
        if _TMI is not None:
            try:
                shape = _TMI.cut_internal_thread(shape, fa, dia, h)
            except Exception:
                thread_dia = dia + 0.05 * P
                thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, h + P)
                shape = shape.cut(thread_cutter)
        else:
            thread_dia = dia + 0.05 * P
            thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, h + P)
            shape = shape.cut(thread_cutter)
    return shape
