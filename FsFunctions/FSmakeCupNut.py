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


def makeCupNut(self, fa):
    """Creates a blind-threaded cap nut
    Supported types:
    - DIN1587 cap nut
    - GOST11860-1 cap (or 'acorn') nut
    - SAE J483a cap nuts, both low and high styles
    """
    SType = fa.baseType
    dia = self.getDia(fa.calc_diam, True)
    if SType == "DIN1587" or SType == "GOST11860-1":
        P, d_k, h, m, s, t, w = fa.dimTable
    elif SType == "SAEJ483a1" or SType == "SAEJ483a2":
        TPI, F, A, H, Q, U = fa.dimTable
        P = 1 / TPI * 25.4
        s = F * 25.4
        d_k = A * 25.4
        m = Q * 25.4
        t = U * 25.4
        h = H * 25.4
        w = h - t - dia / 2 / math.tan(math.radians(60))
    else:
        raise RuntimeError("unknown screw type")

    is_asme = SType.startswith("SAE")
    eff_tpi = None

    if is_asme:
        if _TAI is not None:
            try:
                eff_tpi = _TAI.resolve_nut_tpi(fa)
            except Exception:
                eff_tpi = None
        if not eff_tpi and getattr(fa, "calc_tpi", None):
            try:
                eff_tpi = float(fa.calc_tpi)
            except Exception:
                eff_tpi = None
        if not eff_tpi or eff_tpi <= 0:
            eff_tpi = 25.4 / P if P > 0 else 8.0
        P = 25.4 / eff_tpi
    else:
        if _TMI is not None:
            try:
                p_m = _TMI.resolve_nut_pitch(fa)
                if p_m and p_m > 0:
                    P = p_m
            except Exception:
                pass
        elif getattr(fa, "calc_pitch", None):
            try:
                if fa.calc_pitch > 0:
                    P = fa.calc_pitch
            except Exception:
                pass

    bore_dia = None
    if is_asme and _TAI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _tpi_s = str(getattr(fa, "Thread_TPI_Nut", "") or "")
            _type_s = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
            _cls_s = str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")
            if not _tpi_s:
                _tpi_s = str(eff_tpi)
            bore_dia = _TAI.bore_dia_from_table(fa, _dia_s, _tpi_s, _type_s, _cls_s)
        except Exception:
            bore_dia = None
    elif (not is_asme) and _TMI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _p_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "6H") or "6H")
            if not _p_s:
                _p_s = str(P)
            bore_dia = _TMI.bore_dia_from_table(fa, _dia_s, _p_s, _cls_s)
        except Exception:
            bore_dia = None
    if bore_dia is None:
        bore_dia = self.GetInnerThreadMinDiameter(dia, P, 0.0)

    # Blind cap thread depth (new): keep depth valid for all sizes/custom TPI.
    # This prevents zero/negative depth when geometry is tight.
    thread_depth = h - w
    if thread_depth <= 0:
        thread_depth = max(0.75 * P, 0.25)
    # create the profile of the nut in the x-z plane
    ec = (2 - sqrt3) * s / 6
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(0, 1.1 * bore_dia / 4)
    fm.AddPoint(1.1 * dia / 2, 0)
    fm.AddPoint(s / 2, 0)
    fm.AddPoint(s * sqrt3 / 3, ec)
    fm.AddPoint(s * sqrt3 / 3, m - ec)
    fm.AddPoint(d_k / 2, (m - ec) + (2 * s - sqrt3 * d_k) / 6)
    fm.AddPoint(d_k / 2, h - d_k / 2)
    fm.AddArc(
        d_k / 2 * sqrt2 / 2, h - d_k / 2 + d_k /
        2 * sqrt2 / 2, 0, h
    )
    solid = self.RevolveZ(fm.GetFace())
    # create an additional solid to cut the hex flats with
    solidHex = self.makeHexPrism(s, h * 1.1)
    solid = solid.common(solidHex)
    # cut the threads
    if fa.Thread:
        if (not is_asme) and _TMI is not None:
            try:
                tap_tool = _TMI.make_internal_thread_cutter(bore_dia, P, thread_depth)
            except Exception as ex:
                FreeCAD.Console.PrintLog(
                    f"[FSmakeCupNut] metric thread sweep failed for "
                    f"{fa.baseType} {fa.calc_diam}, falling back to legacy "
                    f"thread cutter: {ex}\n"
                )
                thread_dia = dia + 0.05 * P
                tap_tool = self.CreateBlindInnerThreadCutter(thread_dia, P, thread_depth)
        elif is_asme:
            thread_dia = dia + 0.05 / eff_tpi if eff_tpi and eff_tpi > 0 else dia
            tap_tool = self.CreateBlindInnerThreadCutter(thread_dia, P, thread_depth)
        else:
            thread_dia = dia + 0.05 * P
            tap_tool = self.CreateBlindInnerThreadCutter(thread_dia, P, thread_depth)
        fm.Reset()
        fm.AddPoint(0, h - w),
        fm.AddPoint(1.1 * bore_dia / 2, t),
        fm.AddPoint(1.1 * bore_dia / 2, h),
        fm.AddPoint(0, h)
        thread_chamfer = self.RevolveZ(fm.GetFace())
        tap_tool = tap_tool.cut(thread_chamfer)
        solid = solid.cut(tap_tool)
    # if real threads are not needed, cut a drilled hole at
    # the minor diameter of the threads
    else:
        fm.Reset()
        fm.AddPoint(0, 0),
        fm.AddPoint(0, h - w)
        fm.AddPoint(bore_dia / 2, t)
        fm.AddPoint(bore_dia / 2, 0)
        hole = self.RevolveZ(fm.GetFace())
        solid = solid.cut(hole)
    return solid
