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

import sys as _sys_r, os as _os_r
_wb_r = _os_r.path.dirname(_os_r.path.dirname(_os_r.path.abspath(__file__)))
if _wb_r not in _sys_r.path:
    _sys_r.path.insert(0, _wb_r)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM


def makeThreadedRod(self, fa):
    """make a length of standard threaded rod.

    Supported types:
    - ThreadedRod      : Metric threaded rod (ISO/DIN)
    - ThreadedRodInch  : ASME UNC/UNF inch threaded rod

    Threading parameters:
    - ASME  : Thread_Type (UNC/UNF), Thread_TPI, Thread_Class via FSThreadingASME
    - Metric: Thread_Pitch, Thread_Class_ISO, Thread_Root via FSThreadingMetric

    d_eff (effective diameter for body + thread cutter) from threading module
    get_shank_dia() — same approach as hex head bolts.
    """
    ThreadType = fa.calc_diam
    is_asme    = fa.baseType == 'ThreadedRodInch'

    # ── 1. Base nominal diameter and table pitch ──────────────────────────────
    if fa.Diameter != 'Custom':
        dia = self.getDia(ThreadType, False)
        if fa.baseType == 'ThreadedRod':
            P, tunIn, tunEx = fa.dimTable
        elif fa.baseType == 'ThreadedRodInch':
            P = fa.dimTable[0]
    else:                           # custom pitch and diameter
        P = fa.calc_pitch if fa.calc_pitch else 1.0
        if self.sm3DPrintMode:
            dia = self.smScrewThrScaleA * float(fa.calc_diam) + self.smScrewThrScaleB
        else:
            dia = float(fa.calc_diam)

    # ── 2. Resolve effective diameter and pitch from threading modules ─────────
    #
    #  ASME  : d_eff from FSThreadingASME.get_shank_dia()
    #          P from fa.calc_pitch  (set by execute() from Thread_TPI selection)
    #          Properties shown: Thread_Type (UNC/UNF), Thread_TPI, Thread_Class
    #
    #  Metric: d_eff from FSThreadingMetric.get_shank_dia()
    #          P from fa.calc_pitch  (set by execute() from Thread_Pitch selection)
    #          Properties shown: Thread_Pitch, Thread_Class_ISO, Thread_Root
    #
    if is_asme:
        d_eff = _TA.get_shank_dia(fa, dia)
        if fa.calc_pitch is not None and fa.calc_pitch > 0:
            P = fa.calc_pitch
    else:
        d_eff = _TM.get_shank_dia(fa, dia)
        if fa.calc_pitch is not None and fa.calc_pitch > 0:
            P = fa.calc_pitch

    # ── 3. Rod body revolve profile ───────────────────────────────────────────
    #
    #  cham = 1 × pitch for all chamfers (ends + inner transitions).
    #
    #  Fully threaded  (Thread_Length = 0):
    #    Simple cylinder, chamfer at each outer end only.
    #
    #  Partial threading  (Thread_Length = L,  half = L/2):
    #    Transition chamfers at the inner boundary of each thread zone mirror
    #    the outer end chamfers — this gives a smooth thread exit toward the
    #    unthreaded middle section, identical in style to the rod end chamfers.
    #
    #    z = 0              →  top face
    #    z = -cham          →  top end chamfer end        (r = d_eff/2)
    #    z = -(half-cham)   →  top thread zone            (r = d_eff/2)
    #    z = -half          →  inner taper to smooth      (r = d_eff/2 - cham)
    #    z = -(len-half)    →  smooth zone end            (r = d_eff/2 - cham)
    #    z = -(len-half+cham) →  back to thread OD        (r = d_eff/2)
    #    z = -(len-cham)    →  bottom thread zone         (r = d_eff/2)
    #    z = -len           →  bottom end chamfer         (r = d_eff/2 - cham)
    #
    cham   = P          # chamfer depth at both ends = 1 × pitch
    length = fa.calc_len

    _raw_tl = getattr(fa, "calc_thread_length", 0.0) or 0.0
    _half   = float(_raw_tl) / 2.0
    # Use partial profile only when there is room for inner chamfers
    _partial = _raw_tl > 0 and _raw_tl < length and _half > 2 * cham

    fm = FSFaceMaker()
    fm.AddPoint(0,                  0)
    fm.AddPoint(d_eff / 2 - cham,   0)
    fm.AddPoint(d_eff / 2,         -cham)              # top end chamfer

    if _partial:
        fm.AddPoint(d_eff / 2,     -(_half - cham))    # top thread zone
        fm.AddPoint(d_eff / 2 - cham, -_half)          # inner taper → smooth
        fm.AddPoint(d_eff / 2 - cham, -(length-_half)) # smooth zone (parallel)
        fm.AddPoint(d_eff / 2,  -(length - _half + cham))  # taper back to thread OD
        fm.AddPoint(d_eff / 2,     -(length - cham))   # bottom thread zone
    else:
        fm.AddPoint(d_eff / 2,     -length + cham)     # straight to bottom chamfer

    fm.AddPoint(d_eff / 2 - cham,  -length)
    fm.AddPoint(0,                 -length)
    screw = self.RevolveZ(fm.GetFace())

    # ── 4. Threading ──────────────────────────────────────────────────────────
    #
    #  Thread_Length = 0  → fully threaded (one cut, full length)
    #  Thread_Length = L  → threaded from BOTH ends, each end L/2:
    #       Top end   : offset_z = 0,            tl = L/2
    #       Bottom end: offset_z = -(length-L/2), tl = L/2
    #
    #  Example: rod = 20mm, Thread_Length = 10mm
    #       → top 5mm threaded  (z = 0 to -5)
    #       → bottom 5mm threaded (z = -15 to -20)
    #       → middle 10mm unthreaded
    #
    if fa.Thread:
        raw_tlen  = getattr(fa, "calc_thread_length", 0.0) or 0.0
        half      = float(raw_tlen) / 2.0

        def _cut(shape, tl, oz):
            if is_asme:
                return _TA.cut_thread(shape, fa, d_eff, tl, oz, P)
            else:
                return _TM.cut_thread(shape, fa, d_eff, tl, oz, P)

        if raw_tlen <= 0 or raw_tlen >= length:
            # Thread_Length = 0 or >= total length → fully threaded
            screw = _cut(screw, length, 0.0)
        else:
            # Thread from both ends, half per end
            # Top end: starts at z = 0, goes down half
            screw = _cut(screw, half, 0.0)
            # Bottom end: starts at z = -(length - half), goes down half
            screw = _cut(screw, half, -(length - half))

    return screw
