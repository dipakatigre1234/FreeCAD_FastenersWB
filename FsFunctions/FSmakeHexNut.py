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


def makeHexNut(self, fa):
    """Creates a basic hexagonal nut.
    Supported types:
    - ISO 4032 Hexagon regular nuts (style 1) — Product grades A and B
    - ISO 4033 Hexagon high nuts (style 2) — Product grades A and B
    - ISO 4034 Hexagon regular nuts (style 1) — Product grade C
    - ISO 4035 Hexagon thin nuts chamfered (style 0) — Product grades A and B
    - ASME B18.2.2 machine screw, thin, and regular hexagon nuts
    - DIN 6334 3xD length hexagon nuts
    - ASME B18.2.2 coupling nuts

    Thread diameter offsets (Dipak):
      Metric (ISO/DIN): thread_dia = dia + 0.05 * P
      ASME (inch):      thread_dia = dia + 0.05 / TPI
      Custom pitch/TPI: overrides table value via fa.calc_pitch / fa.calc_tpi
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
    if SType[:3] == 'ISO' or SType == "DIN934":
        P, _, da, _, _, m, _, s = fa.dimTable
    elif SType == 'ASMEB18.2.2.1A':
        P, da, _, m, s = fa.dimTable
    elif SType == 'ASMEB18.2.2.4A':
        P, da, _, m_a, m_b, s = fa.dimTable
        m = m_a
    elif SType == 'ASMEB18.2.2.4B':
        P, da, _, m_a, m_b, s = fa.dimTable
        m = m_b
    elif SType == "DIN6334":
        P, da, m, s = fa.dimTable
    elif SType == "ASMEB18.2.2.13":
        TPI, F, H = fa.dimTable
        P = 1.0 / TPI * 25.4
        m = H * 25.4
        s = F * 25.4
        da = dia

    try:
        da = self.getDia(da, True)
    except (KeyError, TypeError):
        da = float(da)   # da from CSV is already in mm for ASME nut types

    # ── Apply custom pitch / TPI overrides from FastenersCmd ─────────────────
    # fa.calc_pitch is set by FSScrewObject.execute() when the user overrides:
    #   - metric: ThreadPitch (mm) > 0  → fa.calc_pitch = that value
    #   - ASME  : ThreadTPI   (int) > 0 → fa.calc_pitch = 25.4/TPI,
    #                                      fa.calc_tpi   = TPI
    # For 'Custom' diameter rod types, calc_pitch may also carry a custom pitch.
    if fa.calc_pitch is not None and fa.calc_pitch > 0.0:
        P = fa.calc_pitch          # override table pitch (mm) for all types

    # Derive TPI from current P for ASME clearance calculation.
    # fa.calc_tpi is set only when the user has entered a TPI override;
    # otherwise we derive it from the (possibly overridden) pitch.
    if is_asme:
        if fa.calc_tpi is not None and fa.calc_tpi > 0:
            eff_tpi = fa.calc_tpi
        else:
            eff_tpi = 25.4 / P      # derive TPI from table / custom pitch

    # ── Thread geometry constants ─────────────────────────────────────────────
    sqrt2_ = 1.0 / sqrt2
    # chamfer at nut top
    cham = s * (sqrt3 / 3 - 1 / 2) * math.tan(math.radians(22.5))
    H = P * cos30
    cham_i_delta = da / 2.0 - (dia / 2.0 - H * 5.0 / 8.0)
    cham_i = cham_i_delta * math.tan(math.radians(15.0))

    # ── Nut body profile (revolved solid) ─────────────────────────────────────
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(dia / 2.0 - H * 5.0 / 8.0, m - cham_i)
    fm.AddPoint(da / 2.0, m)
    fm.AddPoint(s / 2.0, m)
    fm.AddPoint(s / sqrt3, m - cham)
    fm.AddPoint(s / sqrt3, cham)
    fm.AddPoint(s / 2.0, 0.0)
    fm.AddPoint(da / 2.0, 0.0)
    fm.AddPoint(dia / 2.0 - H * 5.0 / 8.0, 0.0 + cham_i)
    head = self.RevolveZ(fm.GetFace())

    # ── Hexagon prism cut ─────────────────────────────────────────────────────
    extrude = self.makeHexPrism(s, m)
    nut = head.common(extrude)

    # ── Modelled threads (inner thread cutter) ────────────────────────────────
    if fa.Thread:
        # Apply thread diameter clearance offset:
        #   Metric (ISO/DIN/any non-ASME): thread_dia = dia + 0.05 * P
        #   ASME (inch):                   thread_dia = dia + 0.05 / TPI
        if is_asme:
            thread_dia = dia + 0.05 / eff_tpi
        else:
            thread_dia = dia + 0.05 * P

        thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, m + P)
        nut = nut.cut(thread_cutter)

    return nut