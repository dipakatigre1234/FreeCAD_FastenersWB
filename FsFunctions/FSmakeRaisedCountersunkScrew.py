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

# -- Security pin helpers ----------------------------------------------------
# pin_r = (B/2 - Re) * 0.75 by default  (inscribed bore * 75%)
# User sets SecurityPinDiameter [mm]; 0 = use standard diameter.
# Chamfer: tiny 45-deg edge-break = min(pin_r*0.10, 0.25 mm)  max 0.25 mm.

def _fs_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return _fs_float(v[0])
    digits = "".join(c for c in str(v).strip() if c.isdigit() or c == ".")
    return float(digits) if digits else 0.0


def _torx_size_str(tt):
    """Normalise any Torx designator to e.g. "T25".

    Handles every format found in ISO and ASME CSV socket_no columns:
      - float   30.0       -> "T30"   (ISO CSVs store socket_no as float)
      - int     30         -> "T30"
      - string  "T30"      -> "T30"
      - string  "T30.0"    -> "T30"   (float with T prefix)
      - quoted  '"T30"'    -> "T30"   (CSV parsing artifact)
      - string  "30"       -> "T30"
    """
    s = str(tt).strip().strip('"').strip("'").strip().upper()
    if s.startswith("T"):
        num = s[1:]
        try:
            s = "T" + str(int(float(num)))
        except ValueError:
            pass
    else:
        try:
            s = "T" + str(int(float(s)))
        except ValueError:
            s = "T" + s
    return s


def _get_torx_ABRe(torx_key, standard="ISO"):
    """Return (A, B, Re) from iso10664def or asmeb18_6_3_torxdef."""
    from FastenerBase import FsData
    primary  = "asmeb18_6_3_torxdef" if standard.upper() == "ASME" else "iso10664def"
    fallback = "iso10664def"          if standard.upper() == "ASME" else "asmeb18_6_3_torxdef"
    for tbl in (primary, fallback):
        try:
            row = FsData[tbl][torx_key]
            return float(row[0]), float(row[1]), float(row[2])
        except (KeyError, IndexError, TypeError):
            pass
    return None, None, None


def _standard_pin_r(tt, standard="ISO"):
    """Standard (default) pin radius = (B/2 - Re) * 0.75."""
    torx_key = _torx_size_str(tt)
    A, B, Re = _get_torx_ABRe(torx_key, standard)
    if B is not None and Re is not None:
        return max((B / 2.0 - Re) * 0.75, 0.05)
    return 0.3   # absolute fallback


def _make_security_pin_cylinder(tt, z_base, z_top, standard="ISO", pin_dia_mm=0.0):
    """Tamper-resistant centre pin with tiny 45-deg edge chamfer.

    Parameters
    ----------
    tt         : Torx size string e.g. "T25"
    z_base     : Z of pin bottom (world coords)
    z_top      : Z of pin tip -- flush with head top
    standard   : "ISO" or "ASME"
    pin_dia_mm : User-specified diameter [mm].  0 = use standard diameter.
                 If non-zero, clamped to minimum Re (lobe fillet radius) so
                 the pin always contacts the recess body and never floats free.
    """
    ANCHOR_EXTRA = 2.0
    torx_key = _torx_size_str(tt)

    # Get torx geometry for clamping bounds
    A, B, Re = _get_torx_ABRe(torx_key, standard)
    Re = Re if Re is not None else 0.1

    if float(pin_dia_mm) > 0.0:
        pin_r = float(pin_dia_mm) / 2.0
        # Clamp: pin must be at least Re wide so it contacts the recess centre post.
        # If smaller than Re the pin floats inside the lobes without touching anything.
        pin_r = max(pin_r, Re)
    else:
        pin_r = _standard_pin_r(torx_key, standard)

    # Tiny 45-deg edge-break at tip -- max 0.25 mm regardless of pin size
    chamfer_h   = min(pin_r * 0.10, 0.25)
    chamfer_tip = pin_r - chamfer_h          # 45-deg bevel

    total_h     = (z_top - z_base) + ANCHOR_EXTRA
    body_h      = max(total_h - chamfer_h, 0.01)
    actual_base = z_base - ANCHOR_EXTRA

    body = Part.makeCylinder(
        pin_r, body_h,
        FreeCAD.Vector(0.0, 0.0, actual_base),
        FreeCAD.Vector(0.0, 0.0, 1.0))

    cone = Part.makeCone(
        pin_r, chamfer_tip, chamfer_h,
        FreeCAD.Vector(0.0, 0.0, z_top - chamfer_h),
        FreeCAD.Vector(0.0, 0.0, 1.0))

    # Prefer fused solid; fall back to compound to avoid coplanar-face (blue circle) bug
    try:
        result = body.fuse(cone)
        return result if result.isValid() else Part.makeCompound([body, cone])
    except Exception:
        return Part.makeCompound([body, cone])


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
        recess = self.makeHexalobularRecess(tt, t_mean, True)   # ISO 10664 dims
        recess.translate(Base.Vector(0.0, 0.0, f))
        if getattr(fa, "SecurityPin", False):
            # For raised countersunk: z=0 is head top, crown height = f above z=0
            # recess opens at z=f (crown top) downward
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(f), standard="ISO", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))
    elif SType == "ASMEB18.6.3.4A":
        # CSV cols (mm) - same notation as 10Adef:
        # P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min
        csk_angle = math.radians(82)
        P, A_max, A_min, H_max, H_min, O_max, O_min, \
            J_max, J_min, T_max, T_min = fa.dimTable
        dk_theo = A_max
        dk_mean = (A_max + A_min) / 2
        f       = O_max          # O = total oval head height (crown)
        n_min   = (J_max + J_min) / 2
        t_mean  = (T_max + T_min) / 2
        r  = 0.25
        b  = 25.4
        rf = (4 * f * f + dk_theo * dk_theo) / (8 * f)
        head_arc_angle = math.asin(min(dk_mean / 2.0 / rf, 1.0))
        ht = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        recess = self.makeSlotRecess(n_min, t_mean, dk_theo)
        recess.translate(Base.Vector(0.0, 0.0, ht))

    elif SType == 'ASMEB18.6.3.4B':
        # CSV cols (mm) - same notation as 10Bdef:
        # P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min, p_max, p_min
        csk_angle = math.radians(82)
        P, A_max, A_min, H_max, H_min, O_max, O_min, \
            J_max, J_min, T_max, T_min, p_max, p_min = fa.dimTable
        dk_theo = A_max
        dk_mean = (A_max + A_min) / 2
        f       = O_max
        t_mean  = (T_max + T_min) / 2
        r  = 0.25
        b  = 25.4
        rf = (4 * f * f + dk_theo * dk_theo) / (8 * f)
        head_arc_angle = math.asin(min(dk_mean / 2.0 / rf, 1.0))
        ht = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        cT, mH = FsData["ASMEB18.6.3.4Bextra"][fa.calc_diam]
        recess = self.makeHCrossRecess(cT, mH * 25.4)
        recess.translate(Base.Vector(0.0, 0.0, ht))

    elif SType == 'ASMEB18.6.3.4C':
        # CSV cols (mm) - same notation as 10Cdef:
        # P, A_max, A_min, H_max, H_min, O_max, O_min, DriveSize, p_max, p_min
        csk_angle = math.radians(82)
        P, A_max, A_min, H_max, H_min, O_max, O_min, \
            DriveSize, p_max, p_min = fa.dimTable
        dk_theo = A_max
        dk_mean = (A_max + A_min) / 2
        f       = O_max
        r  = 0.25
        b  = 25.4
        rf = (4 * f * f + dk_theo * dk_theo) / (8 * f)
        head_arc_angle = math.asin(min(dk_mean / 2.0 / rf, 1.0))
        ht     = rf - (dk_mean / 2.0) / math.tan(head_arc_angle)
        tt     = _torx_size_str(DriveSize)
        t_mean = (p_max + p_min) / 2
        recess = self.makeHexalobularRecessASME(tt, t_mean, True)
        recess.translate(Base.Vector(0.0, 0.0, ht))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(ht), standard="ASME", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))
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