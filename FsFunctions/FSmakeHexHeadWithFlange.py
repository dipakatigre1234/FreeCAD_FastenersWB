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


def makeHexHeadWithFlange(self, fa):
    """
    Head + body geometry only.
    Threading is fully delegated to FSThreadingASME.cut_thread()
    or FSThreadingMetric.cut_thread() — zero thread logic here.
    """
    dia     = self.getDia(fa.calc_diam, False)
    SType   = fa.baseType
    length  = fa.calc_len
    is_asme = SType.startswith("ASME")

    # ── 1. Unpack dimTable ────────────────────────────────────────────────
    if SType in ("EN1662", "EN1665"):
        P_tbl, b0, b1, b2, b3, c, dc, dw, e, k, kw, f, r1, s = fa.dimTable

    elif SType == "ASMEB18.2.1.8":
        # CSV columns: b0, P, c, dc, kw, r1, s_max, s_min, e_max, e_min
        b0, P_tbl, c, dc, kw, r1, s_max, s_min, e_max, e_min = fa.dimTable
        s = (s_max + s_min) / 2

    elif SType in ("ISO4162", "ISO15071"):
        P_tbl, b0, b1, b2, b3, c = fa.dimTable[:6]
        dc  = fa.dimTable[8]
        kw  = fa.dimTable[15]
        r1  = fa.dimTable[17]
        s   = fa.dimTable[22]

    elif SType == "ISO15072":
        P_tbl           = fa.dimTable[0]
        b0, b1, b2, b3, c = fa.dimTable[3:8]
        dc  = fa.dimTable[10]
        kw  = fa.dimTable[17]
        r1  = fa.dimTable[19]
        s   = fa.dimTable[24]

    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    # ── 2. Thread-length for shaft profile (unthreaded step) ─────────────
    if SType == "ASMEB18.2.1.8":
        b_tbl = float(b0)
    else:
        b_tbl = float(b1 if length <= 125.0 else (b2 if length <= 200.0 else b3))

    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    b = min(float(raw_tlen), length) if raw_tlen > 0.0 else b_tbl

    # ── 3. Effective shank diameter from threading module (CSV + deviation) ──
    d_eff = _TA.get_shank_dia(fa, dia) if is_asme else _TM.get_shank_dia(fa, dia)
    tr    = d_eff / 2.0

    # ── 4. Head geometry constants ────────────────────────────────────────
    cham     = s * (2.0 / sqrt3 - 1.0) * math.sin(math.radians(25))
    sqrt2_   = 1.0 / sqrt2
    beta     = math.radians(25.0)
    tan_beta = math.tan(beta)
    arc1_x   = dc / 2.0 - c / 2.0 + (c / 2.0) * math.sin(beta)
    arc1_z   = c / 2.0 + (c / 2.0) * math.cos(beta)
    kmean    = arc1_z + (arc1_x - s / sqrt3) * tan_beta + kw * 1.1 + cham

    # ── 5. HEAD: revolve profile + hex prism boolean cut ─────────────────
    fm = FSFaceMaker()
    fm.AddPoint(0.0, kmean * 0.9)
    fm.AddPoint(s / 2.0 * 0.8 - r1 / 2.0,  kmean * 0.9)
    fm.AddArc(
        s / 2.0 * 0.8 - r1 / 2.0 + r1 / 2.0 * sqrt2_,
        kmean * 0.9 + r1 / 2.0 - r1 / 2.0 * sqrt2_,
        s / 2.0 * 0.8,
        kmean * 0.9 + r1 / 2.0,
    )
    fm.AddPoint(s / 2.0 * 0.8, kmean - r1)
    fm.AddArc(
        s / 2.0 * 0.8 + r1 - r1 * sqrt2_,
        kmean - r1 + r1 * sqrt2_,
        s / 2.0 * 0.8 + r1,
        kmean,
    )
    fm.AddPoint(s / 2.0, kmean)
    fm.AddPoint(s / 2 + (kmean - 0.1) * sqrt3, 1.0)
    fm.AddPoint(0.0, 0.1)
    head    = self.RevolveZ(fm.GetFace())
    hextool = self.makeHexPrism(s, kmean)
    head    = head.common(hextool)

    # ── 6. BODY: flange + shaft revolve, fused to head ────────────────────
    fm.Reset()
    fm.AddPoint(0.0,         -length)
    fm.AddPoint(d_eff * 4 / 10, -length)
    fm.AddPoint(tr,              -length + d_eff / 10)   # tip taper

    if length - r1 > b:
        # partially threaded — draw unthreaded step only when Thread is off
        if not fa.Thread:
            fm.AddPoint(tr, -1.0 * (length - b))

    fm.AddPoint(tr, -r1)                            # shaft down to fillet
    fm.AddArc2(r1, 0.0, -90)                        # fillet arc
    fm.AddPoint((dc - c) / 2, 0.0)
    fm.AddArc2(0, c / 2, 180 - math.degrees(beta))
    flange_top_ht = math.tan(beta) * (
        (dc - c) / 2 - s * 0.4 + c / 2 / math.tan(beta / 2)
    )
    fm.AddPoint(s * 0.4, flange_top_ht)
    fm.AddPoint(0.0,     flange_top_ht)

    flange = self.RevolveZ(fm.GetFace())
    shape  = head.fuse(flange)

    # ── 7. THREADING: single call — all logic inside threading module ─────
    if fa.Thread:
        tl_cut   = b
        offset_z = -(length - b)
        if is_asme:
            shape = _TA.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P_tbl)
        else:
            shape = _TM.cut_thread(shape, fa, d_eff, tl_cut, offset_z, P_tbl)

    return shape