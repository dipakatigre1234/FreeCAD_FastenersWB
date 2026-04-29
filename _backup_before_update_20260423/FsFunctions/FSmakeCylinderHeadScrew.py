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

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM


def makeCylinderHeadScrew(self, fa):
    """Create a cylinder head fastener (cap screw).

    Supported types:
    - ISO 4762 / ISO 14579 / DIN 7984 / DIN 6912
    - ASMEB18.3.1A / ASMEB18.3.1G

    Threading fully delegated to FSThreadingASME.cut_thread() or
    FSThreadingMetric.cut_thread() — no thread logic here.

    Shank radius tr:
      ASME   → Thread_Outer_Dia from ASME B1.1 table  (_TA.outer_dia_mm)
      Metric → Thread_Mean_Dia  from ISO 965 CSV table (_TM.mean_dia_from_table)
    """
    SType   = fa.baseType
    length  = fa.calc_len
    dia     = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")

    # ── 1. Unpack dimTable ────────────────────────────────────────────────
    if SType == 'ISO4762':
        P_tbl, b_tbl, dk_max, da, ds_mean, e, lf, k, r, s_mean, t, v, dw, w = fa.dimTable
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == 'ISO14579':
        P_tbl, b_tbl, dk_max, da, ds_mean, e, lf, k, r, s_mean, t, v, dw, w = \
            FsData["ISO4762def"][fa.calc_diam]
        tt, A, t = fa.dimTable
        recess = self.makeHexalobularRecess(tt, t, True)

    elif SType == 'DIN7984':
        P_tbl, b_tbl, dk_max, da, ds_min, e, k, r, s_mean, t, v, dw = fa.dimTable
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == 'DIN6912':
        P_tbl, b_tbl, dk_max, da, ds_min, e, k, r, s_mean, t, t2, v, dw = fa.dimTable
        recess = self.makeHexRecess(s_mean, t, True)
        d_cent     = s_mean / 3.0
        depth_cent = d_cent * math.tan(math.pi / 6.0)
        fm = FSFaceMaker()
        fm.AddPoint(0.0,    0.0)
        fm.AddPoint(d_cent, 0.0)
        fm.AddPoint(d_cent, -t2)
        fm.AddPoint(0.0,    -t2 - depth_cent)
        recess = recess.fuse(self.RevolveZ(fm.GetFace()))

    elif SType == 'ASMEB18.3.1A':
        P_tbl, b_tbl, dk_max, k, r, s_mean, t, v, dw = fa.dimTable
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == 'ASMEB18.3.1G':
        P_tbl, b_tbl, A, H, C_max, J, T, K, r = (x * 25.4 for x in fa.dimTable)
        dk_max = A
        k      = H
        v      = C_max
        s_mean = J
        t      = T
        dw     = A - K
        recess = self.makeHexRecess(s_mean, t, True)

    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── 2. Resolve effective pitch P (standard or custom TPI override) ────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) \
        else P_tbl

    # ── 3. Thread length — standard table or custom Thread_Length ─────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        # Custom Thread_Length set by user
        b = min(float(raw_tlen), length)
    else:
        # Standard: clamp b_tbl to (length - r) — fully threads short bolts
        b = min(b_tbl, max(length - r, 0.0))

    # ── 4. Effective shank diameter from threading module (CSV + deviation) ──
    d_eff = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    tr    = d_eff / 2.0


    # ── 5. Console log ────────────────────────────────────────────────────
    try:
        import FreeCAD as _FC
        _tpi_log = round(25.4 / P) if P > 0 else 0
        _custom  = " (custom)" if (raw_pitch and float(raw_pitch) > 0) else ""
        _cls_log = str(getattr(fa, "Thread_Class", "-") or "-") if is_asme \
                   else str(getattr(fa, "Thread_Class_ISO", "-") or "-")
        _pitch_s = str(getattr(fa, "Thread_Pitch", "") or "") if not is_asme else ""
        _FC.Console.PrintMessage(
            "[Thread] Type       : " + str(fa.baseType) + "\n" +
            "[Thread] Nominal D  : " + f"{dia:.4f}mm\n" +
            "[Thread] Pitch P    : " + f"{P:.5f}mm" + _custom + "\n" +
            "[Thread] TPI        : " + str(_tpi_log) + _custom + "\n" +
            ("[Thread] Class      : " + _cls_log + "\n" if is_asme else
             "[Thread] MetricPitch: " + _pitch_s + "  Class: " + _cls_log + "\n") +
            "[Thread] Shank r    : " + f"{tr:.5f}mm\n" +
            "[Thread] Thread Len : " + f"{b:.3f}mm\n" +
            "[Thread] Total Len  : " + f"{length:.3f}mm\n"
        )
    except Exception:
        pass

    # ── 6. Revolve profile ────────────────────────────────────────────────
    fm = FSFaceMaker()
    fm.AddPoint(0.0,           k)
    fm.AddPoint(dk_max / 2 - v, k)
    fm.AddArc2(0.0, -v, -90)
    fm.AddPoint(dk_max / 2,    (dk_max - dw) / 2)
    fm.AddPoint(dw / 2,        0.0)
    fm.AddPoint(tr + r,        0.0)
    fm.AddArc2(0.0, -r, 90)             # fillet arc: starts at (tr+r,0) ends at (tr,-r)
    # NO step — arc lands exactly at shank radius tr, no blue ring edge

    if length - r > b:                  # partially threaded
        if not fa.Thread:
            fm.AddPoint(tr, -1 * (length - b))

    fm.AddPoint(tr,            -length + d_eff / 10)
    fm.AddPoint(d_eff * 4 / 10, -length)
    fm.AddPoint(0.0,          -length)

    shape = self.RevolveZ(fm.GetFace())

    # ── 7. Cut recess into head ───────────────────────────────────────────
    recess.translate(Base.Vector(0.0, 0.0, k))
    shape = shape.cut(recess)

    # ── 8. Threading — fully delegated to threading modules ───────────────
    if fa.Thread:
        tl_cut   = b
        offset_z = -(length - b)
        if is_asme:
            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)
        else:
            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

    return shape