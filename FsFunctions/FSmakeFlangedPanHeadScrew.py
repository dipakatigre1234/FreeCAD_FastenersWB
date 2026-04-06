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

import FastenerBase


def makeFlangedPanHeadScrew(self, fa):
    """Create a pan head screw with a flange.

    Supported types:
    - DIN 967 cross recessed pan head screw with collar

    Thread diameter formula (Dipak):
      Metric : thread_dia = dia - 0.15 * P
    """
    SType  = fa.baseType
    length = fa.calc_len
    dia    = self.getDia(fa.calc_diam, False)

    # ── Unpack dimTable ───────────────────────────────────────────────────
    if SType == 'DIN967':
        P_tbl, b_tbl, c, da, dk, r, k, rf, x, cT, mH, mZ = fa.dimTable
        alpha  = math.acos((rf - k + c) / rf)
        recess = self.makeHCrossRecess(cT, mH)
        recess.translate(Base.Vector(0.0, 0.0, k))
    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── Pitch override (ThreadPitch from dashboard) ───────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # ── Thread length override (ThreadLength from dashboard) ──────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 else b_tbl

    # ── Effective thread diameter from proper threading module ────────────
    is_asme = fa.baseType.startswith("ASME")
    if is_asme:
        d_eff = _TA.get_shank_dia(fa, dia)
    else:
        d_eff = _TM.get_shank_dia(fa, dia)
    tr = d_eff / 2.0

    FreeCAD.Console.PrintMessage(
        f"[FlangedPanHead] dia={dia:.4f}mm  d_eff={d_eff:.4f}mm  "
        f"P={P:.4f}mm  thread_length={b:.2f}mm\n"
    )

    # ── Revolve profile ───────────────────────────────────────────────────
    # Head uses full dia. Arc ends at (dia/2, -r); step inward to tr at
    # same z so the entire shaft is at thread_dia → volume changes correctly.
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(0.0, k)
    fm.AddArc(
        rf * math.sin(alpha / 2.0),
        k - rf + rf * math.cos(alpha / 2.0),
        rf * math.sin(alpha),
        c
    )
    fm.AddPoint(dk / 2.0,      c)
    fm.AddPoint(dk / 2.0,      0.0)
    fm.AddPoint(dia / 2.0 + r, 0.0)
    fm.AddArc2(0.0, -r, 90)             # ends at (dia/2, -r)
    fm.AddPoint(tr, -r)                 # step in to thread radius at same z

    if length - r > b:                  # partially threaded
        thread_length = b
        if not fa.Thread:
            fm.AddPoint(tr, -1 * (length - b))
    else:
        thread_length = length - r

    fm.AddPoint(tr,  -length)
    fm.AddPoint(0.0, -length)

    shape = self.RevolveZ(fm.GetFace())
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