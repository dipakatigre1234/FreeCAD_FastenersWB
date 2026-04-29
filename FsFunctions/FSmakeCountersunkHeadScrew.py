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

# ── Security pin helpers ──────────────────────────────────────────────────────
_TORX_PIN_DIA_MM = {
    "T6":  0.56, "T7":  0.56, "T8":  0.68, "T9":  0.68, "T10": 0.84,
    "T15": 1.12, "T20": 1.40, "T25": 1.68, "T27": 1.68, "T30": 2.10,
    "T40": 2.80, "T45": 3.36, "T50": 4.20,
}
_TORX_CHAMFER_H = 0.10

def _fs_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return _fs_float(v[0])
    digits = ''.join(c for c in str(v).strip() if c.isdigit() or c == '.')
    return float(digits) if digits else 0.0

def _torx_size_str(tt):
    s = str(tt).strip().upper()
    return s if s.startswith("T") else "T" + s

def _make_security_pin_cylinder(tt, z_base, z_top):
    """Create a security (tamper-resistant) centre pin solid.
    z_base : bottom of pin; extended further down by ANCHOR_EXTRA for robust fuse.
    z_top  : tip of pin (flush with head top surface, which is z=0 for countersunk).
    """
    ANCHOR_EXTRA = 2.0
    torx_key = _torx_size_str(tt)
    pin_r    = _TORX_PIN_DIA_MM.get(torx_key, None)
    total_h  = (z_top - z_base) + ANCHOR_EXTRA
    if pin_r is None:
        pin_r = min(total_h * 0.20, 2.0)
    else:
        pin_r = pin_r / 2.0
    chamfer_h   = _TORX_CHAMFER_H
    chamfer_r   = chamfer_h
    body_h      = total_h - chamfer_h
    actual_base = z_base - ANCHOR_EXTRA
    body = Part.makeCylinder(pin_r, body_h,
               FreeCAD.Vector(0.0, 0.0, actual_base), FreeCAD.Vector(0.0, 0.0, 1.0))
    cone = Part.makeCone(pin_r, max(pin_r - chamfer_r, pin_r * 0.1), chamfer_h,
               FreeCAD.Vector(0.0, 0.0, z_top - chamfer_h), FreeCAD.Vector(0.0, 0.0, 1.0))
    try:
        return body.fuse(cone)
    except Exception:
        return body



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

    elif SType == "ASMEB18.6.3.1C":
        # CSV cols: P, b, dk_theo, dk_mean, k, socket_no, recess_dia_ref, p_max, p_min  (9 cols)
        # NOTE: all numeric values are already stored in mm (same convention as 1A/1B)
        csk_angle = math.radians(82)
        P_tbl, b_tbl, dk_theo, dk_mean, k_val, socket_no, recess_dia_ref, p_max, p_min = fa.dimTable
        r = 0.25     # ASME doesn't spec a radius; assume 0.25 mm
        t_mean = (p_max + p_min) / 2   # recess depth in mm
        tt = _torx_size_str(socket_no) # already 'T5', 'T6', etc.
        chamfer_end = False
        recess = self.makeHexalobularRecess(tt, t_mean, False)
        if getattr(fa, "SecurityPin", False):
            # countersunk: z=0 is head top, z=-k_val is head bottom (all in mm)
            security_pin_solid = _make_security_pin_cylinder(tt, -_fs_float(k_val), 0.0)

    elif SType == "ISO7046":
        csk_angle = math.radians(90)
        P_tbl, _, b_tbl, dk_theo, dk_mean, _, n_min, r, t_mean, _ = fa.dimTable
        chamfer_end = False
        cT, mH, _ = FsData["ISO7046extra"][fa.calc_diam]
        recess = self.makeHCrossRecess(cT, mH)

    elif SType == "ISO14581":
        # CSV cols: P, a_max, b, dk_theo, dk_max, dk_min, ds, k_max, k_min,
        #           r_max, r_min, x_max, socket_no, A_ref, t_max, t_min  (16 cols)
        csk_angle = math.radians(90)
        (P_tbl, a, b_tbl,
         dk_theo, dk_max, dk_min,
         ds,
         k_max, k_min,
         r_max, r_min,
         x_max,
         socket_no, A_ref,
         t_max, t_min) = fa.dimTable
        # Mean values (default)
        dk_mean = (dk_max + dk_min) / 2
        k       = (k_max  + k_min)  / 2
        r       = (r_max  + r_min)  / 2
        tt      = _torx_size_str(int(socket_no))
        t_mean  = (t_max  + t_min)  / 2
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)
        if getattr(fa, "SecurityPin", False):
            # countersunk: z=0 is head top, z=-k is head bottom
            security_pin_solid = _make_security_pin_cylinder(tt, -_fs_float(k), 0.0)

    elif SType == "ISO14582":
        # CSV cols: P, a_max, b, dk_theo, dk_max, dk_min, ds_max, ds_min,
        #           dg_max, dg_min, rc_max, k_max, r_min, socket_no, A_ref,
        #           t_max, t_min  (17 cols)
        csk_angle = math.radians(90)
        (P_tbl, _, b_tbl,
         dk_theo, dk_max, dk_min,
         ds_max, ds_min,
         dg_max, dg_min,
         rc_max,
         k_max,
         r_min,
         socket_no, A_ref,
         t_max, t_min) = fa.dimTable
        # Mean values (default)
        dk_mean = (dk_max + dk_min) / 2
        r       = r_min
        tt      = _torx_size_str(int(socket_no))
        t_mean  = (t_max  + t_min)  / 2
        k       = k_max   # ISO14582 only has k_max
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, -_fs_float(k), 0.0)

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
        f"thread_dia={thread_dia:.4f}mm, "
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
    if security_pin_solid is not None:
        try:
            fused = shape.fuse(security_pin_solid)
            if fused.isValid():
                shape = fused
            else:
                shape = Part.makeCompound([shape, security_pin_solid])
        except Exception as _pin_err:
            FreeCAD.Console.PrintWarning(
                f"[SecurityPin] fuse failed ({_pin_err}), using compound\n")
            shape = Part.makeCompound([shape, security_pin_solid])

    # ── Thread cutter ─────────────────────────────────────────────────────
    if fa.Thread:

        tl_cut   = thread_length

        offset_z = -(length - thread_length)

        if is_asme:

            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

        else:

            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

    return shape