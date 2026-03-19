# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2022                                                    *
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


def makeFlangedSquareHeadBolt(self, fa):
    """Creates a screw with a chamfered square head and a cylindrical collar.

    Supported types:
    - DIN 478 Square head bolts with collar

    Thread diameter formula (Dipak):
      Metric : thread_dia = dia - 0.15 * P
    """
    dia    = self.getDia(fa.calc_diam, False)
    length = fa.calc_len

    # ── Unpack dimTable ───────────────────────────────────────────────────
    if fa.baseType == "DIN478":
        P_tbl, b1, b2, c, da, dc, e, k, r, s = fa.dimTable
        b_tbl = b1 if length < 125 else b2
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.baseType}")

    # ── Pitch override (ThreadPitch from dashboard) ───────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # ── Thread length override (ThreadLength from dashboard) ──────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 else b_tbl

    # ── Thread diameter: metric formula ──────────────────────────────────
    # thread_dia = dia - 0.15 * P
    thread_dia = dia - 0.15 * P
    tr         = thread_dia / 2.0

    FreeCAD.Console.PrintMessage(
        f"[Dipak] Threading: dia={dia:.4f}mm, "
        f"thread_dia={thread_dia:.4f}mm, P={P:.3f}mm, "
        f"allowance={dia - thread_dia:.4f}mm, "
        f"thread_length={b:.2f}mm\n"
    )

    # ── Square head revolve (unchanged — uses s/e geometry, not dia) ──────
    fm = FSFaceMaker()
    fm.AddPoint(0.0,   k)
    fm.AddPoint(s / 2, k)
    fm.AddPoint(e / 2, k - (e - s) / 2 * math.tan(math.radians(30)))
    fm.AddPoint(e / 2, 0.1)
    fm.AddPoint(0.0,   0.1)
    head_revolve = self.RevolveZ(fm.GetFace())
    head_square  = Part.makeBox(s, s, k, Base.Vector(-s / 2, -s / 2, 0.0))
    head_square  = head_revolve.common(head_square)

    # ── Collar + shaft revolve ────────────────────────────────────────────
    # Arc ends at (dia/2, -r); step inward to tr at same z so the entire
    # shaft is at thread_dia → volume changes correctly.
    fm.Reset()
    fm.AddPoint(0.0,              c)
    fm.AddPoint(dc / 2 - c / 4,  c)
    fm.AddArc2(0.0, -c / 4, -90)
    fm.AddPoint(dc / 2,           0.0)
    fm.AddPoint(dia / 2 + r,      0.0)
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
    shape = shape.fuse(head_square)

    # ── Thread cutter ─────────────────────────────────────────────────────
    if fa.Thread:
        thread_cutter = self.CreateBlindThreadCutter(thread_dia, P, thread_length)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -1 * (length - thread_length)))
        shape = shape.cut(thread_cutter)

    return shape