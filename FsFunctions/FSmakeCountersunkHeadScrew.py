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
from FastenerBase import FSFaceMaker
import math


def makeCountersunkHeadScrew(self, fa):
    """Creates a countersunk (flat-head) screw

    Supported types:
    - ISO 10642      hexagon socket countersunk head screws
    - ISO 2009       countersunk slotted flat head screws
    - ISO 7046       countersunk flat head screws with H cross recess
    - ISO 14581      hexalobular socket countersunk head screws, flat head
    - ISO 14582      hexalobular socket countersunk head screws, high head
    - ASMEB18.3.2    UNC hexagon socket countersunk head screws
    - ASMEB18.6.3.1A UNC slotted countersunk flat head screws
    - ASMEB18.6.3.1B UNC cross recessed countersunk flat head screws

    Thread diameter formulas (Dipak):
      ASME/inch : thread_dia = dia - 0.15 / TPI
      Metric    : thread_dia = dia - 0.15 * P
    """
    SType   = fa.baseType
    length  = fa.calc_len
    dia     = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")

    # ── Unpack dimTable ───────────────────────────────────────────────────
    if SType == "ISO10642":
        csk_angle = math.radians(90)
        P_tbl, b_tbl, dk_theo, dk_mean, _, _, _, _, r, s_mean, t, _ = fa.dimTable
        chamfer_end = True
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == "ASMEB18.3.2":
        csk_angle = math.radians(82)
        P_tbl, b_tbl, dk_theo, dk_mean, _, r, s_mean, t = fa.dimTable
        chamfer_end = True
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == "ISO2009":
        csk_angle = math.radians(90)
        P_tbl, _, b_tbl, dk_theo, dk_mean, _, n_min, r, t_mean, _ = fa.dimTable
        chamfer_end = False
        recess = self.makeSlotRecess(n_min, t_mean, dk_theo)

    elif SType == "ASMEB18.6.3.1A":
        csk_angle = math.radians(82)
        P_tbl, b_tbl, dk_theo, dk_mean, _, n_min, r, t_mean = fa.dimTable
        chamfer_end = False
        recess = self.makeSlotRecess(n_min, t_mean, dk_theo)

    elif SType == "ASMEB18.6.3.1B":
        csk_angle = math.radians(82)
        P_tbl, b_tbl, dk_theo, dk_mean, _, n_min, r, t_mean = fa.dimTable
        chamfer_end = False
        cT, mH = FsData["ASMEB18.6.3.1Bextra"][fa.calc_diam]
        recess = self.makeHCrossRecess(cT, mH * 25.4)

    elif SType == "ISO7046":
        csk_angle = math.radians(90)
        P_tbl, _, b_tbl, dk_theo, dk_mean, _, n_min, r, t_mean, _ = fa.dimTable
        chamfer_end = False
        cT, mH, _ = FsData["ISO7046extra"][fa.calc_diam]
        recess = self.makeHCrossRecess(cT, mH)

    elif SType == "ISO14581":
        csk_angle = math.radians(90)
        P_tbl, a, b_tbl, dk_theo, dk_mean, k, r, tt, A, t_mean = fa.dimTable
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)

    elif SType == "ISO14582":
        csk_angle = math.radians(90)
        P_tbl, _, b_tbl, dk_theo, dk_mean, _, r, tt, _, t_mean = fa.dimTable
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)

    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── Pitch override (ThreadPitch mm / ThreadTPI) ───────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # ── Thread length override (ThreadLength from dashboard) ──────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 else b_tbl

    # ── Thread diameter ───────────────────────────────────────────────────
    # ASME/inch : thread_dia = dia - 0.15 / TPI
    # Metric    : thread_dia = dia - 0.15 * P
    if is_asme:
        tpi = getattr(fa, "calc_tpi", None)
        if not tpi or tpi <= 0:
            tpi = round(25.4 / P_tbl)
        thread_dia = dia - (0.15 / tpi)
        log_extra  = f"TPI={tpi}"
    else:
        thread_dia = dia - 0.15 * P
        log_extra  = f"P={P:.3f}mm"

    tr = thread_dia / 2.0

    FreeCAD.Console.PrintMessage(
        f"[Dipak] Threading: dia={dia:.4f}mm, "
        f"thread_dia={thread_dia:.4f}mm, {log_extra}, "
        f"allowance={dia - thread_dia:.4f}mm, "
        f"thread_length={b:.2f}mm\n"
    )

    # ── Head geometry ─────────────────────────────────────────────────────
    head_flat_ht    = (dk_theo - dk_mean) / 2 / math.tan(csk_angle / 2)
    sharp_corner_ht = -1 * (head_flat_ht + (dk_mean - dia) / (2 * math.tan(csk_angle / 2)))
    fillet_start_ht = sharp_corner_ht - r * math.tan(csk_angle / 4)

    # ── Revolve profile ───────────────────────────────────────────────────
    # Shaft uses tr (= thread_dia/2) so revolved solid is at thread_dia
    # → volume changes correctly.
    fm = FSFaceMaker()
    fm.AddPoint(0.0, -length)

    if chamfer_end:
        fm.AddPoint(dia * 4 / 10, -length)
        fm.AddPoint(tr,           -length + dia / 10)
    else:
        fm.AddPoint(tr, -length)

    if length + fillet_start_ht > b:        # partially threaded
        thread_length = b
        if not fa.Thread:
            fm.AddPoint(tr, -length + thread_length)
    else:
        thread_length = length + fillet_start_ht

    fm.AddPoint(tr, fillet_start_ht)        # shaft at thread radius up to fillet
    fm.AddArc2(r, 0.0, -math.degrees(csk_angle / 2))
    fm.AddPoint(dk_mean / 2, -head_flat_ht)
    fm.AddPoint(dk_mean / 2,  0.0)
    fm.AddPoint(0.0,          0.0)

    shape = self.RevolveZ(fm.GetFace())
    shape = shape.cut(recess)

    # ── Thread cutter ─────────────────────────────────────────────────────
    if fa.Thread:
        thread_cutter = self.CreateBlindThreadCutter(thread_dia, P, thread_length)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -1 * (length - thread_length)))
        shape = shape.cut(thread_cutter)

    return shape