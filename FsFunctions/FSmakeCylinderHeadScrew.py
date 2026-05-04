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

# -- Security pin helpers (Cylinder Head) ------------------------------------

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
    torx_key = _torx_size_str(tt)
    A, B, Re = _get_torx_ABRe(torx_key, standard)
    if B is not None and Re is not None:
        return max((B / 2.0 - Re) * 0.75, 0.05)
    return 0.3


def _make_security_pin_cylinder_head(tt, k_val, standard="ISO", pin_dia_mm=0.0):
    """Proportional security pin for CYLINDER HEAD screws.

    Z=0 -> bearing face (pin base), Z=+k -> head top (pin tip).
    pin_dia_mm=0 uses standard diameter = (B/2 - Re)*0.75*2.
    """
    torx_key = _torx_size_str(tt)

    if float(pin_dia_mm) > 0.0:
        pin_r = float(pin_dia_mm) / 2.0
    else:
        pin_r = _standard_pin_r(torx_key, standard)

    chamfer_h   = min(pin_r * 0.10, 0.25)
    chamfer_tip = pin_r - chamfer_h
    body_h      = max(k_val - chamfer_h, 0.01)

    body = Part.makeCylinder(pin_r, body_h,
        FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Vector(0.0, 0.0, 1.0))
    cone = Part.makeCone(pin_r, chamfer_tip, chamfer_h,
        FreeCAD.Vector(0.0, 0.0, k_val - chamfer_h), FreeCAD.Vector(0.0, 0.0, 1.0))

    # Prefer fused solid; fall back to compound to avoid coplanar-face (blue circle) bug
    try:
        result = body.fuse(cone)
        return result if result.isValid() else Part.makeCompound([body, cone])
    except Exception:
        return Part.makeCompound([body, cone])


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
        tt     = _torx_size_str(socket_no)
        recess = self.makeHexalobularRecess(tt, t, True)   # ISO 10664 dims

        # ── Security pin ──────────────────────────────────────────────────
        # Build pin in cylinder-head world coordinates.
        # After shape is revolved and recess is cut, fuse the pin in.
        # Exactly mirrors the working countersunk approach — same function
        # logic, same fuse strategy, just coordinates shifted +k upward.
        if getattr(fa, 'SecurityPin', False):
            security_pin_solid = _make_security_pin_cylinder_head(tt, _fs_float(k), standard="ISO", pin_dia_mm=getattr(fa, "SecurityPinDiameter", 0.0))

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