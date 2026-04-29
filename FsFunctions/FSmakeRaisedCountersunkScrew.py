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
    z_base : bottom of pin (extended below head base for robust fuse)
    z_top  : tip of pin (flush with head top surface)
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





def makeRaisedCountersunkScrew(self, fa):
    """creates a countersunk (or 'flat-head') screw
    The top of the screw is rounded.
    supported types:
    - ISO 2010 Slotted raised countersunk head screws
    - ISO 7047 raised countersunk head screws with H cross recess
    - ISO 14584 raised countersunk head screws with hexalobular recess
    """
    SType   = fa.baseType
    length  = fa.calc_len
    dia     = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")
    security_pin_solid = None
    if SType == "ISO2010":
        csk_angle = math.radians(90)
        P, _, b, dk_theo, dk_mean, _, n_min, r, t_mean, _ = fa.dimTable
        rf, t_mean, cT, mH, _ = FsData["Raised_countersunk_def"][fa.calc_diam]
        # Lengths and angles for calculation of head rounding
        head_arc_angle = math.asin(dk_mean / 2.0 / rf)  # angle of head edge
        # height of raised head top
        ht = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        recess = self.makeSlotRecess(n_min, t_mean, dk_theo)
        recess.translate(Base.Vector(0.0, 0.0, ht))
    elif SType == "ISO7047":
        csk_angle = math.radians(90)
        P, _, b, dk_theo, dk_mean, _, n_min, r, t_mean, _ = fa.dimTable
        rf, t_mean, cT, mH, _ = FsData["Raised_countersunk_def"][fa.calc_diam]
        head_arc_angle = math.asin(dk_mean / 2.0 / rf)
        ht = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        recess = self.makeHCrossRecess(cT, mH)
        recess.translate(Base.Vector(0.0, 0.0, ht))
    elif SType == "ISO14584":
        # CSV cols: P, a_max, b_min, dk_theo, dk_max, dk_min, f_max, f_min,
        #           r_min, rf, socket_no, A_ref, t_max, t_min  (14 cols)
        csk_angle = math.radians(90)
        (P, a_max, b,
         dk_theo, dk_max, dk_min,
         f_max, f_min,
         r, rf,
         socket_no, A_ref,
         t_max, t_min) = fa.dimTable
        # Mean values (default)
        dk_mean = (dk_max + dk_min) / 2
        f       = (f_max  + f_min)  / 2   # crown height (mean)
        tt      = _torx_size_str(socket_no)      # already 'T30' or numeric
        A       = A_ref
        t_mean  = (t_max  + t_min)  / 2
        head_arc_angle = math.asin(dk_mean / 2.0 / rf)
        ht = rf - math.sqrt(rf**2 - A**2 / 4) + f
        recess = self.makeHexalobularRecess(tt, t_mean, True)
        recess.translate(Base.Vector(0.0, 0.0, f))
        if getattr(fa, "SecurityPin", False):
            # For raised countersunk: z=0 is head top, crown height = f above z=0
            # recess opens at z=f (crown top) downward
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(f))
    elif SType == "ASMEB18.6.3.4A":
        csk_angle = math.radians(82)
        P, dk_theo, dk_mean, _, f, n_min, t_mean = fa.dimTable
        # Lengths and angles for calculation of head rounding
        r = 0.25  # ASME doesn't spec a radius, so just assume 0.25mm
        b = 25.4  # ASME doesn't spec, so just assume 1"
        # Calculate head radius (rf)
        rf = (4 * f * f + dk_theo * dk_theo) / (8 * f)
        head_arc_angle = math.asin(dk_mean / 2.0 / rf)  # angle of head edge
        # height of raised head top
        ht = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        recess = self.makeSlotRecess(n_min, t_mean, dk_theo)
        recess.translate(Base.Vector(0.0, 0.0, ht))
    elif SType == 'ASMEB18.6.3.4B':
        csk_angle = math.radians(82)
        P, dk_theo, dk_mean, _, f, _, _ = fa.dimTable
        # Lengths and angles for calculation of head rounding
        r = 0.25    #ASME doesn't spec a radius, so just assume 0.25mm
        b = 25.4    #ASME doesn't spec, so just assume 1"
        #Calculate head radius (rf)
        rf = (4 * f * f + dk_theo * dk_theo) / (8 * f)
        head_arc_angle = math.asin(dk_mean / 2.0 / rf)  # angle of head edge
        # height of raised head top
        ht = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        cT, mH = FsData["ASMEB18.6.3.4Bextra"][fa.calc_diam]
        recess = self.makeHCrossRecess(cT, mH * 25.4)
        recess.translate(Base.Vector(0.0, 0.0, ht))
    elif SType == 'ASMEB18.6.3.4C':
        # Hexalobular (Torx) oval countersunk — ASME B18.6.3 Table 4C
        # CSV cols: P, A_max, A_mean, H, C, socket_no, recess_dia_ref, p_max, p_min  (9 cols)
        csk_angle = math.radians(82)
        P, dk_theo, dk_mean, _, f, socket_no, recess_dia_ref, p_max, p_min = fa.dimTable
        r  = 0.25    # ASME doesn't spec a radius; assume 0.25mm
        b  = 25.4    # ASME doesn't spec thread length; assume 1"
        rf = (4 * f * f + dk_theo * dk_theo) / (8 * f)
        head_arc_angle = math.asin(dk_mean / 2.0 / rf)
        ht     = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        tt     = _torx_size_str(socket_no)
        t_mean = (p_max + p_min) / 2
        recess = self.makeHexalobularRecess(tt, t_mean, True)
        recess.translate(Base.Vector(0.0, 0.0, ht))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(ht))
    # lay out fastener profile
    # ── Pitch override (ThreadPitch / ThreadTPI from dashboard) ───────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) else P

    # ── Thread length override (Thread_Length from dashboard) ─────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        b = min(float(raw_tlen), length)

    # ── Effective shank diameter from threading module ────────────────────
    d_eff      = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    tr         = d_eff / 2.0

    head_flat_ht = (dk_theo - dk_mean) / 2 / math.tan(csk_angle / 2)
    sharp_corner_ht = -1 * (
        head_flat_ht + (dk_mean - dia) / (2 * math.tan(csk_angle / 2))
    )
    fillet_start_ht = sharp_corner_ht - r * math.tan(csk_angle / 4)
    fm = FSFaceMaker()
    fm.AddPoint(0.0, -length)
    fm.AddPoint(d_eff * 4 / 10, -length)
    fm.AddPoint(tr, -length + d_eff / 10)
    if length + fillet_start_ht > b:  # partially threaded fastener
        thread_length = b
        if not fa.Thread:
            fm.AddPoint(tr, -length + thread_length)
    else:
        thread_length = length + fillet_start_ht
    fm.AddPoint(tr, fillet_start_ht)
    fm.AddArc2(r, 0.0, -math.degrees(csk_angle / 2))
    fm.AddPoint(dk_mean / 2, -head_flat_ht)
    fm.AddPoint(dk_mean / 2, 0.0)
    fm.AddArc(
        rf * math.sin(head_arc_angle / 2),
        ht + rf * (math.cos(head_arc_angle / 2) - 1),
        0.0,
        ht,
    )
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
    if fa.Thread:
        tl_cut   = thread_length
        offset_z = -(length - thread_length)
        if is_asme:
            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)
        else:
            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)
    return shape
