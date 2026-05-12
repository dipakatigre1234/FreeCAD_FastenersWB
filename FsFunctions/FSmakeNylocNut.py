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
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None


tan30 = math.tan(math.radians(30.0))


def nylocMakeFace(do, p, da, dw, e, m, h, s):
    di = (do - p) / 2
    do = do / 2
    dw = dw / 2
    da = da / 2
    e = e / 2
    s = s / 2
    # Keep this exactly on the hex envelope; tiny offsets can create sliver
    # faces between adjacent flats after boolean operations.
    s1 = s
    ch1 = do - di
    ch2 = (e - dw) * tan30
    ch3 = m - (e - s) * tan30
    h1 = h * 0.9
    r = (s - di) / 3

    fm = FastenerBase.FSFaceMaker()
    fm.AddPoints((di, ch1), (da, 0), (dw, 0), (e, ch2),
                 (e, ch3), (s1, m), (s1, h - r))
    fm.AddArc2(-r, 0, 90)
    fm.AddPoints((di + r, h), (di + r, h1), (di, h1))
    return fm.GetFace()


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
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "") or "6H")
            if not _p_s:
                _p_s = str(_metric_thread_pitch_for_nut(fa, p))
            if _p_s:
                return _TMI.bore_dia_from_table(fa, _dia_s, _p_s, _cls_s)
        except Exception:
            pass
    return self.GetInnerThreadMinDiameter(dia, p, 0.0)


def makeNylocNut(self, fa):
    """Create a nut with a non-metallic locking insert
    Supported Types:
    - DIN 985 Nyloc nuts
    - ISO 7040 Nyloc nuts
    - ISO 7041 Nyloc nuts
    - ISO 10511 thin nyloc nuts
    - ISO 10512 fine thread nyloc nuts
    """
    if fa.baseType == "DIN985":
        P, da, dw, e, m, h, s = fa.dimTable
    elif fa.baseType in ["ISO7040", "ISO7041", "ISO10511", "ISO10512"]:
        # Updated ISO704x/ISO1051x layouts use min/max notation.
        # Common numeric order:
        # P, da_max, da_min, dw, e, h_max, h_min, m, mw, s_max, s_min
        P = fa.dimTable[0]
        da = (fa.dimTable[1] + fa.dimTable[2]) / 2
        dw = fa.dimTable[3]
        e = fa.dimTable[4]
        h = (fa.dimTable[5] + fa.dimTable[6]) / 2
        m = fa.dimTable[7]
        s = (fa.dimTable[9] + fa.dimTable[10]) / 2
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")
    dia = self.getDia(fa.calc_diam, True)
    P = _metric_thread_pitch_for_nut(fa, P)
    bore_dia = _metric_bore_dia_for_nut(self, fa, dia, P)
    section = nylocMakeFace(dia, dia - bore_dia, da, dw, e, m, h, s)
    nutSolid = self.RevolveZ(section)
    # Move the revolution seam away from hex-flat boundaries; this avoids
    # persistent sliver side faces after boolean intersection.
    nutSolid.rotate(Base.Vector(0.0, 0.0, 0.0), Base.Vector(0.0, 0.0, 1.0), 11.0)
    htool = htool = self.makeHexPrism(s, m * 3)
    # Merge coplanar sliver faces produced by boolean intersection.
    nutSolid = nutSolid.common(htool).removeSplitter()
    if fa.Thread:
        if _TMI is not None:
            try:
                nutSolid = _TMI.cut_internal_thread(nutSolid, fa, dia, h)
            except Exception as ex:
                FreeCAD.Console.PrintLog(
                    f"[FSmakeNylocNut] metric thread sweep failed for "
                    f"{fa.baseType} {fa.calc_diam}, falling back to legacy "
                    f"thread cutter: {ex}\n"
                )
                thread_dia = dia + 0.05 * P
                threadCutter = self.CreateInnerThreadCutter(thread_dia, P, h + P)
                nutSolid = nutSolid.cut(threadCutter)
        else:
            thread_dia = dia + 0.05 * P
            threadCutter = self.CreateInnerThreadCutter(thread_dia, P, h + P)
            nutSolid = nutSolid.cut(threadCutter)

    # Final cleanup: merge coplanar/split faces that can reappear after
    # subsequent boolean cuts (threading, bore, etc.).
    return nutSolid.removeSplitter()
