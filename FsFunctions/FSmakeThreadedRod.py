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
    cham   = P          # chamfer depth at both ends = 1 × pitch
    length = fa.calc_len
    fm = FSFaceMaker()
    fm.AddPoint(0,                  0)
    fm.AddPoint(d_eff / 2 - cham,   0)
    fm.AddPoint(d_eff / 2,         -cham)
    fm.AddPoint(d_eff / 2,         -length + cham)
    fm.AddPoint(d_eff / 2 - cham,  -length)
    fm.AddPoint(0,                 -length)
    screw = self.RevolveZ(fm.GetFace())

    # ── 4. Threading ──────────────────────────────────────────────────────────
    #
    #  Thread runs the full rod length: tl = length, offset_z = 0.
    #  ASME  : FSThreadingASME.cut_thread()   — UN/UNR helix cutter
    #  Metric: FSThreadingMetric.cut_thread() — ISO metric helix cutter
    #
    if fa.Thread:
        tl_cut   = length
        offset_z = 0.0
        if is_asme:
            screw = _TA.cut_thread(screw, fa, d_eff, tl_cut, offset_z, P)
        else:
            screw = _TM.cut_thread(screw, fa, d_eff, tl_cut, offset_z, P)

    return screw
