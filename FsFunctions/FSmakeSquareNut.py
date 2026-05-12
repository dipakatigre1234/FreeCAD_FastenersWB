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
import sys as _sys_nut, os as _os_nut
_wb_nut = _os_nut.path.dirname(_os_nut.path.dirname(_os_nut.path.abspath(__file__)))
if _wb_nut not in _sys_nut.path:
    _sys_nut.path.insert(0, _wb_nut)
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None
try:
    import FSThreadingASMEInternal as _TAI
except Exception:
    _TAI = None


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
    is_asme = SType.startswith("ASME")
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
    elif SType == "ASMEB18.2.2.3":
        # CSV columns: TPI, F_max, F_min, H_max, H_min (inches)
        TPI, F_max, F_min, H_max, H_min = fa.dimTable
        P = 1 / TPI * 25.4
        s = ((F_max + F_min) / 2) * 25.4
        dw = s
        m = ((H_max + H_min) / 2) * 25.4
        top_chamfer = True

    # Resolve pitch from dashboard properties when available.
    if not is_asme and _TMI is not None:
        _p_nut_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
        if _p_nut_s:
            try:
                P = float(_p_nut_s)
            except Exception:
                pass
        elif getattr(fa, "calc_pitch", None) is not None and fa.calc_pitch > 0.0:
            P = fa.calc_pitch
    else:
        if getattr(fa, "calc_pitch", None) is not None and fa.calc_pitch > 0.0:
            P = fa.calc_pitch
        if is_asme and _TAI is not None:
            try:
                _eff_tpi_resolved = _TAI.resolve_nut_tpi(fa)
                if _eff_tpi_resolved and _eff_tpi_resolved > 0:
                    P = 25.4 / _eff_tpi_resolved
            except Exception:
                pass

    # create the nut body using a recantular prism primitive
    nut = Part.makeBox(s, s, m, Base.Vector(-s / 2, -s / 2, 0.0))
    # subtract the internal bore from the nut using a revolved solid
    do = dia * 1.1
    _bore_r = None
    if not is_asme and _TMI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _p_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "") or "6H")
            if not _p_s:
                _p_mm = _TMI.resolve_nut_pitch(fa)
                _p_s = str(_p_mm) if _p_mm else ""
            if _p_s:
                _bore_r = _TMI.bore_dia_from_table(fa, _dia_s, _p_s, _cls_s) / 2.0
        except Exception:
            _bore_r = None
    elif is_asme and _TAI is not None:
        try:
            _dia_s_a = str(getattr(fa, "calc_diam", "") or "")
            _tpi_prop = str(getattr(fa, "Thread_TPI_Nut", "") or "")
            _type_s_a = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
            _cls_s_a = str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")
            if not _tpi_prop:
                _tpi_val_a = _TAI.resolve_nut_tpi(fa)
                _tpi_prop = str(_tpi_val_a) if _tpi_val_a else ""
            if _tpi_prop:
                _bore_r = _TAI.bore_dia_from_table(
                    fa, _dia_s_a, _tpi_prop, _type_s_a, _cls_s_a) / 2.0
        except Exception:
            _bore_r = None
    if _bore_r is None:
        _bore_r = dia / 2 - P * 0.625 * sqrt3 / 2

    inner_rad = _bore_r
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
        if is_asme:
            _eff_tpi_c = None
            if _TAI is not None:
                try:
                    _eff_tpi_c = _TAI.resolve_nut_tpi(fa)
                except Exception:
                    pass
            if not _eff_tpi_c or _eff_tpi_c <= 0:
                _eff_tpi_c = 25.4 / P if P > 0 else 8.0
            _p_thread = 25.4 / _eff_tpi_c if _eff_tpi_c > 0 else P
            # Ensure ASME bore follows class/type/TPI before thread cut.
            if _TAI is not None:
                try:
                    _dia_s = str(getattr(fa, "calc_diam", "") or "")
                    _tpi_s = str(getattr(fa, "Thread_TPI_Nut", "") or "")
                    _type_s = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
                    _cls_s = str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")
                    if (_tpi_s == "Custom" or not _tpi_s):
                        _tpi_s = str(_eff_tpi_c)
                    _bore_eff = _TAI.bore_dia_from_table(fa, _dia_s, _tpi_s, _type_s, _cls_s)
                    bore_cyl = Part.makeCylinder(
                        _bore_eff / 2.0,
                        m + 2.0 * _p_thread,
                        Base.Vector(0.0, 0.0, -_p_thread),
                        Base.Vector(0, 0, 1),
                    )
                    nut = nut.cut(bore_cyl)
                except Exception:
                    pass
            thread_dia = dia + 0.05 / _eff_tpi_c
            thread_cutter = self.CreateInnerThreadCutter(thread_dia, _p_thread, m + _p_thread)
            nut = nut.cut(thread_cutter)
        else:
            # Full-depth metric thread cut driven by dashboard pitch/class.
            if _TMI is not None:
                try:
                    nut = _TMI.cut_internal_thread(nut, fa, dia, m)
                except Exception:
                    thread_dia = dia + 0.05 * P
                    thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, m + P)
                    nut = nut.cut(thread_cutter)
            else:
                thread_dia = dia + 0.05 * P
                thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, m + P)
                nut = nut.cut(thread_cutter)
    return nut
