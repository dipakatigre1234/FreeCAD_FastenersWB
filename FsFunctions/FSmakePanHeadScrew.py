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
    """Safely coerce any scalar/list/tuple/string to float."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return _fs_float(v[0])
    digits = ''.join(c for c in str(v).strip() if c.isdigit() or c == '.')
    return float(digits) if digits else 0.0


def _torx_size_str(tt):
    """Normalise a Torx designator to e.g. 'T25'."""
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


def makePanHeadScrew(self, fa):
    """Create a pan-head screw with a rounded top and cylindrical sides.

    Supported types:
      - ISO 7045   Pan head screws with type H or type Z cross recess
      - ISO 14583  Hexalobular socket pan head screws
      - ASMEB18.6.3.9A/9B/9C/10A/10B/10C/12A/12C
    """
    SType   = fa.baseType
    length  = fa.calc_len
    dia     = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")
    security_pin_solid = None

    # ── ISO 7045 ──────────────────────────────────────────────────────────────
    if SType == "ISO7045":
        P, a, b, dk_max, da, k, r, rf, x, cT, mH, mZ = \
            FsData["ISO7045def"][fa.calc_diam]
        recess = self.makeHCrossRecess(cT, mH)
        beta_cr    = math.asin(mH / 2.0 / rf)
        tan_beta_cr = math.tan(beta_cr)
        hcr = k - rf + (mH / 2.0) / tan_beta_cr
        recess.translate(Base.Vector(0.0, 0.0, hcr))

    # ── ISO 14583 ─────────────────────────────────────────────────────────────
    elif SType == "ISO14583":
        # CSV cols: P, a_max, b_min, da_max, dk_max, dk_min, k_max, k_min,
        #           r_min, rf, x_max, socket_no, A_ref, t_max, t_min  (15 cols)
        (P, a_max, b,
         d_a_max,
         dk_max, dk_min,
         k_max, k_min,
         r, rf,
         x_max,
         socket_no, A_ref,
         t_max, t_min) = fa.dimTable
        dk_max = (dk_max + dk_min) / 2
        k_torx = (k_max  + k_min)  / 2
        tt     = _torx_size_str(int(socket_no))
        t      = (t_max  + t_min)  / 2
        k = rf - math.sqrt(rf ** 2 - A_ref ** 2 / 4) + k_torx
        recess = self.makeHexalobularRecess(tt, t, True)
        recess.translate(Base.Vector(0.0, 0.0, k_torx))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(k_torx))

    # ── ASMEB18.6.3.9A – slotted pan head ────────────────────────────────────
    elif SType == "ASMEB18.6.3.9A":
        # CSV cols (mm): P(in), A_max, A_min, H, R, J_max, T_max
        P, A_max, A_min, H, R_head, J_max, T_max = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2
        k      = H
        rf     = dk_max
        J      = J_max
        T      = T_max
        recess = self.makeSlotRecess(J, T, dk_max)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.9B – cross-recessed pan head ──────────────────────────────
    elif SType == "ASMEB18.6.3.9B":
        # CSV cols (mm): P, A_max, A_min, H_max, H_min, R, M_ref, Driver, p_max, p_min
        P, A_max, A_min, H_max, H_min, R_head, M_ref, Driver, p_max, p_min = fa.dimTable
        dk_max = (A_max + A_min) / 2
        k      = (H_max + H_min) / 2
        rf     = dk_max * 0.8
        mH     = (p_max + p_min) / 2
        # FIX: coerce Driver to plain int to avoid KeyError (3,) in iso4757def
        cT     = int(_fs_float(Driver))
        intersect_angle_rad = math.acos((dk_max / 2 - R_head) / (rf - R_head))
        intersect_angle_deg = math.degrees(intersect_angle_rad)
        recess = self.makeHCrossRecess(cT, mH)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.9C – hexalobular pan head ─────────────────────────────────
    elif SType == "ASMEB18.6.3.9C":
        # CSV cols (mm): P, A_max, A_min, H_max, H_min, R, socket_no, recess_dia_ref, p_max, p_min
        P, A_max, A_min, H_max, H_min, R, socket_no, recess_dia_ref, p_max, p_min = fa.dimTable
        dk_max = (A_max + A_min) / 2
        k      = (H_max + H_min) / 2
        r      = R
        rf     = dk_max * 0.8
        tt     = _torx_size_str(socket_no)
        t      = (p_max + p_min) / 2
        recess = self.makeHexalobularRecess(tt, t, True)
        recess.translate(Base.Vector(0.0, 0.0, k))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(k))

    # ── ASMEB18.6.3.10A – slotted oval-head ──────────────────────────────────
    elif SType == "ASMEB18.6.3.10A":
        # CSV cols (inches): P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min
        P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2 * 25.4
        H      = (H_max + H_min) / 2 * 25.4
        k      = (O_max + O_min) / 2 * 25.4
        J      = J_max * 25.4
        T      = T_max * 25.4
        rh     = k - H
        rf     = (4 * rh * rh + dk_max * dk_max) / (8 * rh)
        recess = self.makeSlotRecess(J, T, dk_max)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.10B – cross-recessed oval-head ────────────────────────────
    elif SType == "ASMEB18.6.3.10B":
        # CSV cols (inches): P, A_max, A_min, H_max, H_min, O_max, O_min,
        #                    J_max, J_min, T_max, T_min, p_max, p_min
        P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min, p_max, p_min = fa.dimTable
        # FIX: coerce both mH and cT read from the secondary lookup table
        # (rows stored as nested lists produce tuple unpacking → (3,) keys)
        raw_mH, raw_cT = FsData["ASMEB18.6.3.10Bextra"][fa.calc_diam]
        mH = _fs_float(raw_mH) * 25.4          # coerce + convert inches → mm
        cT = int(_fs_float(raw_cT))            # coerce to plain int for iso4757def lookup
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2 * 25.4
        H      = (H_max + H_min) / 2 * 25.4
        k      = (O_max + O_min) / 2 * 25.4
        rh     = k - H
        rf     = (4 * rh * rh + dk_max * dk_max) / (8 * rh)
        recess = self.makeHCrossRecess(cT, mH)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.10C – hexalobular oval-head ───────────────────────────────
    elif SType == "ASMEB18.6.3.10C":
        # CSV cols (inches): P, A_max, A_min, H_max, H_min, O_max, O_min, socket_no, p_max, p_min
        P, A_max, A_min, H_max, H_min, O_max, O_min, socket_no, p_max, p_min = fa.dimTable
        P      = P    * 25.4
        dk_max = (A_max + A_min) / 2 * 25.4
        H      = (H_max + H_min) / 2 * 25.4
        k      = (O_max + O_min) / 2 * 25.4
        rh     = k - H
        rf     = (4 * rh * rh + dk_max * dk_max) / (8 * rh)
        r      = 0.25
        tt     = _torx_size_str(socket_no)
        t      = (p_max + p_min) / 2 * 25.4
        recess = self.makeHexalobularRecess(tt, t, True)
        recess.translate(Base.Vector(0.0, 0.0, k))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(k))

    # ── ASMEB18.6.3.12A – slotted truss head ─────────────────────────────────
    elif SType == "ASMEB18.6.3.12A":
        # CSV cols (inches): P, A_max, A_min, H_max, H_min, R, J_max, J_min, T_max, T_min
        P, A_max, A_min, H_max, H_min, R, J_max, J_min, T_max, T_min = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2 * 25.4
        k      = (H_max + H_min) / 2 * 25.4
        rf     = R * 25.4
        J      = J_max * 25.4
        T      = T_max * 25.4
        recess = self.makeSlotRecess(J, T, dk_max)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.12C – hexalobular truss head ──────────────────────────────
    elif SType == "ASMEB18.6.3.12C":
        # CSV cols (inches): P, A_max, A_min, H_max, H_min, R, socket_no, recess_dia_ref, p_max, p_min
        P, A_max, A_min, H_max, H_min, R, socket_no, recess_dia_ref, p_max, p_min = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2 * 25.4
        k      = (H_max + H_min) / 2 * 25.4
        rf     = R * 25.4
        r      = 0.25
        tt     = _torx_size_str(socket_no)
        t      = (p_max + p_min) / 2 * 25.4
        recess = self.makeHexalobularRecess(tt, t, True)
        recess.translate(Base.Vector(0.0, 0.0, k))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(k))

    # ── Pitch override (Thread_Pitch / TPI from dashboard) ───────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) else P

    # ── Thread length override (Thread_Length from dashboard) ────────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        b = min(float(raw_tlen), length)

    # ── Effective shank diameter from threading module ────────────────────────
    d_eff = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    tr    = d_eff / 2.0

    # ASME types: apply defaults for unspecified geometry parameters
    if is_asme:
        r = 0.25          # fillet not specified in ASME; assume 0.25 mm
        b = 1.5 * 25.4    # max threaded length = 1.5" per para 2.4.1(b)

    # ── Head profile angles ───────────────────────────────────────────────────
    beta     = math.asin(dk_max / 2.0 / rf)   # angle of head edge
    tan_beta = math.tan(beta)
    alpha    = beta / 2.0                       # half angle
    he       = k - rf + (dk_max / 2.0) / tan_beta   # height of head edge
    h_arc_x  = rf * math.sin(alpha)
    h_arc_z  = k - rf + rf * math.cos(alpha)

    # ── Revolve profile ───────────────────────────────────────────────────────
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(0.0, k)

    if SType == "ASMEB18.6.3.9A":
        fm.AddPoint(dk_max / 2 - R_head, k)
        fm.AddArc2(0, -R_head, -90)
    elif SType == "ASMEB18.6.3.9B":
        fm.AddArc2(0.0, -rf, intersect_angle_deg - 90)
        fm.AddArc2(-R_head * math.cos(intersect_angle_rad),
                   -R_head * math.sin(intersect_angle_rad), -intersect_angle_deg)
    elif SType in ("ASMEB18.6.3.10A", "ASMEB18.6.3.10B",
                   "ASMEB18.6.3.12A", "ASMEB18.6.3.12C",
                   "ASMEB18.6.3.10C"):
        # NOTE: original code had a broken compound 'or' string comparison;
        # replaced with explicit tuple membership test.
        fm.AddArc2(0.0, -rf, -math.degrees(beta))
    else:
        fm.AddArc(h_arc_x, h_arc_z, dk_max / 2.0, he)

    fm.AddPoint(dk_max / 2.0, 0.0)
    fm.AddPoint(tr + r, 0.0)
    fm.AddArc2(0.0, -r, 90)

    if length - r > b:   # partially threaded fastener
        thread_length = b
        if not fa.Thread:
            fm.AddPoint(tr, -1 * (length - b))
    else:
        thread_length = length - r

    fm.AddPoint(tr, -length + d_eff / 10)
    fm.AddPoint(d_eff * 4 / 10, -length)
    fm.AddPoint(0.0, -length)
    shape = self.RevolveZ(fm.GetFace())

    # ── Cut recess ────────────────────────────────────────────────────────────
    shape = shape.cut(recess)

    # ── Fuse security pin (if requested) ─────────────────────────────────────
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

    # ── Cut thread ────────────────────────────────────────────────────────────
    if fa.Thread:
        tl_cut   = thread_length
        offset_z = -(length - thread_length)
        if is_asme:
            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)
        else:
            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

    return shape