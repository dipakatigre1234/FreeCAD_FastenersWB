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
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None
try:
    import FSThreadingASMEInternal as _TAI
except Exception:
    _TAI = None


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


def makeHexNutWFlange(self, fa):
    """Creates a hexagon nut with a flanged base.
    Supported types:
    - EN1661 nuts with flange
    - ASME B18.2.2 Table 13A — Hex Flange Nuts (ASMEB18.2.2.13A)
    - ASME B18.2.2 Table 13B — Large Hex Flange Nuts (ASMEB18.2.2.13B)
    - DIN6331 Hexagon nuts with collar height 1,5 d
    """

    match fa.baseType:
        case "EN1661" | "ASMEB18.2.2.13A" | "ASMEB18.2.2.13B" | "ISO4161" | "ISO10663":
            return _makeHexNutWithTaperedFlange(self, fa)
        case "DIN6331":
            return _makeHexNutWithSquareFlange(self, fa)
        case _:
            raise NotImplementedError(f"Unknown fastener type: {fa.Type}")


def _makeHexNutWithTaperedFlange(self, fa):
    dia = self.getDia(fa.calc_diam, True)
    if fa.baseType == "EN1661":
        # EN1661def columns:
        # P, da_mean, c, dc, dw, e, m_mean, mw, r, s
        P = fa.dimTable[0]
        da = fa.dimTable[1]
        c = fa.dimTable[2]
        dc = fa.dimTable[3]
        m = fa.dimTable[6]
        s = fa.dimTable[9]
        flange_edge_rounded = True
    elif fa.baseType in ("ASMEB18.2.2.13A", "ASMEB18.2.2.13B"):
        # CSV columns: TPI, F_min, F_max, G_min, G_max, B_min, B_max, H_min, H_max, J, K (mm)
        TPI, F_min, F_max, G_min, G_max, B_min, B_max, H_min, H_max, J, K = fa.dimTable
        P = 1 / TPI * 25.4
        s = (F_max + F_min) / 2
        dc = (B_max + B_min) / 2
        da = 1.05 * dia
        m = (H_max + H_min) / 2
        c = K
        flange_edge_rounded = False
    elif fa.baseType == "ISO4161":
        # ISO4161def columns:
        # P, c_min, da_max, da_min, dc, dw, e, m_max, m_min, mw, s_max, s_min, rc
        P = fa.dimTable[0]
        c = fa.dimTable[1]
        da = (fa.dimTable[2] + fa.dimTable[3]) / 2
        dc = fa.dimTable[4]
        m = (fa.dimTable[7] + fa.dimTable[8]) / 2
        s = (fa.dimTable[11] + fa.dimTable[10]) / 2
        flange_edge_rounded = True
    elif fa.baseType == "ISO10663":
        # ISO10663def columns:
        # P, c_min, d_a_max, d_a_min, d_c_max, d_w_min, e_min,
        # m_max, m_min, m_w_min, s_max, s_min, r_max
        P = fa.dimTable[0]
        c = fa.dimTable[1]
        da = (fa.dimTable[2] + fa.dimTable[3]) / 2
        dc = fa.dimTable[4]
        m = (fa.dimTable[7] + fa.dimTable[8]) / 2
        s = (fa.dimTable[11] + fa.dimTable[10]) / 2
        flange_edge_rounded = True
    if fa.baseType not in ("ASMEB18.2.2.13A", "ASMEB18.2.2.13B"):
        P = _metric_thread_pitch_for_nut(fa, P)
        _bore_d = _metric_bore_dia_for_nut(self, fa, dia, P)
        inner_rad = _bore_d / 2.0
    else:
        inner_rad = dia / 2 - P * 0.625 * sqrt3 / 2
    inner_cham_ht = tan15 * (da / 2 - inner_rad)
    # create the body of the nut
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(inner_rad, m - inner_cham_ht)
    fm.AddPoint(da / 2, m)
    fm.AddPoint(s / 2, m)
    fm.AddPoint(s / 2 + sqrt3 * m, 0)
    fm.AddPoint(da / 2, 0)
    fm.AddPoint(inner_rad, inner_cham_ht)
    nut_body = self.RevolveZ(fm.GetFace())
    # cut the hex flats with a boolean subtraction
    nut_body = nut_body.common(self.makeHexPrism(s, m))
    # add the flange with a boolean fuse
    fm.Reset()
    fm.AddPoint((da + s) / 4, 0.0)
    if flange_edge_rounded:
        fm.AddPoint((dc + sqrt3 * c) / 2, 0.0)
        fm.AddPoint((dc - c) / 2, 0.0)
        fm.AddArc2(0, c / 2, 150)
        fm.AddPoint(
            (da + s) / 4,
            sqrt3 / 3 * ((dc - c) / 2 + c / (4 - 2 * sqrt3) - (da + s) / 4),
        )
    else:
        fm.AddPoint(dc / 2, 0.0)
        fm.AddPoint(dc / 2, c)
        fm.AddPoint(
            (da + s) / 4, c + (dc / 2 - (da + s) / 4) * math.tan(math.radians(30))
        )
    face = fm.GetFace()
    flange = self.RevolveZ(face)
    nut_body = nut_body.fuse(flange).removeSplitter()

    if fa.Thread:
        if fa.baseType in ("ASMEB18.2.2.13A", "ASMEB18.2.2.13B"):
            # ASME nut threading from dashboard properties (type/TPI/class).
            _eff_tpi = None
            _p_thread = P
            if _TAI is not None:
                try:
                    _eff_tpi = _TAI.resolve_nut_tpi(fa)
                except Exception:
                    pass
                try:
                    _dia_s = str(getattr(fa, "calc_diam", "") or "")
                    _tpi_s = str(getattr(fa, "Thread_TPI_Nut", "") or "")
                    _type_s = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
                    _cls_s = str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")
                    if (_tpi_s == "Custom" or not _tpi_s) and _eff_tpi:
                        _tpi_s = str(_eff_tpi)
                    if _tpi_s:
                        _bore_eff = _TAI.bore_dia_from_table(fa, _dia_s, _tpi_s, _type_s, _cls_s)
                        bore_cyl = Part.makeCylinder(
                            _bore_eff / 2.0,
                            m + 2.0 * (25.4 / _eff_tpi if _eff_tpi and _eff_tpi > 0 else P),
                            Base.Vector(0.0, 0.0, -(25.4 / _eff_tpi if _eff_tpi and _eff_tpi > 0 else P)),
                            Base.Vector(0, 0, 1),
                        )
                        nut_body = nut_body.cut(bore_cyl)
                except Exception:
                    pass
            if not _eff_tpi or _eff_tpi <= 0:
                _eff_tpi = 25.4 / P if P > 0 else 8.0
            _p_thread = 25.4 / _eff_tpi if _eff_tpi > 0 else P
            thread_cutter = self.CreateInnerThreadCutter(
                dia + 0.05 / _eff_tpi, _p_thread, m + _p_thread
            )
            nut_body = nut_body.cut(thread_cutter)
        elif _TMI is not None:
            try:
                nut_body = _TMI.cut_internal_thread(nut_body, fa, dia, m)
            except Exception as ex:
                FreeCAD.Console.PrintLog(
                    f"[FSmakeHexNutWFlange] metric thread sweep failed for "
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
    return nut_body


def _makeHexNutWithSquareFlange(self, fa):
    dia = self.getDia(fa.calc_diam, True)
    P, a, d1, damin, damax, m, s = fa.dimTable
    P = _metric_thread_pitch_for_nut(fa, P)

    da = (damax + damin) / 2.0
    tan30 = math.tan(math.radians(30.0))
    inner_rad = _metric_bore_dia_for_nut(self, fa, dia, P) / 2.0
    inner_chamfer_X = da / 2.0 - inner_rad
    inner_chamfer_Z = inner_chamfer_X * tan30
    outer_chamfer_X = (d1 - s) / 2.0
    outer_chamfer_Z = outer_chamfer_X * tan30

    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(0.0, -1.0)
    fm.AddPoint(inner_rad + inner_chamfer_X, -1.0)
    fm.AddPointRelative(0.0, 1.0)
    fm.AddPoint(inner_rad, inner_chamfer_Z)
    fm.AddPoint(inner_rad, m - inner_chamfer_Z)
    fm.AddPoint(inner_rad + inner_chamfer_X, m)
    fm.AddPoint(s / 2.0, m)
    fm.AddPoint(d1 / 2.0, m - outer_chamfer_Z)
    fm.AddPoint(d1 / 2.0, m + 1.0)
    fm.AddPoint(0.0, m + 1.0)

    import Part

    nut_body = self.makeHexPrism(s, m)
    collar = Part.makeCylinder(d1 / 2.0, a)
    cutoff_body = self.RevolveZ(fm.GetFace())
    nut_body = nut_body.fuse(collar)
    nut_body = nut_body.cut(cutoff_body).removeSplitter()

    if fa.Thread:
        if _TMI is not None:
            try:
                nut_body = _TMI.cut_internal_thread(nut_body, fa, dia, m)
            except Exception as ex:
                FreeCAD.Console.PrintLog(
                    f"[FSmakeHexNutWFlange] metric thread sweep failed for "
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
    return nut_body
