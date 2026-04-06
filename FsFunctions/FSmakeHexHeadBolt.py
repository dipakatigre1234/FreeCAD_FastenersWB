# -*- coding: utf-8 -*-
"""
FsMakeHexHeadBolt.py
====================
HEAD geometry    : from fa.dimTable (asmeb18 / ISO / DIN CSV) — never deviated
SHANK + TIP dia  : from threading module get_shank_dia() — deviated d_eff
THREADING        : delegated to FSThreadingASME / FSThreadingMetric
"""
from screw_maker import *

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM


def makeHexHeadBolt(self, fa):
    """Creates a bolt with a hexagonal head.

    Supported types:
    - DIN 933 / DIN 961 / ISO 4014 / 4016 / 4017 / 4018
    - ISO 8676 / 8765 / ASMEB18.2.1.6 / ASMEB18.2.1.7

    HEAD dimensions  : fa.dimTable  (asmeb18 / ISO / DIN CSV) — not deviated
    SHANK + TIP dia  : _TA.get_shank_dia() or _TM.get_shank_dia() → d_eff
    Thread cutter OD : same d_eff — cut_thread() receives d_eff not nominal
    """
    dia     = self.getDia(fa.calc_diam, False)
    length  = fa.calc_len
    is_asme = fa.baseType.startswith("ASME")

    # ── 1. Unpack dimTable ────────────────────────────────────────────────
    if fa.baseType in ("DIN933", "DIN961", "ISO4017", "ISO8676"):
        P_tbl, c, dw, e, k, r, s = fa.dimTable
        b_tbl = length

    elif fa.baseType == "ISO4018":
        P_tbl, _, _, c, _, dw, e, k, _, _, _, r, s, _ = fa.dimTable
        b_tbl = length

    elif fa.baseType == "ISO4014":
        P_tbl, b1, b2, b3, c, dw, e, k, r, s = fa.dimTable
        b_tbl = b1 if length <= 125.0 else (b2 if length <= 200.0 else b3)

    elif fa.baseType == "ISO4016":
        P_tbl, b1, b2, b3, c, _, _, _, dw, e, k, _, _, _, r, s, _ = fa.dimTable
        b_tbl = b1 if length <= 125.0 else (b2 if length <= 200.0 else b3)

    elif fa.baseType == "ISO8765":
        P_tbl, b1, b2, b3, c = fa.dimTable[:5]
        dw = fa.dimTable[11]
        e  = fa.dimTable[13]
        k  = fa.dimTable[15]
        r  = fa.dimTable[22]
        s  = fa.dimTable[23]
        b_tbl = b1 if length <= 125.0 else (b2 if length <= 200.0 else b3)

    elif fa.baseType in ("ASMEB18.2.1.2", "ASMEB18.2.1.3"):
        # CSV columns: b1, b2, P, c, dw, e_max, e_min, k_max, k_min, r, s_max, s_min
        b1_tbl, b2_tbl, P_tbl, c, _dw_unused, e_max, e_min, k_max, k_min, r, s_max, s_min = fa.dimTable
        e = (e_max + e_min) / 2
        k = (k_max + k_min) / 2
        s = (s_max + s_min) / 2
        b_tbl = b2_tbl if length > 6 * 25.4 else b1_tbl
        dw    = None

    elif fa.baseType == "ASMEB18.2.1.6":
        # CSV columns: b, P, c, dw, e_max, e_min, k_max, k_min, r, s_max, s_min
        b_tbl, P_tbl, c, _dw6, e_max, e_min, k_max, k_min, r, s_max, s_min = fa.dimTable
        e = (e_max + e_min) / 2
        k = (k_max + k_min) / 2
        s = (s_max + s_min) / 2
        dw = _dw6
        if length > 6 * 25.4:
            b_tbl += 6.35

    elif fa.baseType == "ASMEB18.2.1.7":
        # CSV columns: b1, b2, P, c, dw, e_max, e_min, k_max, k_min, r, s_max, s_min
        b1_tbl, b2_tbl, P_tbl, c, _dw7, e_max, e_min, k_max, k_min, r, s_max, s_min = fa.dimTable
        e = (e_max + e_min) / 2
        k = (k_max + k_min) / 2
        s = (s_max + s_min) / 2
        dw    = _dw7
        b_tbl = b2_tbl if length > 6 * 25.4 else b1_tbl

    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    # ── 2. Resolve effective pitch P ─────────────────────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) \
        else P_tbl

    # ── 3. Thread length ──────────────────────────────────────────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        b = min(float(raw_tlen), length)
    else:
        b = b_tbl

    # ── 4. d_eff — single call to threading module ────────────────────────
    #
    #  Threading module does:
    #    CSV lookup → raw Thread_Outer_Dia (ASME) or Thread_Mean_Dia (Metric)
    #    _interpolated_deviation_pct(dia) → pct
    #    d_eff = CSV_dia − (CSV_dia × pct / 100)
    #
    #  This is the ONLY place d_eff is computed.
    #  Both shank profile and cut_thread use this same value.
    #  To change deviation: edit the 4 constants at top of the threading module.
    #
    if is_asme:
        d_eff = _TA.get_shank_dia(fa, dia)
    else:
        d_eff = _TM.get_shank_dia(fa, dia)

    tr = d_eff / 2.0

    # ── 5. Console log ────────────────────────────────────────────────────
    try:
        import FreeCAD as _FC
        _tpi_log = round(25.4 / P) if P > 0 else 0
        _custom  = " (custom)" if (raw_pitch and float(raw_pitch) > 0) else ""
        _cls_log = str(getattr(fa, "Thread_Class", "-") or "-") if is_asme \
                   else str(getattr(fa, "Thread_Class_ISO", "-") or "-")
        _pitch_s = str(getattr(fa, "Thread_Pitch", "") or "") if not is_asme else ""
        _FC.Console.PrintMessage(
            "[Thread] Type        : " + str(fa.baseType) + "\n" +
            "[Thread] Nominal D   : " + f"{dia:.4f} mm\n" +
            "[Thread] d_eff       : " + f"{d_eff:.5f} mm  (threading module CSV + deviation)\n" +
            "[Thread] Pitch P     : " + f"{P:.5f} mm" + _custom + "\n" +
            "[Thread] TPI         : " + str(_tpi_log) + _custom + "\n" +
            ("[Thread] Class       : " + _cls_log + "\n" if is_asme else
             "[Thread] MetricPitch : " + _pitch_s + "  Class: " + _cls_log + "\n") +
            "[Thread] Shank r     : " + f"{tr:.5f} mm\n" +
            "[Thread] Thread Len  : " + f"{b:.3f} mm\n" +
            "[Thread] Total Len   : " + f"{length:.3f} mm\n"
        )
    except Exception:
        pass

    # ── 6. Head geometry constants ────────────────────────────────────────
    cham = (e - s) * math.sin(math.radians(15))

    # ── 7. HEAD + BODY revolve profile ────────────────────────────────────
    #
    #  HEAD  (z = 0 → k):  s, k, e, c, dw, r  ← fa.dimTable  (never deviated)
    #  SHANK (z = 0 → -length):  tr, d_eff     ← threading module
    #
    fm = FSFaceMaker()
    fm.AddPoint(0.0,           k)
    fm.AddPoint(s / 2.0,       k)
    fm.AddPoint(s / sqrt3,     k - cham)
    fm.AddPoint(s / sqrt3,     c)
    if dw is not None:
        fm.AddPoint(dw / 2.0,  c)
        fm.AddPoint(dw / 2.0,  0.0)
    fm.AddPoint(tr + r,        0.0)
    fm.AddArc2(0.0, -r, 90)          # fillet: (tr+r, 0) → (tr, -r)

    _b_profile = min(b, length)
    if length - r > _b_profile:
        if not fa.Thread:
            fm.AddPoint(tr, -1 * (length - _b_profile))

    # shank + tip — d_eff only, NOT nominal dia
    fm.AddPoint(tr,              -length + d_eff / 10)
    fm.AddPoint(d_eff * 4 / 10,  -length)
    fm.AddPoint(0.0,             -length)

    shape = self.RevolveZ(fm.GetFace())

    # ── 8. Hex head cut ───────────────────────────────────────────────────
    extrude = self.makeHexPrism(s, k + length + 2)
    extrude.translate(Base.Vector(0.0, 0.0, -length - 1))
    shape = shape.common(extrude)

    # ── 9. Threading — delegated to threading modules ─────────────────────
    if fa.Thread:
        tl_cut   = min(b, max(length - r, 0.0))
        offset_z = -(length - tl_cut)
        # d_eff passed as `dia` — threading modules use get_shank_dia()
        # internally so the cutter OD matches the body exactly
        if is_asme:
            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)
        else:
            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P)

    return shape