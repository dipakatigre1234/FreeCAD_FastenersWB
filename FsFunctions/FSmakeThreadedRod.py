# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2013, 2014, 2015                                        *
*   Original code by:                                                     *
*   Ulrich Brammer <ulrich1a[at]users.sourceforge.net>                    *
*                                                                         *
*   This file is a supplement to the FreeCAD CAx development system.     *
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU Lesser General Public License (LGPL)   *
*   as published by the Free Software Foundation; either version 2 of    *
*   the License, or (at your option) any later version.                  *
*   for detail see the LICENCE text file.                                *
*                                                                         *
*   This software is distributed in the hope that it will be useful,     *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the        *
*   GNU Library General Public License for more details.                 *
*                                                                         *
*   You should have received a copy of the GNU Library General Public    *
*   License along with this macro; if not, write to the Free Software    *
*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307 *
*   USA                                                                  *
*                                                                         *
***************************************************************************
"""
from screw_maker import *

import sys as _sys_r, os as _os_r
_wb_r = _os_r.path.dirname(_os_r.path.dirname(_os_r.path.abspath(__file__)))
if _wb_r not in _sys_r.path:
    _sys_r.path.insert(0, _wb_r)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM


def makeThreadedRod(self, fa):
    """Make a threaded rod: full thread OR partial thread with smooth centre shank.

    PARTIAL THREAD ROD  (Thread_Length = L  <  rod length)
    ═══════════════════════════════════════════════════════
    The rod has THREE sections — thread zone / plain shank / thread zone.
    Each thread zone = Thread_Length / 2.  Plain shank = rod_length - Thread_Length.

        z=0   z=−half  z=−(half+taper)     z=−(L−half−taper)  z=−(L−half)   z=−L
        ├─thread─┤─taper─┤──────── shank ────────┤───taper───┤──thread──┤

    SMOOTH SHANK TRANSITION
    ════════════════════════
      rt = d_eff / 2   thread zone body radius  (= cutter OD, from threading module)
      rs = dia   / 2   shank body radius        (user nominal, ≥ rt)

    Body profile:
      • Thread zones : flat cylinder at rt
      • Taper zones  : conical ramp from rt → rs (top) / rs → rt (bottom)
                       placed OUTSIDE the main thread zones
      • Shank        : flat cylinder at rs

    Smooth entry/exit at shank junctions:
      Each cutter is extended by one pitch (taper) INTO the taper zone:
        TOP cutter    : z = 0             →  z = −(half + taper)
        BOTTOM cutter : z = −(L−half−taper) →  z = −L

      In the taper zone the body OD increases from rt toward rs.
      Since the cutter OD = rt, it cuts LESS deeply where body > rt:
        • At taper start (body = rt) : full-depth groove  ← matches thread zone
        • At taper end   (body = rs) : near-zero groove   ← thread fades into shank
      Result: smooth visual fade at both shank junctions, no flip needed.
    """

    ThreadType = fa.calc_diam
    is_asme    = fa.baseType == 'ThreadedRodInch'

    # ── 1. Nominal diameter and table pitch ───────────────────────────────────
    if fa.Diameter != 'Custom':
        dia = self.getDia(ThreadType, False)
        if fa.baseType == 'ThreadedRod':
            P, tunIn, tunEx = fa.dimTable
        elif fa.baseType == 'ThreadedRodInch':
            P = fa.dimTable[0]
    else:
        P = fa.calc_pitch if fa.calc_pitch else 1.0
        if self.sm3DPrintMode:
            dia = self.smScrewThrScaleA * float(fa.calc_diam) + self.smScrewThrScaleB
        else:
            dia = float(fa.calc_diam)

    # ── 2. Effective diameter and pitch override ──────────────────────────────
    if is_asme:
        d_eff = _TA.get_shank_dia(fa, dia)
        if fa.calc_pitch is not None and fa.calc_pitch > 0:
            P = fa.calc_pitch
    else:
        d_eff = _TM.get_shank_dia(fa, dia)
        if fa.calc_pitch is not None and fa.calc_pitch > 0:
            P = fa.calc_pitch

    # ── 3. Geometry constants ─────────────────────────────────────────────────
    cham   = P          # end-chamfer axial width  = 1 pitch
    taper  = P          # thread→shank taper width = 1 pitch (placed outside thread zone)
    length = fa.calc_len

    _raw_tl = getattr(fa, "calc_thread_length", 0.0) or 0.0
    _half   = float(_raw_tl) / 2.0

    # Partial mode requires:
    #   • thread_length set and < total rod length
    #   • each thread half-zone long enough for chamfer + some straight thread
    #   • shank long enough for both tapers
    _partial = (
        _raw_tl > 0
        and _raw_tl < length
        and _half > cham
        and (length - _raw_tl) > 2 * taper
    )

    _rt = d_eff / 2.0   # thread zone radius  (= cutter OD from threading module)
    _rs = dia   / 2.0   # smooth shank radius (user nominal, >= _rt)

    # ── 4. Revolve profile ────────────────────────────────────────────────────
    fm = FSFaceMaker()

    fm.AddPoint(0.0,        0.0)
    fm.AddPoint(_rt - cham, 0.0)          # top face outer edge
    fm.AddPoint(_rt,       -cham)         # top end-chamfer done

    if _partial:
        # TOP thread zone: body flat at _rt (cutter OD matches body → full-depth thread)
        fm.AddPoint(_rt,   -_half)

        # TOP taper: body expands rt→rs OUTSIDE the thread zone
        fm.AddPoint(_rs,   -(_half + taper))

        # smooth shank at nominal diameter
        fm.AddPoint(_rs,   -(length - _half - taper))

        # BOTTOM taper: body contracts rs→rt OUTSIDE the thread zone (mirror of top)
        fm.AddPoint(_rt,   -(length - _half))

        # BOTTOM thread zone: body flat at _rt
        fm.AddPoint(_rt,   -(length - cham))

    else:
        # fully threaded: flat cylinder from end-chamfer to end-chamfer
        fm.AddPoint(_rt,   -(length - cham))

    fm.AddPoint(_rt - cham, -length)      # bottom end-chamfer done
    fm.AddPoint(0.0,        -length)

    screw = self.RevolveZ(fm.GetFace())

    # ── 5. Thread cutting ─────────────────────────────────────────────────────
    if fa.Thread:

        def _cut(shape, tl, oz):
            if is_asme:
                return _TA.cut_thread(shape, fa, dia, tl, oz, P)
            else:
                return _TM.cut_thread(shape, fa, dia, tl, oz, P)

        if not _partial:
            # fully threaded — single cutter, end to end
            screw = _cut(screw, length, 0.0)

        else:
            # ── TOP cutter ────────────────────────────────────────────────────
            # Covers thread zone + top taper zone:
            #   z = 0  →  z = −(half + taper)
            # At z=0:              body = rt, full-depth thread starts ✓
            # At z=−half:          body = rt, still full-depth ✓
            # At z=−(half+taper):  body = rs > rt → cutter cuts ~zero depth ✓
            #                      → thread fades smoothly into shank surface ✓
            screw = _cut(screw, _half + taper, 0.0)

            # ── BOTTOM cutter ─────────────────────────────────────────────────
            # Covers bottom taper zone + thread zone:
            #   z = −(L−half−taper)  →  z = −L
            # At z=−(L−half−taper):  body = rs > rt → cutter cuts ~zero depth ✓
            #                         → thread fades smoothly up from shank ✓
            # At z=−(L−half):        body = rt, full-depth thread ✓
            # At z=−L:               rod face, end-chamfer hides the exit ✓
            screw = _cut(screw, _half + taper, -(length - _half - taper))

    return screw
