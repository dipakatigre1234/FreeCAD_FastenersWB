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

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM



def makeHeadlessScrew(self, fa):
    """Creates a headless screw with a smooth shank.

    Supported types:
      ISO 2342 - slotted headless screws with shank

    Thread diameter formula (Dipak):
      Metric : thread_dia = dia - 0.15 * P
    """
    SType  = fa.baseType
    dia    = self.getDia(fa.calc_diam, False)
    length = fa.calc_len

    # ── Unpack dimTable ───────────────────────────────────────────────────
    if SType == "ISO2342":
        P_tbl, b_tbl, d_s_min, d_s_max, n_nom, _, _, t_min, t_max, _ = fa.dimTable
        t    = (t_min + t_max) / 2
        n    = n_nom
        cham = dia / 10
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    # ── Pitch override (ThreadPitch from dashboard) ───────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # ── Thread length override (ThreadLength from dashboard) ──────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 else b_tbl

    # ── Thread diameter: metric formula ──────────────────────────────────
    # thread_dia = dia - 0.15 * P
    # This screw has a smooth shank (d_s) and a threaded end (thread_dia).
    # The smooth shank uses full dia; the threaded section uses tr.
    thread_dia = dia - 0.15 * P
    tr         = thread_dia / 2.0

    FreeCAD.Console.PrintMessage(
        f"[Dipak] Threading: dia={dia:.4f}mm, "
        f"thread_dia={thread_dia:.4f}mm, P={P:.3f}mm, "
        f"allowance={dia - thread_dia:.4f}mm, "
        f"thread_length={b:.2f}mm\n"
    )

    # ── Revolve profile ───────────────────────────────────────────────────
    # Smooth shank section uses full dia/2.
    # At the shank-to-thread transition (z = -length+b) step inward to tr
    # so the threaded portion is at thread_dia → volume changes correctly.
    fm = FSFaceMaker()
    fm.AddPoint(0.0,            0.0)
    fm.AddPoint(dia / 2 - cham, 0.0)
    fm.AddPoint(dia / 2,       -cham)
    fm.AddPoint(dia / 2,       -length + b)   # end of smooth shank
    fm.AddPoint(tr,            -length + b)   # step in to thread radius
    fm.AddPoint(tr,            -length + cham)
    fm.AddPoint(tr - cham,     -length)
    fm.AddPoint(0.0,           -length)

    shape = self.RevolveZ(fm.GetFace())

    # ── Slot recess ───────────────────────────────────────────────────────
    if SType == "ISO2342":
        slot_shape = Part.makeBox(
            n, 1.1 * dia, 1.1 * t,
            Base.Vector(-n / 2, -0.55 * dia, -t)
        )
        shape = shape.cut(slot_shape)

    # ── Thread cutter ─────────────────────────────────────────────────────
    if fa.Thread:
        thread_cutter = self.CreateBlindThreadCutter(thread_dia, P, b)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -1 * (length - b)))
        shape = shape.cut(thread_cutter)

    return shape