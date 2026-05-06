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
    torx_key = _torx_size_str(tt)

    # Get torx geometry for clamping bounds
    A, B, Re = _get_torx_ABRe(torx_key, standard)
    Re = Re if Re is not None else 0.1
    anchor_extra = max(2.0, 0.75 * A) if A is not None else 2.0

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

    total_h     = (z_top - z_base) + anchor_extra
    body_h      = max(total_h - chamfer_h, 0.01)
    actual_base = z_base - anchor_extra

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
        # Support both current max/min table and legacy compact table.
        csk_angle = math.radians(82)
        if len(fa.dimTable) >= 11:
            # Current CSV cols:
            # P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min
            P_tbl, A_max, A_min, H_max, H_min, O_max, O_min, \
                J_max, J_min, T_max, T_min = fa.dimTable
            dk_theo = A_max
            dk_mean = (A_max + A_min) / 2
            n_min   = (J_max + J_min) / 2
            t_mean  = (T_max + T_min) / 2
            b_tbl   = length
            r       = 0.25
        else:
            # Legacy CSV cols:
            # P, b, dk_theo, dk_mean, k, n_min, r, t_mean
            P_tbl, b_tbl, dk_theo, dk_mean, _k, n_min, r, t_mean = fa.dimTable
        chamfer_end = True
        recess = self.makeSlotRecess(n_min, t_mean, dk_theo)

    elif SType == "ASMEB18.6.3.1B":
        # Support both current max/min table and legacy compact table.
        csk_angle = math.radians(82)
        if len(fa.dimTable) >= 13:
            # Current CSV cols:
            # P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min,
            # T_max, T_min, p_max, p_min
            P_tbl, A_max, A_min, H_max, H_min, O_max, O_min, \
                J_max, J_min, T_max, T_min, p_max, p_min = fa.dimTable
            dk_theo = A_max
            dk_mean = (A_max + A_min) / 2
            n_min   = (J_max + J_min) / 2
            t_mean  = (T_max + T_min) / 2
            b_tbl   = length
            r       = 0.25
        else:
            # Legacy CSV cols:
            # P, b, dk_theo, dk_mean, k, n_min, r, t_mean
            P_tbl, b_tbl, dk_theo, dk_mean, _k, n_min, r, t_mean = fa.dimTable
        chamfer_end = True
        cT, mH = FsData["ASMEB18.6.3.1Bextra"][fa.calc_diam]
        recess = self.makeHCrossRecess(cT, mH * 25.4)

    elif SType == "ASMEB18.6.3.1C":
        # Current CSV cols:
        # P, A_max, A_min, H_max, H_min, O_max, O_min, DriveSize, p_max, p_min
        csk_angle = math.radians(82)
        P_tbl, A_max, A_min, H_max, H_min, O_max, O_min, \
            socket_no, p_max, p_min = fa.dimTable
        dk_theo = A_max
        dk_mean = (A_max + A_min) / 2
        k_val   = H_max    # head height
        b_tbl   = length
        r       = 0.25
        t_mean  = (p_max + p_min) / 2
        tt      = _torx_size_str(socket_no)
        chamfer_end = True
        recess = self.makeHexalobularRecessASME(tt, t_mean, False)
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(
                tt, -_fs_float(k_val), 0.0, standard="ASME",
                pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

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
        tt      = _torx_size_str(socket_no)
        t_mean  = (t_max  + t_min)  / 2
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)   # ISO 10664 dims
        if getattr(fa, "SecurityPin", False):
            # countersunk: z=0 is head top, z=-k is head bottom
            security_pin_solid = _make_security_pin_cylinder(tt, -_fs_float(k), 0.0, standard="ISO", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

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
        tt      = _torx_size_str(socket_no)
        t_mean  = (t_max  + t_min)  / 2
        k       = k_max   # ISO14582 only has k_max
        chamfer_end = True
        recess = self.makeHexalobularRecess(tt, t_mean, False)   # ISO 10664 dims
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, -_fs_float(k), 0.0, standard="ISO", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

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
        fm.AddPoint(dia * 4 / 10, -length)         # smooth outward tip chamfer
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
