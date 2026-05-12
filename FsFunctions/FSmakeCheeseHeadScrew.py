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


def makeCheeseHeadScrew(self, fa):
    """Create a cheese head screw

    supported types:
    - ISO 1207 slotted screw
    - ISO 7048 cross recessed screw
    - ISO 14580 Hexalobular socket cheese head screws
    """
    SType   = fa.baseType
    length  = fa.calc_len
    dia     = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")
    security_pin_solid = None
    if SType == "ISO1207" or SType == "DIN84":
        P, a, b, dk, dk_mean, da, k, n_min, r, t_min, x = fa.dimTable
        r_fil = r * 2.0
        recess = self.makeSlotRecess(n_min, t_min, dk)
    elif SType == "ISO7048":
        P, a, b, dk, dk_mean, da, k, r, x, cT, mH, mZ = fa.dimTable
        r_fil = r * 2.0
        recess = self.makeHCrossRecess(cT, mH)
    elif SType == "ISO1580":
        P, a, b, dk, da, k, n_min, r, rf, t_min, x = fa.dimTable
        r_fil = rf
        recess = self.makeSlotRecess(n_min, t_min, dk)
    elif SType == "ISO14580":
        # CSV cols: P, a_max, b_min, dk_max, dk_min, da_max, k_max, k_min,
        #           r_min, w_min, x_max, socket_no, A_ref, t_max, t_min  (15 cols)
        (P, a, b,
         dk_max, dk_min,
         da,
         k_max, k_min,
         r, w_min, x_max,
         socket_no, A_ref,
         t_max, t_min) = fa.dimTable
        # Mean values (default)
        dk    = (dk_max + dk_min) / 2
        k     = (k_max  + k_min)  / 2
        tt    = _torx_size_str(socket_no)
        t_min = (t_max  + t_min)  / 2
        r_fil = r * 2.0
        recess = self.makeHexalobularRecess(tt, t_min, True)   # ISO 10664 dims
        if getattr(fa, "SecurityPin", False):
            security_pin_solid = _make_security_pin_cylinder(tt, 0.0, _fs_float(k), standard="ISO", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))
    # ── Pitch override (Thread_Pitch / TPI from dashboard) ───────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) else P

    # ── Thread length override (Thread_Length from dashboard) ─────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        b = min(float(raw_tlen), length)

    # ── Effective shank diameter from threading module ────────────────────
    d_eff = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    tr    = d_eff / 2.0

    head_taper_angle = math.radians(5)
    # lay out the fastener profile
    fm = FSFaceMaker()
    fm.AddPoint(0.0, k)
    fm.AddPoint(
        dk / 2
        - k * math.tan(head_taper_angle)
        - r_fil * math.tan((math.pi / 2 - head_taper_angle) / 2),
        k,
    )
    fm.AddArc2(0.0, -r_fil, -90 + math.degrees(head_taper_angle))
    fm.AddPoint(dk / 2, 0.0)
    fm.AddPoint(tr + r, 0.0)
    fm.AddArc2(0.0, -r, 90)
    if length - r > b:  # partially threaded fastener
        thread_length = b
        if not fa.Thread:
            fm.AddPoint(tr, -1 * (length - b))
    else:
        thread_length = length - r
    fm.AddPoint(tr,        -length + d_eff/10)
    fm.AddPoint(d_eff * 4 / 10, -length)    # smooth outward tip chamfer
    fm.AddPoint(0.0, -length)
    screw = self.RevolveZ(fm.GetFace())
    # cut the driving feature, then add modelled threads if needed
    recess.translate(Base.Vector(0.0, 0.0, k))
    screw = screw.cut(recess)
    if security_pin_solid is not None:
        try:
            fused = screw.fuse(security_pin_solid)
            if fused.isValid():
                screw = fused
            else:
                screw = Part.makeCompound([screw, security_pin_solid])
        except Exception as _pin_err:
            FreeCAD.Console.PrintWarning(
                f"[SecurityPin] fuse failed ({_pin_err}), using compound\n")
            screw = Part.makeCompound([screw, security_pin_solid])
    if fa.Thread:
        tl_cut   = thread_length
        offset_z = -(length - thread_length)
        if is_asme:
            screw = _TA.cut_thread(screw, fa, d_eff, tl_cut, offset_z, P)
        else:
            screw = _TM.cut_thread(screw, fa, d_eff, tl_cut, offset_z, P)
    return screw
