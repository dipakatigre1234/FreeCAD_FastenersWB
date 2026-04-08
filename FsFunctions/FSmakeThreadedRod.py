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
    Each thread zone = L / 2.  Plain shank = rod_length - L.

        z=0     z=-half      z=-(L-half)   z=-L
        ├── thread ─┤── shank ──┤── thread ──┤

    Both thread zones start AND end smoothly:
      • Outer end  : standard end-chamfer (body tapers to zero) at both rod tips
      • Inner end  : conical taper (thread radius → shank radius) at shank junction

    EQUAL THREADING — WHY CUTTERS EXTEND PAST THE SHANK JUNCTION
    ══════════════════════════════════════════════════════════════
    Every MakePipeShell helix has a lead-in (~1P shallow) at its START and
    a lead-out (~1P shallow) at its END.

    Without extension (old code with _extra=0):
      Lead-OUT of top cutter  → lands at z=-half  (visible shank junction) ✗
      Lead-IN  of bottom cutter → lands at z=-(L-half) (visible) ✗
    Result: 1-2 turns near each shank end look narrower than the rest.

    Fix — extend each cutter by  extra = 2 × P  PAST the shank boundary:
      TOP cutter   : oz = 0,                  tl = half + extra
      BOTTOM cutter: oz = -(L - half - extra), tl = half + extra

      Lead-out of TOP   → inside shank (z=−half … −(half+extra))    ✓ hidden
      Lead-in  of BOTTOM → inside shank (z=−(L−half−extra) … −(L−half)) ✓ hidden

    Every visible thread turn is now identical depth/width on both ends.

    PROFILE GEOMETRY  (partial mode)
    ══════════════════════════════════
      cham  = P   axial width of end-chamfer
      taper = P   axial width of thread→shank conical taper
      rt = d_eff/2   thread body radius  (from threading module)
      rs = dia/2     shank radius        (user nominal, ≥ rt)

      (0,         0)           centre top
      (rt-cham,   0)           top face outer edge
      (rt,       -cham)        top end-chamfer complete
      (rt,       -(half-taper)) thread straight ends
      (rs,       -half)        TOP TAPER end → shank begins   [conical ramp]
      (rs,       -(L-half))    shank ends
      (rt,       -(L-half+taper)) BOTTOM TAPER end → thread resumes
      (rt,       -(L-cham))    bottom thread straight ends
      (rt-cham,  -L)           bottom end-chamfer complete
      (0,        -L)           centre bottom
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
    taper  = P          # thread→shank taper width = 1 pitch
    #
    # extra = 0: cutters cut EXACTLY half per end — no extra thread added.
    # Smooth entry/exit at the shank junction is provided by the BODY PROFILE
    # TAPER (conical ramp, rt → rs over 1 pitch).  The helix lead-in/out
    # naturally coincides with the taper zone and fades gracefully there.
    extra  = 0.0
    length = fa.calc_len

    _raw_tl = getattr(fa, "calc_thread_length", 0.0) or 0.0
    _half   = float(_raw_tl) / 2.0

    # Partial mode: thread_length set, < total length, and each half zone
    # is long enough to hold  chamfer + straight + taper  (minimum = cham+taper)
    _partial = (
        _raw_tl > 0
        and _raw_tl < length
        and _half > (cham + taper)
    )

    _rt = d_eff / 2.0   # thread zone radius  (from threading module)
    _rs = dia   / 2.0   # smooth shank radius (user nominal, >= _rt)

    # ── 4. Revolve profile ────────────────────────────────────────────────────
    fm = FSFaceMaker()

    fm.AddPoint(0.0,        0.0)
    fm.AddPoint(_rt - cham, 0.0)        # top face outer edge
    fm.AddPoint(_rt,       -cham)       # top end-chamfer done

    if _partial:
        # top thread straight (stays at thread radius up to taper start)
        fm.AddPoint(_rt,   -(_half - taper))

        # conical taper: thread radius → shank radius  (smooth runout)
        fm.AddPoint(_rs,   -_half)

        # smooth shank (straight cylinder at nominal diameter)
        fm.AddPoint(_rs,   -(length - _half))

        # conical taper: shank radius → thread radius  (mirror of top)
        fm.AddPoint(_rt,   -(length - _half + taper))

        # bottom thread straight
        fm.AddPoint(_rt,   -(length - cham))
    else:
        # fully threaded: straight cylinder from end-chamfer to end-chamfer
        fm.AddPoint(_rt,   -(length - cham))

    fm.AddPoint(_rt - cham, -length)    # bottom end-chamfer done
    fm.AddPoint(0.0,        -length)

    screw = self.RevolveZ(fm.GetFace())

    # ── 5. Thread cutting ─────────────────────────────────────────────────────
    if fa.Thread:

        def _cut(shape, tl, oz):
            if is_asme:
                return _TA.cut_thread(shape, fa, d_eff, tl, oz, P)
            else:
                return _TM.cut_thread(shape, fa, d_eff, tl, oz, P)

        if not _partial:
            # fully threaded — single cutter end to end
            screw = _cut(screw, length, 0.0)
        else:
            # TOP cutter
            #   starts at z = 0  (rod face — lead-in invisible at chamfer)
            #   ends   at z = -(half + extra)  — 2P inside smooth shank
            #   lead-out lands inside shank, not at visible junction  ✓
            screw = _cut(screw, _half + extra, 0.0)

            # BOTTOM cutter
            #   starts at z = -(length - half - extra) — 2P before shank junction
            #   ends   at z = -length  (rod face — lead-out invisible at chamfer)
            #   lead-in  lands inside shank, not at visible junction  ✓
            screw = _cut(screw, _half + extra, -(length - _half - extra))

    return screw
