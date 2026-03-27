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



def makeFlangedButtonHeadScrew(self, fa):
    """Create a button head cap screw with a rounded flange

    Supported types:
    - ISO 7380-2 Button head screw with collar
    - ASMEB18.3.3B UNC hex socket button head screws with flange

    Thread diameter formulas (Dipak):
      ASME/inch : thread_dia = dia - 0.15 / TPI
      Metric    : thread_dia = dia - 0.15 * P
    """
    SType  = fa.baseType
    length = fa.calc_len
    dia    = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")

    # ── Unpack dimTable ───────────────────────────────────────────────────
    if SType == 'ISO7380-2':
        P_tbl, b_tbl, c, da, dk, dk_c, s_mean, t_min, r, k, e, w = fa.dimTable
    elif SType == 'ASMEB18.3.3B':
        P_tbl, b_tbl, c, dk, dk_c, s_mean, t_min, r, k = fa.dimTable
    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── Pitch override (ThreadPitch mm / ThreadTPI) ───────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # ── Thread length override (ThreadLength from dashboard) ──────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 else b_tbl

    # ── Effective shank diameter from threading module CSV ───────────────
    # Replaces formula-based thread_dia with CSV-lookup d_eff
    d_eff      = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    thread_dia = d_eff   # keep thread_dia name for profile compatibility
    tr         = d_eff / 2.0

    FreeCAD.Console.PrintMessage(
        f"[Dipak] Threading: dia={dia:.4f}mm, "
        f"thread_dia={thread_dia:.4f}mm, {log_extra}, "
        f"allowance={dia - thread_dia:.4f}mm, "
        f"thread_length={b:.2f}mm\n"
    )

    # ── Head geometry ─────────────────────────────────────────────────────
    e_cham = 2.0 * s_mean / sqrt3 * 1.005
    ak     = -(4 * (k - c) ** 2 + e_cham ** 2 - dk ** 2) / (8 * (k - c))
    rH     = math.sqrt((dk / 2.0) ** 2 + ak ** 2)
    alpha  = (math.atan(2 * (k - c + ak) / e_cham) + math.atan((2 * ak) / dk)) / 2

    # ── Revolve profile ───────────────────────────────────────────────────
    # Head uses full dia. Arc ends at (dia/2, -r); step inward to tr at
    # same z so the entire shaft is at thread_dia → volume changes correctly.
    fm = FSFaceMaker()
    fm.AddPoint(0.0,          k)
    fm.AddPoint(e_cham / 2.0, k)
    fm.AddArc(
        rH * math.cos(alpha),
        c - ak + rH * math.sin(alpha),
        dk / 2.0,
        c
    )
    fm.AddPoint((dk_c - c) / 2.0, c)
    fm.AddArc2(0.0, -c / 2, -180)
    fm.AddPoint(dia / 2 + r,  0.0)
    fm.AddArc2(0.0, -r, 90)             # ends at (dia/2, -r)
    fm.AddPoint(tr, -r)                 # step in to thread radius at same z

    if length - r > b:                  # partially threaded
        thread_length = b
        if not fa.Thread:
            fm.AddPoint(tr, -1 * (length - b))
    else:
        thread_length = length - r

    fm.AddPoint(tr,           -length + dia / 10)
    fm.AddPoint(dia * 4 / 10, -length)
    fm.AddPoint(0.0,          -length)

    shape = self.RevolveZ(fm.GetFace())

    # ── Cut hex recess into head ──────────────────────────────────────────
    recess = self.makeHexRecess(s_mean, t_min, True)
    recess.translate(Base.Vector(0.0, 0.0, k))
    shape = shape.cut(recess)

    # ── Thread cutter ─────────────────────────────────────────────────────
    if fa.Thread:

        tl_cut   = thread_length

        offset_z = -(length - thread_length)

        if is_asme:

            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

        else:

            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

    return shape