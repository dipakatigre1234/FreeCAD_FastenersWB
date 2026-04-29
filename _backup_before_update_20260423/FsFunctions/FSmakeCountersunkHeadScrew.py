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

from FastenerBase import FSFaceMaker
import math


# ── Helper: safely extract a float from dimTable values ──────────────────────
# dimTable entries can be plain float, tuple/list, or Torx-code strings ('T10').
# For geometry we only ever need t_mean (recess depth), which is always numeric.
def _fs_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return _fs_float(v[0])
    digits = ''.join(c for c in str(v).strip() if c.isdigit() or c == '.')
    return float(digits) if digits else 0.0


def _make_security_pin(t_mean_val):
    """Return a chamfered-top cylinder solid for a security/tamper-resistant pin.

    Geometry (all Z relative to head top surface = Z 0):
      - Pin body  : plain cylinder,  base Z = -t_mean_val  →  top Z = -chamfer_h
      - Pin chamfer: frustum (cone), base Z = -chamfer_h   →  tip  Z =  0
                     radius shrinks from pin_r → (pin_r - chamfer_r) over chamfer_h
    The base at Z = -t_mean_val is the recess floor — the pin grows upward
    from there so it is always physically connected to the head material.

    The chamfer is very small: chamfer_h = 8 % of pin_r (≈ 0.03–0.07 mm
    for typical M3–M8 screws), giving a subtle but visible top bevel.
    """
    pin_r     = t_mean_val * 0.30        # pin radius  ≈ 30 % of recess depth
    pin_h     = t_mean_val               # total height = full recess depth
    chamfer_h = pin_r * 0.08             # very small chamfer height
    chamfer_r = chamfer_h                # 45° chamfer  → δr = δh

    body_h    = pin_h - chamfer_h        # plain cylinder height

    # Cylinder body — base at recess floor, top just below head surface
    body = Part.makeCylinder(
               pin_r, body_h,
               FreeCAD.Vector(0.0, 0.0, -pin_h),
               FreeCAD.Vector(0.0, 0.0,  1.0))

    # Chamfer frustum — sits on top of cylinder, tip flush with Z = 0
    cone = Part.makeCone(
               pin_r, pin_r - chamfer_r, chamfer_h,
               FreeCAD.Vector(0.0, 0.0, -chamfer_h),
               FreeCAD.Vector(0.0, 0.0,  1.0))

    return body.fuse(cone)


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

    # Flag: True for ISO14581/14582 — pin is added after shape is built
    security_pin_solid = None

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
        FreeCAD.Console.PrintMessage(f"[Dipak-debug] ISO14581 dimTable={fa.dimTable}\n")
        P_tbl, a, b_tbl, dk_theo, dk_mean, k, r, tt, A, t_mean = fa.dimTable
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)
        # ── Security pin: height = k (actual head height) ─────────────────
        # t_mean is socket engagement depth (tiny, ~0.25 mm).
        # k is the full countersunk head height (e.g. 4.22 mm).
        # Pin spans from Z = -k (head floor) → Z = 0 (head top surface).
        security_pin_solid = _make_security_pin(_fs_float(k))

    elif SType == "ISO14582":
        csk_angle = math.radians(90)
        FreeCAD.Console.PrintMessage(f"[Dipak-debug] ISO14582 dimTable={fa.dimTable}\n")
        # ISO14582 dimTable: P_tbl, dk_ref, b_tbl, dk_theo, dk_mean, k, r, tt, A, t_mean
        # Unpack all 10 cols so k (head height) is captured, not discarded.
        P_tbl, _dk_ref, b_tbl, dk_theo, dk_mean, k, r, tt, _A, t_mean = fa.dimTable
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)
        security_pin_solid = _make_security_pin(_fs_float(k))

    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── Pitch override (ThreadPitch mm / ThreadTPI) ───────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # ── Thread length override (ThreadLength from dashboard) ──────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 else b_tbl

    # ── Effective shank diameter from threading module CSV ───────────────
    d_eff      = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    thread_dia = d_eff
    tr         = d_eff / 2.0

    FreeCAD.Console.PrintMessage(
        f"[Dipak] Threading: dia={dia:.4f}mm, "
        f"thread_dia={thread_dia:.4f}mm, "
        f"allowance={dia - thread_dia:.4f}mm, "
        f"thread_length={b:.2f}mm\n"
    )

    # ── Head geometry ─────────────────────────────────────────────────────
    head_flat_ht    = (dk_theo - dk_mean) / 2 / math.tan(csk_angle / 2)
    sharp_corner_ht = -1 * (head_flat_ht + (dk_mean - dia) / (2 * math.tan(csk_angle / 2)))
    fillet_start_ht = sharp_corner_ht - r * math.tan(csk_angle / 4)

    # ── Revolve profile ───────────────────────────────────────────────────
    fm = FSFaceMaker()
    fm.AddPoint(0.0, -length)

    if chamfer_end:
        fm.AddPoint(dia * 4 / 10, -length)
        fm.AddPoint(tr,           -length + dia / 10)
    else:
        fm.AddPoint(tr, -length)

    if length + fillet_start_ht > b:
        thread_length = b
        if not fa.Thread:
            fm.AddPoint(tr, -length + thread_length)
    else:
        thread_length = length + fillet_start_ht

    fm.AddPoint(tr, fillet_start_ht)
    fm.AddArc2(r, 0.0, -math.degrees(csk_angle / 2))
    fm.AddPoint(dk_mean / 2, -head_flat_ht)
    fm.AddPoint(dk_mean / 2,  0.0)
    fm.AddPoint(0.0,          0.0)

    shape = self.RevolveZ(fm.GetFace())
    shape = shape.cut(recess)

    # ── Fuse security pin AFTER recess cut ───────────────────────────────
    # The pin solid is positioned in the same coordinate system as the head
    # (Z=0 = head top, Z=-t_mean = recess floor). Fusing after the recess
    # cut ensures the pin base sits on actual solid head material and is
    # fully connected — no floating geometry.
    if security_pin_solid is not None:
        shape = shape.fuse(security_pin_solid)

    # ── Thread cutter ─────────────────────────────────────────────────────
    if fa.Thread:
        tl_cut   = thread_length
        offset_z = -(length - thread_length)
        if is_asme:
            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)
        else:
            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

    return shape