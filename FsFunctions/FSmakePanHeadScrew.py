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


def _torx_entry_z_on_domed_head(torx_key, head_top_z, head_radius, standard="ISO"):
    """Height where the domed head surface meets the Torx outer diameter A."""
    A, _, _ = _get_torx_ABRe(torx_key, standard)
    if A is None:
        return head_top_z
    return head_top_z - head_radius + math.sqrt(
        max(head_radius * head_radius - A * A / 4.0, 0.0)
    )


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


def makePanHeadScrew(self, fa):
    """Create a pan-head screw with a rounded top and cylindrical sides.

    Supported types:
      - ISO 7045   Pan head screws with type H or type Z cross recess
      - ISO 14583  Hexalobular socket pan head screws
      - ASMEB18.6.3.9A/9B/9C/10A/10B/10C/12A/12B/12C
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
        tt     = _torx_size_str(socket_no)
        t      = (t_max  + t_min)  / 2
        k = rf - math.sqrt(rf ** 2 - A_ref ** 2 / 4) + k_torx
        recess = self.makeHexalobularRecess(tt, t, True)   # ISO 10664 dims
        recess.translate(Base.Vector(0.0, 0.0, k_torx))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(k_torx), standard="ISO", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

    # ── ASMEB18.6.3.9A – slotted pan head ────────────────────────────────────
    elif SType == "ASMEB18.6.3.9A":
        # CSV cols: P [in], A_max [mm], A_min [mm], H_max [mm], H_min [mm],
        #           O_max [mm], O_min [mm], J_max [mm], J_min [mm],
        #           T_max [mm], T_min [mm]
        P, A_max, A_min, H_max, H_min, O_max, O_min, \
            J_max, J_min, T_max, T_min = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2
        k      = (H_max + H_min) / 2
        O      = (O_max + O_min) / 2
        rf     = (4 * O * O + dk_max * dk_max) / (8 * O)
        J      = (J_max + J_min) / 2
        T      = (T_max + T_min) / 2
        recess = self.makeSlotRecess(J, T, dk_max)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.9B – cross-recessed pan head ──────────────────────────────
    elif SType == "ASMEB18.6.3.9B":
        # CSV cols: P [mm], A_max [mm], A_min [mm], H_max [mm], H_min [mm],
        #           O_max [mm], O_min [mm], M_ref [mm], Driver, p_max [mm], p_min [mm]
        P, A_max, A_min, H_max, H_min, O_max, O_min, \
            M_ref, Driver, p_max, p_min = fa.dimTable
        dk_max = (A_max + A_min) / 2
        k      = (H_max + H_min) / 2
        R_head = (O_max + O_min) / 2
        rf     = dk_max * 0.8
        mH     = M_ref
        cT     = int(_fs_float(Driver))
        acos_arg = (dk_max / 2.0 - R_head) / (rf - R_head)
        acos_arg = max(-1.0, min(1.0, acos_arg))
        intersect_angle_rad = math.acos(acos_arg)
        intersect_angle_deg = math.degrees(intersect_angle_rad)
        recess = self.makeHCrossRecess(cT, mH)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.9C – hexalobular pan head ─────────────────────────────────
    elif SType == "ASMEB18.6.3.9C":
        # CSV cols: P [mm], A_max [mm], A_min [mm], H_max [mm], H_min [mm],
        #           O_max [mm], O_min [mm], DriveSize, p_max [mm], p_min [mm]
        P, A_max, A_min, H_max, H_min, O_max, O_min, DriveSize, p_max, p_min = fa.dimTable
        dk_max = (A_max + A_min) / 2
        k_torx = (H_max + H_min) / 2
        k      = k_torx
        O      = (O_max + O_min) / 2
        rf     = (4 * O * O + dk_max * dk_max) / (8 * O)
        tt     = _torx_size_str(DriveSize)
        t      = (p_max + p_min) / 2
        entry_z = _torx_entry_z_on_domed_head(tt, k_torx, rf, "ASME")
        recess = self.makeHexalobularRecessASME(tt, t, True)
        recess.translate(Base.Vector(0.0, 0.0, entry_z))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(entry_z), standard="ASME", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

    # ── ASMEB18.6.3.10A – slotted oval-head ──────────────────────────────────
    elif SType == "ASMEB18.6.3.10A":
        # CSV cols (in): P, A_max, A_min, H_max, H_min, O_max, O_min,
        #                J_max, J_min, T_max, T_min
        P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2 * 25.4
        H      = (H_max + H_min) / 2 * 25.4
        k      = (O_max + O_min) / 2 * 25.4
        J      = (J_max + J_min) / 2 * 25.4
        T      = (T_max + T_min) / 2 * 25.4
        rh     = k - H
        rf     = (4 * rh * rh + dk_max * dk_max) / (8 * rh)
        recess = self.makeSlotRecess(J, T, dk_max)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.10B – cross-recessed oval-head ────────────────────────────
    elif SType == "ASMEB18.6.3.10B":
        # CSV cols (in): P, A_max, A_min, H_max, H_min, O_max, O_min,
        #                J_max, J_min, T_max, T_min, p_max, p_min
        P, A_max, A_min, H_max, H_min, O_max, O_min, J_max, J_min, T_max, T_min, p_max, p_min = fa.dimTable
        raw_mH, raw_cT = FsData["ASMEB18.6.3.10Bextra"][fa.calc_diam]
        mH = _fs_float(raw_mH) * 25.4
        cT = int(_fs_float(raw_cT))
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
        # CSV cols (in): P, A_max, A_min, H_max, H_min, O_max, O_min,
        #                DriveSize, p_max, p_min
        P, A_max, A_min, H_max, H_min, O_max, O_min, DriveSize, p_max, p_min = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2 * 25.4
        H      = (H_max + H_min) / 2 * 25.4
        k      = (O_max + O_min) / 2 * 25.4
        rh     = k - H
        rf     = (4 * rh * rh + dk_max * dk_max) / (8 * rh)
        r      = 0.25
        tt     = _torx_size_str(DriveSize)
        t      = (p_max + p_min) / 2 * 25.4
        entry_z = _torx_entry_z_on_domed_head(tt, k, rf, "ASME")
        recess = self.makeHexalobularRecessASME(tt, t, True)
        recess.translate(Base.Vector(0.0, 0.0, entry_z))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(entry_z), standard="ASME", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

    # ── ASMEB18.6.3.12A – slotted truss head ─────────────────────────────────
    elif SType == "ASMEB18.6.3.12A":
        # Compact CSV cols from asmeb18.6.3.12def.csv:
        # P [in], A [in], H [in], R [in], J [in], T [in]
        P, A, H, R, J, T = fa.dimTable
        P, A, H, R, J, T = (25.4 * x for x in (P, A, H, R, J, T))
        dk_max = A
        k      = H
        rf     = R
        recess = self.makeSlotRecess(J, T, dk_max)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.12B – cross recessed truss head ───────────────────────────
    elif SType == "ASMEB18.6.3.12B":
        # Compact CSV cols from asmeb18.6.3.12def.csv:
        # P [in], A [in], H [in], R [in], J [in], T [in]
        # Cross-recess specifics come from ASMEB18.6.3.12Cextra in this repo.
        P, A, H, R, _J, _T = fa.dimTable
        mH, cT = FsData["ASMEB18.6.3.12Cextra"][fa.calc_diam]
        P, A, H, R, mH = (25.4 * x for x in (P, A, H, R, mH))
        dk_max = A
        k      = H
        rf     = R
        # The available ISO 4757 recess geometry only goes up to type 4.
        # Keep the family stable for larger diameters instead of jumping shape.
        cT = min(int(_fs_float(cT)), 4)
        recess = self.makeHCrossRecess(cT, mH)
        recess.translate(Base.Vector(0.0, 0.0, k))

    # ── ASMEB18.6.3.12C – hexalobular truss head ──────────────────────────────
    elif SType == "ASMEB18.6.3.12C":
        # CSV cols (mm) - same notation as 10Cdef but R instead of O:
        # P, A_max, A_min, H_max, H_min, R, DriveSize, p_max, p_min
        P, A_max, A_min, H_max, H_min, R, DriveSize, p_max, p_min = fa.dimTable
        P      = P * 25.4
        dk_max = (A_max + A_min) / 2
        k      = (H_max + H_min) / 2
        rf     = R
        r      = 0.25
        tt     = _torx_size_str(DriveSize)
        t      = (p_max + p_min) / 2
        entry_z = _torx_entry_z_on_domed_head(tt, k, rf, "ASME")
        recess = self.makeHexalobularRecessASME(tt, t, True)
        recess.translate(Base.Vector(0.0, 0.0, entry_z))
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(entry_z), standard="ASME", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

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
        if raw_tlen <= 0.0:
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

    if SType == "ASMEB18.6.3.9B":
        fm.AddArc2(0.0, -rf, intersect_angle_deg - 90.0)
        fm.AddArc2(-R_head * math.cos(intersect_angle_rad),
                   -R_head * math.sin(intersect_angle_rad), -intersect_angle_deg)
    elif SType in ("ASMEB18.6.3.10A", "ASMEB18.6.3.10B",
                   "ASMEB18.6.3.12A", "ASMEB18.6.3.12B", "ASMEB18.6.3.12C",
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
    fm.AddPoint(d_eff * 4 / 10, -length)    # smooth outward tip chamfer
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
