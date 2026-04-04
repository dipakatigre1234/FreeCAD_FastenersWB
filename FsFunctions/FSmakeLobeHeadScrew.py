# FSmakeLobeHeadScrew.py  —  ASME B18.2.1.9  External 6-Lobe Flanged Bolt
#
# Bolt geometry CSV  (FsData/asmeb18.2.1.9def.csv):
#   columns: Dia, b, G, H, K, C, B, T, r1   (P removed — computed from TPI)
#
# Thread logic is FULLY delegated to FSThreadingASME.py.
# This file contains ONLY head/shank/flange geometry + the call to apply threads.
#
# ─────────────────────────────────────────────────────────────────────────────
# HOW THREADING IS CALLED
# ─────────────────────────────────────────────────────────────────────────────
#   When fa.Thread is True:
#     1. FSThreadingASME.resolve_thread_params(nominal, fa)
#        → validates type/series/TPI/class, returns pitch_mm and outer_dia_mm
#     2. FSThreadingASME.apply_asme_thread(shape, fa, nominal, dia, tl, -offset)
#        → calls make_UN_thread_cutter, translates, cuts — returns new shape

from screw_maker import *

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM


import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)


import sys as _sys
import os as _os

# FSThreadingASME.py is at the workbench root (one level up from FsFunctions/)
_wb_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _wb_root not in _sys.path:
    _sys.path.insert(0, _wb_root)


_V  = 0.632
_RT = 0.090


# ─────────────────────────────────────────────────────────────────────────────
# 6-lobe prism  (Torx-style drive recess)
# ─────────────────────────────────────────────────────────────────────────────
def _prism(G, h):
    A   = G
    V   = G * _V
    rt  = G * _RT
    rv  = -((V + sqrt3 * (2*rt - A)) * V + (A - 4*rt) * A) \
           / (4*V - 2*sqrt3*A + (4*sqrt3 - 8)*rt)
    b   = math.acos(
              max(-1., min(1., A / (4*rv + 4*rt) - 2*rt / (4*rv + 4*rt)))
          ) - math.pi / 6
    P0  = Base.Vector(A/2 - rt + rt*math.sin(b), -rt*math.cos(b), 0)
    P1  = Base.Vector(A/2, 0, 0)
    P2  = Base.Vector(A/2 - rt + rt*math.sin(b),  rt*math.cos(b), 0)
    Pi  = Base.Vector(sqrt3*V/4, V/4, 0)
    R   = Base.Matrix()
    R.rotateZ(math.radians(60))
    e   = [Part.Arc(P0, P1, P2).toShape()]
    Pi2 = R.multiply(P0)
    e.append(Part.Arc(P2, Pi, Pi2).toShape())
    for i in range(5):
        P1  = R.multiply(P1)
        P2  = R.multiply(P2)
        e.append(Part.Arc(Pi2, P1, P2).toShape())
        Pi  = R.multiply(Pi)
        Pi2 = R.multiply(Pi2)
        e.append(Part.Arc(P2, Pi, P0 if i == 4 else Pi2).toShape())
    return Part.Face(Part.Wire(e)).extrude(Base.Vector(0, 0, h))


# ─────────────────────────────────────────────────────────────────────────────
# Main shape function
# ─────────────────────────────────────────────────────────────────────────────
def makeLobeHeadScrew(self, fa):
    """Generate ASME B18.2.1.9 6-Lobe Flanged Bolt shape.

    Thread cutting is delegated entirely to FSThreadingASME.py.
    This function only builds head + flange + shank geometry.
    """
    # dimTable: b, G, H_max, H_min, K_max, K_min, C_max, C_min, B, T, r1
    b, G, H_max, H_min, K_max, K_min, C_max, C_min, B, T, r1 = fa.dimTable
    H = (H_max + H_min) / 2
    K = (K_max + K_min) / 2
    C = (C_max + C_min) / 2
    dia = self.getDia(fa.calc_diam, False)
    L   = float(fa.calc_len) if fa.calc_len else 50.0

    nominal = _TA.bolt_nominal(fa.calc_diam)

    # ── Resolve thread parameters from FSThreadingASME ────────────────────
    # ── Resolve pitch and d_eff from threading module ─────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P  = float(raw_pitch) if (raw_pitch and float(raw_pitch) > 0) else (25.4 / round(25.4 / (dia * 0.08)))
    d_eff = _TA.get_shank_dia(fa, dia)
    tr    = d_eff / 2.0

    # ── Console log ───────────────────────────────────────────────────────
    try:
        import FreeCAD as _FC
        _FC.Console.PrintMessage(
            "\n[ASMEB18.2.1.9]\n"
            "  Diameter    : " + str(fa.calc_diam)                       + "\n"
            "  Nominal     : " + str(nominal)                            + "\n"
            "  Thread2Type : " + str(tp["thread_type"])                  + "\n"
            "  Series      : " + str(tp["lookup_series"])                + "\n"
            "  TPI source  : " + ("Custom" if tp["is_custom_tpi"]
                                   else "Table")                          + "\n"
            "  TPI         : " + str(tp["tpi"])                          + "\n"
            "  Pitch (mm)  : " + str(round(P, 4))                        + "\n"
            "  Class       : " + str(tp["thread_cls"])                   + "\n"
            "  OD (in)     : " + str(round(td/25.4, 5))                  + "\n"
            "  OD (mm)     : " + str(round(td, 4))                       + "\n"
            "  UNR root    : " + str(is_unr)                             + "\n"
        )
    except Exception:
        pass

    # ── Thread length override ────────────────────────────────────────────
    tl_ov = getattr(fa, "calc_thread_length", None) or 0
    if tl_ov > 0:
        b = min(float(tl_ov), L)

    # ── Geometry constants ────────────────────────────────────────────────
    c  = max(K, .3)
    r  = max(r1, .1)
    lh = H - K
    vr = G * _V / 2.0
    rf = max(G * .04, .1)

    # ── Head (6-lobe intersection) ────────────────────────────────────────
    f = FSFaceMaker()
    f.AddPoint(0, c+lh)
    f.AddPoint(G/2-rf, c+lh)
    f.AddArc2(0, -rf, -90)
    f.AddPoint(G/2, c)
    f.AddPoint(0, c)
    p = _prism(G, lh)
    p.translate(Base.Vector(0, 0, c))
    head = self.RevolveZ(f.GetFace()).common(p)

    # ── Flange underside slope ────────────────────────────────────────────
    f2 = FSFaceMaker()
    f2.AddPoint(0, c+T)
    f2.AddPoint(vr, c+T)
    f2.AddPoint(G/2, c)
    f2.AddPoint(0, c)
    slope = self.RevolveZ(f2.GetFace())

    # ── Shank / flange transition / lead-in ───────────────────────────────
    f.Reset()
    f.AddPoint(0, c)
    f.AddPoint(C/2-c/4, c)
    f.AddArc2(0, -c/4, -90)
    f.AddPoint(C/2, 0)
    # Arc from (tr+r, 0): 90° sweep lands exactly at (tr, -r).
    f.AddPoint(tr + r, 0)
    f.AddArc2(0, -r, 90)
    tl = b if (L - r) > b else (L - r)
    if (L - r) > b and not fa.Thread:
        f.AddPoint(tr, -(L - b))
    f.AddPoint(tr, -L + d_eff/10.0)
    f.AddPoint(d_eff * .4, -L)
    f.AddPoint(0, -L)
    shape = self.RevolveZ(f.GetFace()).fuse(slope).fuse(head)

    # ── Thread cut — fully delegated to FSThreadingASME ──────────────────
    if fa.Thread:
        shape = _TA.cut_thread(shape, fa, d_eff, tl, -(L - tl), P)

    return shape