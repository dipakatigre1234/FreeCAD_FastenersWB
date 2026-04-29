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
import FastenerBase
import sys as _sys_nut, os as _os_nut
_wb_nut = _os_nut.path.dirname(_os_nut.path.dirname(_os_nut.path.abspath(__file__)))
if _wb_nut not in _sys_nut.path:
    _sys_nut.path.insert(0, _wb_nut)
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None
try:
    import FSThreadingASMEInternal as _TAI
except Exception:
    _TAI = None


def makeHexNut(self, fa):
    """Creates a basic hexagonal nut.
    Supported types:
    - ISO 4032 Hexagon regular nuts (style 1) — Product grades A and B
    - ISO 4033 Hexagon high nuts (style 2) — Product grades A and B
    - ISO 4034 Hexagon regular nuts (style 1) — Product grade C
    - ISO 4035 Hexagon thin nuts chamfered (style 0) — Product grades A and B
    - ISO 7414 Hexagon heavy nuts — metric
    - ASME B18.2.2 Table 3  — Hex Machine Screw Nuts (ASMEB18.2.2.3)
    - ASME B18.2.2 Table 5A — Hex Nuts (ASMEB18.2.2.5A)
    - ASME B18.2.2 Table 5B — Hex Jam Nuts (ASMEB18.2.2.5B)
    - ASME B18.2.2 Table 11 — Heavy Hex Nuts (11A) and Heavy Hex Jam Nuts (11B)
    - DIN 6334 3xD length hexagon nuts
    - ASME B18.2.2 Table 14 — Hex Coupling Nuts (ASMEB18.2.2.14)

    Thread diameter offsets (Dipak):
      Metric (ISO/DIN): thread_dia = dia + 0.05 * P
      ASME (inch):      thread_dia = dia + 0.05 / TPI
      Custom pitch/TPI: overrides table value via fa.calc_pitch / fa.calc_tpi

    dimTable column layout per type:
      ISO7414              : P, c, da, dw, e, m, mw, s_nom
      ASMEB18.2.2.1A       : P, da, e_max, e_min, m_max, m_min, s_max, s_min (mm) → m = mean(m), s = mean(s)
      ASMEB18.2.2.3        : TPI, F_max, F_min, H_max, H_min (inches) → m = H_max*25.4, s = F_max*25.4
      ASMEB18.2.2.5A       : P, da, e_max, e_min, m_a_max, m_a_min, m_b_max, m_b_min, s_max, s_min (mm) → m=mean(m_a)
      ASMEB18.2.2.5B       : same CSV → m = mean(m_b) (jam nut height)
      ASMEB18.2.2.11A      : P, da, s_min, s_max, e_min, e_max, m_a_min, m_a_max, m_b_min, m_b_max → m = mean(m_a)
      ASMEB18.2.2.11B      : same as 11A → m = mean(m_b) (jam nut)
      ASMEB18.2.2.14       : TPI, F_min, F_max, G_min, G_max, H_min, H_max (mm) → Coupling Nut
    """

    SType = fa.baseType

    # ── Convert ASME inch string → mm (fallback when getDia KeyError) ─────────
    def _asme_inch_to_mm(diam_str):
        """Parse '2 1/8in', '1/4in', '1in' etc. → diameter in mm."""
        s = str(diam_str).replace("in", "").strip()
        if " " in s:
            whole, frac = s.split(" ", 1)
            n, d = frac.split("/")
            return (float(whole) + float(n) / float(d)) * 25.4
        elif "/" in s:
            n, d = s.split("/")
            return float(n) / float(d) * 25.4
        else:
            return float(s) * 25.4

    try:
        dia = self.getDia(fa.calc_diam, True)
    except (KeyError, TypeError):
        # Large ASME sizes (e.g. '2 1/8in') may not exist in DiaList
        dia = _asme_inch_to_mm(fa.calc_diam)

    # ── Detect ASME (inch) vs metric ─────────────────────────────────────────
    is_asme = SType.startswith("ASME")

    # ── Unpack dimension table ────────────────────────────────────────────────
    if SType == "ISO7414":
        # CSV columns: P, c, da, dw, e, m, mw, s_nom
        P, _, da, _, e, m, _, s = fa.dimTable
    elif SType[:3] == 'ISO' or SType == "DIN934":
        P, _, da, _, e, m, _, s = fa.dimTable
    elif SType == 'ASMEB18.2.2.1A':
        # CSV columns: P, da, e_max, e_min, m_max, m_min, s_max, s_min (mm)
        P, da, e_max, e_min, m_max, m_min, s_max, s_min = fa.dimTable
        e = (e_max + e_min) / 2
        m = (m_max + m_min) / 2
        s = (s_max + s_min) / 2
    elif SType == 'ASMEB18.2.2.3':
        # CSV columns: TPI, F_max, F_min, H_max, H_min (all in inches)
        TPI, F_max, F_min, H_max, H_min = fa.dimTable
        P = 1.0 / TPI * 25.4
        s = ((F_max + F_min) / 2) * 25.4
        m = ((H_max + H_min) / 2) * 25.4
        e = s * 2 / sqrt3   # no e column in CSV — derive from s
        da = dia
    elif SType == 'ASMEB18.2.2.5A':
        # CSV columns: P, da, e_max, e_min, m_a_max, m_a_min, m_b_max, m_b_min, s_max, s_min (mm)
        # 5A = Hex Nut  → use m_a (regular nut height)
        P, da, e_max, e_min, m_a_max, m_a_min, m_b_max, m_b_min, s_max, s_min = fa.dimTable
        e = (e_max + e_min) / 2
        m = (m_a_max + m_a_min) / 2
        s = (s_max + s_min) / 2
    elif SType == 'ASMEB18.2.2.5B':
        # CSV columns: P, da, e_max, e_min, m_a_max, m_a_min, m_b_max, m_b_min, s_max, s_min (mm)
        # 5B = Hex Jam Nut → use m_b (thin/jam nut height)
        P, da, e_max, e_min, m_a_max, m_a_min, m_b_max, m_b_min, s_max, s_min = fa.dimTable
        e = (e_max + e_min) / 2
        m = (m_b_max + m_b_min) / 2
        s = (s_max + s_min) / 2
    elif SType == 'ASMEB18.2.2.11A':
        # CSV columns: P, da, s_min, s_max, e_min, e_max, m_a_min, m_a_max, m_b_min, m_b_max (mm)
        P, da, s_min, s_max, e_min, e_max, m_a_min, m_a_max, m_b_min, m_b_max = fa.dimTable
        e = (e_max + e_min) / 2
        m = (m_a_max + m_a_min) / 2
        s = (s_max + s_min) / 2
    elif SType == 'ASMEB18.2.2.11B':
        # CSV columns: P, da, s_min, s_max, e_min, e_max, m_a_min, m_a_max, m_b_min, m_b_max (mm)
        P, da, s_min, s_max, e_min, e_max, m_a_min, m_a_max, m_b_min, m_b_max = fa.dimTable
        e = (e_max + e_min) / 2
        m = (m_b_max + m_b_min) / 2
        s = (s_max + s_min) / 2
    elif SType == "DIN6334":
        P, da, m, s = fa.dimTable
        e = s * 2 / sqrt3   # derive e from s for DIN
    elif SType == "ASMEB18.2.2.14":
        # CSV columns: TPI, F_min, F_max, G_min, G_max, H_min, H_max (mm) — Hex Coupling Nut
        # F = width across flats (s),  G = width across corners (e)
        TPI, F_min, F_max, G_min, G_max, H_min, H_max = fa.dimTable
        P = 1.0 / TPI * 25.4
        e = (G_max + G_min) / 2
        m = (H_max + H_min) / 2
        s = (F_max + F_min) / 2
        da = dia

    try:
        da = self.getDia(da, True)
    except (KeyError, TypeError):
        da = float(da)   # da from CSV is already in mm for ASME nut types

    # ── Resolve pitch — metric nut ALWAYS uses Thread_Pitch_Nut from CSV ────────
    #
    # dimTable P is DISCARDED for metric nuts — it is the bolt/standard table
    # pitch and is not relevant to the internal thread the user selected.
    #
    # Source priority for metric nut:
    #   1. Thread_Pitch_Nut  — user picked from metric_internal_thread_dia.csv
    #   2. fa.calc_pitch     — custom pitch override (rare)
    # dimTable P is NOT used as fallback for metric nut pitch.
    #
    # For ASME nuts: keep original P from dimTable + calc_pitch/TPI override.
    #
    if not is_asme and _TMI is not None:
        _p_nut_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
        if _p_nut_s:
            try:
                P = float(_p_nut_s)          # ← Thread_Pitch_Nut from CSV wins
            except Exception:
                pass
        elif fa.calc_pitch is not None and fa.calc_pitch > 0.0:
            P = fa.calc_pitch                # ← custom pitch fallback
        # dimTable P intentionally NOT used here
    else:
        # ASME: keep dimTable P, apply calc_pitch override if set
        if fa.calc_pitch is not None and fa.calc_pitch > 0.0:
            P = fa.calc_pitch
        if is_asme:
            if fa.calc_tpi is not None and fa.calc_tpi > 0:
                eff_tpi = fa.calc_tpi
            else:
                eff_tpi = 25.4 / P

    # ── Thread geometry constants ─────────────────────────────────────────────
    sqrt2_ = 1.0 / sqrt2
    # chamfer at hex corners
    # ASME: use actual e (width across corners) mean from CSV
    # ISO/DIN: use original formula based on s (no e mean applied)
    if is_asme:
        cham = (e - s) * math.sin(math.radians(15))
    else:
        cham = s * (sqrt3 / 3 - 1 / 2) * math.tan(math.radians(22.5))
    H = P * cos30

    # ── Bore radius from CSV D1max + deviation ───────────────────────────────
    # Metric nuts: use D1max from metric_internal_thread_dia.csv
    # ASME nuts:   use Minor_Dia_Max from un_unr_internal_thread_minor_dia.csv
    _bore_r = None
    if not is_asme and _TMI is not None:
        try:
            _dia_s  = str(getattr(fa, "calc_diam", "") or "")
            _p_s    = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
            _cls_s  = str(getattr(fa, "Thread_Class_Nut", "") or "6H")
            if not _p_s:
                # Resolve pitch from fa (calc_pitch or coarsest)
                _p_mm = _TMI.resolve_nut_pitch(fa)
                _p_s  = str(_p_mm) if _p_mm else ""
            if _p_s:
                _bore_eff = _TMI.bore_dia_from_table(fa, _dia_s, _p_s, _cls_s)
                _bore_r   = _bore_eff / 2.0
        except Exception:
            _bore_r = None
    elif is_asme and _TAI is not None:
        # ASME nut — bore from un_unr_internal_thread_minor_dia.csv
        try:
            _dia_s_a   = str(getattr(fa, "calc_diam", "") or "")
            _tpi_s_a   = str(getattr(fa, "Thread_TPI_Nut", "") or "")
            _type_s_a  = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
            _cls_s_a   = str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")
            # Resolve TPI from fa if Thread_TPI_Nut not set
            if not _tpi_s_a:
                _tpi_val_a = _TAI.resolve_nut_tpi(fa)
                _tpi_s_a   = str(_tpi_val_a) if _tpi_val_a else ""
            if _tpi_s_a:
                _bore_eff_a = _TAI.bore_dia_from_table(
                    fa, _dia_s_a, _tpi_s_a, _type_s_a, _cls_s_a)
                _bore_r = _bore_eff_a / 2.0
        except Exception:
            _bore_r = None

    if _bore_r is None:
        # Fallback: original ISO formula for bore (minor diameter)
        _bore_r = dia / 2.0 - H * 5.0 / 8.0

    cham_i_delta = da / 2.0 - _bore_r
    cham_i = cham_i_delta * math.tan(math.radians(15.0))

    # ── Nut body profile (revolved solid) ─────────────────────────────────────
    # Chamfer radial position must match makeHexPrism(s) corner radius = s/sqrt3.
    # e is used only for chamfer HEIGHT: cham = (e-s)*sin(15°) for ASME.
    # Using e/2 here would mismatch the hex prism corner (s/sqrt3 ≠ e/2 for ASME).
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(_bore_r,      m - cham_i)
    fm.AddPoint(da / 2.0,     m)
    fm.AddPoint(s / 2.0,      m)
    fm.AddPoint(s / sqrt3,    m - cham)
    fm.AddPoint(s / sqrt3,    cham)
    fm.AddPoint(s / 2.0,      0.0)
    fm.AddPoint(da / 2.0,     0.0)
    fm.AddPoint(_bore_r,      0.0 + cham_i)
    head = self.RevolveZ(fm.GetFace())

    # ── Hexagon prism cut ─────────────────────────────────────────────────────
    # removeSplitter() merges the coplanar face patches on each flat that result
    # from the boolean common of three distinct outer surface segments
    # (bottom chamfer cone + cylinder + top chamfer cone) with the hex prism.
    # Without it, each flat shows as two or three separate faces with seam lines.
    extrude = self.makeHexPrism(s, m)
    nut = head.common(extrude).removeSplitter()

    # ── Modelled threads (inner thread cutter) ────────────────────────────────
    #
    # Body bore wall is already at D1max (minor dia) from the revolve profile.
    # Thread cutter runs from major dia inward — uses proven CreateInnerThreadCutter.
    #
    # Why NOT use make_internal_thread_cutter from _TMI:
    #   That function places the helix at bore_dia/2 (minor dia) which is the
    #   wrong radius — the helix must run at the major dia side (nominal/2).
    #   CreateInnerThreadCutter already does this correctly.
    #
    # Flow:
    #   bore wall = D1max/2  (set in revolve profile above)  ← from CSV
    #   cutter OD = dia + 0.05×P  (just above major dia)     ← proven
    #   cutter cuts from major inward → creates thread form between D1max and major
    #
    if fa.Thread:
        if is_asme:
            # Resolve eff_tpi: prefer _TAI.resolve_nut_tpi, fall back to dimTable
            _eff_tpi_c = None
            if _TAI is not None:
                try:
                    _eff_tpi_c = _TAI.resolve_nut_tpi(fa)
                except Exception:
                    pass
            if not _eff_tpi_c and 'eff_tpi' in dir():
                _eff_tpi_c = eff_tpi
            if not _eff_tpi_c or _eff_tpi_c <= 0:
                _eff_tpi_c = 25.4 / P if P > 0 else 8.0
            thread_dia = dia + 0.05 / _eff_tpi_c
            thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, m + P)
            nut = nut.cut(thread_cutter)
        else:
            thread_dia    = dia + 0.05 * P
            thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, m + P)
            nut = nut.cut(thread_cutter)

    return nut