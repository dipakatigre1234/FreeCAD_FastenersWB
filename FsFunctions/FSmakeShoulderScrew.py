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

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)
import FSThreadingASME   as _TA
import FSThreadingMetric as _TM



def makeShoulderScrew(self, fa):
    """creates a screw with a cylindrical head and a round shoulder section

    supported types:
    - ISO 7379 shoulder screws
    - ASMEB18.3.4 shoulder screws
    """
    SType   = fa.baseType
    length  = fa.calc_len
    d2      = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")

    # ── Unpack dimTable ───────────────────────────────────────────────────
    if SType == 'ISO7379':
        # CSV cols: P, d1, d3, l2, l3, SW  (6 cols)
        P, d1, d3, l2, l3, SW = fa.dimTable

    elif SType == 'ASMEB18.3.4':
        # CSV cols: P, d1, dk_max, dk_min, l2, k_max, k_min, SW  (8 cols)
        P, d1, dk_max, dk_min, l2, k_max, k_min, SW = fa.dimTable
        # Mean values (default)
        d3 = (dk_max + dk_min) / 2   # head diameter
        l3 = (k_max  + k_min)  / 2   # head height

    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── Pitch override (ThreadPitch / TPI from dashboard) ─────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch is not None and float(raw_pitch) > 0.0) else P

    # ── Effective shank diameter from threading module ────────────────────
    # NOTE: d_eff and tr are computed exactly as in the original.
    # The threading module (get_shank_dia) already handles deriving the
    # correct minor/pitch diameter from fa — do not override it here.
    d_eff = _TA.get_shank_dia(fa, d2) if is_asme else _TM.get_shank_dia(fa, d2)
    tr    = d_eff / 2.0
    l1    = length

    # ── Revolve profile ── GEOMETRY UNCHANGED FROM ORIGINAL ──────────────
    fm = FSFaceMaker()
    fm.AddPoint(0,                      l1 + l3)
    fm.AddPoint(d3 / 2 - 0.04 * d3,    l1 + l3)
    fm.AddPoint(d3 / 2,                 l1 + l3 - 0.04 * d3)
    fm.AddPoint(d3 / 2,                 l1)
    fm.AddPoint(d1 / 2,                 l1)
    fm.AddArc(d1 / 2 - 0.04 * d1, l1 - 0.1 * l3, d1 / 2, l1 - 0.2 * l3)
    fm.AddPoint(d1 / 2,                 0)
    fm.AddPoint(tr,                     0)
    fm.AddPoint(tr,                     -l2 + d_eff / 10)
    fm.AddPoint(d_eff * 4 / 10,         -l2)
    fm.AddPoint(0,                      -l2)
    screw = self.RevolveZ(fm.GetFace())

    # ── Cut hexagonal socket recess into head ─────────────────────────────
    recess = self.makeHexRecess(SW, l3 * 0.4, True)
    recess.translate(Base.Vector(0.0, 0.0, l1 + l3))
    screw = screw.cut(recess)

    # ── Cut modelled threads ── THREADING CALL UNCHANGED FROM ORIGINAL ────
    # d_eff passed to cut_thread is what produces the correct helical grooves.
    # Do NOT substitute d2 here — that removes the grooves.
    if fa.Thread:
        offset_z = 0.0
        if is_asme:
            screw = _TA.cut_thread(screw, fa, d_eff, l2, offset_z, P)
        else:
            screw = _TM.cut_thread(screw, fa, d_eff, l2, offset_z, P)

    return screw