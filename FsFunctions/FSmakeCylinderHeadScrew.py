# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2013, 2014, 2015                                        *
*   Original code by:                                                     *
*   Ulrich Brammer <ulrich1a[at]users.sourceforge.net>                    *
***************************************************************************
"""
from screw_maker import *

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM

# ── Security pin table ────────────────────────────────────────────────────────
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


def _make_security_pin_cylinder_head(tt, k_val):
    """Security pin for CYLINDER HEAD screws (ISO14579).

    Cylinder head coordinate system:
      Z = +k  →  head TOP surface  (recess opening after translate)
      Z =  0  →  head BOTTOM / bearing face

    The pin must span from Z = 0 (bearing face, rooted in solid)
    up to Z = +k (head top, flush with recess opening).

    This is the SAME logic as the working countersunk _make_security_pin()
    but shifted +k upward to match the cylinder head coordinate system.

    The countersunk version worked because its head top = Z=0 and
    pin went from Z=-k to Z=0.
    Here head top = Z=+k so pin goes from Z=0 to Z=+k.
    """
    torx_key = _torx_size_str(tt)
    pin_dia  = _TORX_PIN_DIA_MM.get(torx_key, None)

    if pin_dia is None:
        pin_r = min(k_val * 0.25, 2.0)
        FreeCAD.Console.PrintMessage(
            f"[SecurityPin] Unknown Torx '{torx_key}', fallback pin_r={pin_r:.3f}mm\n")
    else:
        pin_r = pin_dia / 2.0

    pin_h     = k_val                   # full head height
    chamfer_h = _TORX_CHAMFER_H
    chamfer_r = chamfer_h               # 45° bevel
    body_h    = pin_h - chamfer_h

    FreeCAD.Console.PrintMessage(
        f"[SecurityPin] drive={torx_key}, pin_dia={pin_r*2:.3f}mm, "
        f"k={k_val:.3f}mm\n")

    # Cylinder body: base at Z=0 (bearing face), top at Z=(k - chamfer_h)
    body = Part.makeCylinder(
               pin_r, body_h,
               FreeCAD.Vector(0.0, 0.0, 0.0),
               FreeCAD.Vector(0.0, 0.0, 1.0))

    # Chamfer cone: base at Z=(k - chamfer_h), tip at Z=k (head top)
    cone = Part.makeCone(
               pin_r, pin_r - chamfer_r, chamfer_h,
               FreeCAD.Vector(0.0, 0.0, k_val - chamfer_h),
               FreeCAD.Vector(0.0, 0.0, 1.0))

    try:
        return body.fuse(cone)
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"[SecurityPin] cone fuse failed: {e}\n")
        return body


def makeCylinderHeadScrew(self, fa):
    """Create a cylinder head fastener (cap screw).

    Supported types:
    - ISO 4762      hexagon socket head cap screw
    - ISO 14579     hexalobular socket head cap screw  ← SecurityPin supported
    - DIN 7984      hexagon socket low head
    - DIN 6912      hexagon socket low head with centre
    - ASMEB18.3.1A  UNC hexagon socket head cap screw
    - ASMEB18.3.1G  UNC hexagon socket low head cap screw
    """
    SType   = fa.baseType
    length  = fa.calc_len
    dia     = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")

    security_pin_solid = None
    tt = None

    # ── 1. Unpack dimTable ────────────────────────────────────────────────
    if SType == 'ISO4762':
        (P_tbl, b_tbl,
         dk_max, dk_min,
         da, ds_max, ds_min,
         e, lf,
         k_max, k_min,
         r,
         s_max, s_min,
         t, v, dw, w) = fa.dimTable
        dk     = (dk_max + dk_min) / 2
        k      = (k_max  + k_min)  / 2
        s_mean = (s_max  + s_min)  / 2
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == 'ISO14579':
        (P_tbl, b_tbl,
         dk_max_c, dk_max_d, dk_min,
         da_max, ds_max, ds_min,
         f_max,
         k_max, k_min,
         r_min, v_max, dw_min, w_min,
         socket_no, A_ref,
         t_max, t_min) = fa.dimTable
        dk     = (dk_max_c + dk_min) / 2
        da     = da_max
        ds     = (ds_max + ds_min) / 2
        k      = (k_max  + k_min)  / 2
        r      = r_min
        v      = v_max
        dw     = dw_min
        w      = w_min
        s_mean = A_ref
        t      = (t_max + t_min) / 2
        tt     = _torx_size_str(int(socket_no))
        recess = self.makeHexalobularRecess(tt, t, True)

        # ── Security pin ──────────────────────────────────────────────────
        # Build pin in cylinder-head world coordinates.
        # After shape is revolved and recess is cut, fuse the pin in.
        # Exactly mirrors the working countersunk approach — same function
        # logic, same fuse strategy, just coordinates shifted +k upward.
        if getattr(fa, 'SecurityPin', True):
            security_pin_solid = _make_security_pin_cylinder_head(tt, _fs_float(k))

    elif SType == 'DIN7984':
        (P_tbl, b_tbl,
         dk_max, dk_min,
         da, ds_min,
         e,
         k_max, k_min,
         r,
         s_max, s_min,
         t_max, t_min,
         v, dw) = fa.dimTable
        dk     = (dk_max + dk_min) / 2
        k      = (k_max  + k_min)  / 2
        s_mean = (s_max  + s_min)  / 2
        t      = (t_max  + t_min)  / 2
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == 'DIN6912':
        (P_tbl, b_tbl,
         dk_max, dk_min,
         da, ds_min,
         e,
         k_max, k_min,
         r,
         s_max, s_min,
         t1_max, t1_min,
         t2_max, t2_min,
         v, dw) = fa.dimTable
        dk     = (dk_max + dk_min) / 2
        k      = (k_max  + k_min)  / 2
        s_mean = (s_max  + s_min)  / 2
        t      = (t1_max + t1_min) / 2
        t2     = (t2_max + t2_min) / 2
        recess = self.makeHexRecess(s_mean, t, True)
        d_cent     = s_mean / 3.0
        depth_cent = d_cent * math.tan(math.pi / 6.0)
        fm = FSFaceMaker()
        fm.AddPoint(0.0,    0.0)
        fm.AddPoint(d_cent, 0.0)
        fm.AddPoint(d_cent, -t2)
        fm.AddPoint(0.0,    -t2 - depth_cent)
        recess = recess.fuse(self.RevolveZ(fm.GetFace()))

    elif SType == 'ASMEB18.3.1A':
        (P_tbl, b_tbl,
         dk_max, dk_min,
         k_max, k_min,
         r, s_mean, t, v, dw) = fa.dimTable
        dk = (dk_max + dk_min) / 2
        k  = (k_max  + k_min)  / 2
        recess = self.makeHexRecess(s_mean, t, True)

    elif SType == 'ASMEB18.3.1G':
        (P_tbl, b_tbl,
         dk_max, dk_min,
         k_max, k_min,
         C_max, J, T, K, r) = (x * 25.4 for x in fa.dimTable)
        dk     = (dk_max + dk_min) / 2
        k      = (k_max  + k_min)  / 2
        v      = C_max
        s_mean = J
        t      = T
        dw     = dk - K
        recess = self.makeHexRecess(s_mean, t, True)

    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── 2. Pitch / thread length / shank ─────────────────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) else P_tbl

    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 \
        else min(b_tbl, max(length - r, 0.0))

    d_eff = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    tr    = d_eff / 2.0

    # ── 3. Revolve profile ────────────────────────────────────────────────
    fm = FSFaceMaker()
    fm.AddPoint(0.0,            k)
    fm.AddPoint(dk / 2 - v,     k)
    fm.AddArc2(0.0, -v, -90)
    fm.AddPoint(dk / 2,         (dk - dw) / 2)
    fm.AddPoint(dw / 2,         0.0)
    fm.AddPoint(tr + r,         0.0)
    fm.AddArc2(0.0, -r, 90)

    if length - r > b:
        if not fa.Thread:
            fm.AddPoint(tr, -1 * (length - b))

    fm.AddPoint(tr,             -length + d_eff / 10)
    fm.AddPoint(d_eff * 4 / 10, -length)
    fm.AddPoint(0.0,            -length)

    shape = self.RevolveZ(fm.GetFace())

    # ── 4. Cut recess then fuse security pin ──────────────────────────────
    # makeHexalobularRecess(tt, t, True) builds recess in local coords:
    #   Z = 0   → opening top
    #   Z = -t  → floor
    # translate(0,0,k) moves it to world:
    #   Z = +k        → opening = head top surface
    #   Z = (k - t)   → floor
    recess.translate(Base.Vector(0.0, 0.0, k))
    shape = shape.cut(recess)

    # Fuse pin — SAME strategy as working countersunk version.
    # Pin spans Z=0 (bearing face = solid) to Z=+k (head top).
    # The head body between Z=0..k is solid EXCEPT for the recess cavity.
    # Fusing a cylinder that fits inside the cavity produces the standing pin.
    if security_pin_solid is not None:
        shape = shape.fuse(security_pin_solid)
        FreeCAD.Console.PrintMessage("[SecurityPin] fuse applied\n")

    # ── 5. Thread cutter ──────────────────────────────────────────────────
    if fa.Thread:
        tl_cut   = b
        offset_z = -(length - b)
        if is_asme:
            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)
        else:
            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

    return shape