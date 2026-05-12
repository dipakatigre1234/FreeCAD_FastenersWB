# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2022                                                    *
*   Alex Neufeld <alex.d.neufeld@gmail.com>                               *
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
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None
try:
    import FSThreadingASMEInternal as _TAI
except Exception:
    _TAI = None


def _cut_weldnut_threads(self, shape, fa, dia, depth, P):
    """Apply modelled internal threads for weld nuts (DIN/ISO metric + ASME fallback)."""
    if not fa.Thread:
        return shape

    is_asme = str(getattr(fa, "baseType", "") or "").startswith("ASME")

    if not is_asme and _TMI is not None:
        try:
            return _TMI.cut_internal_thread(shape, fa, dia, depth)
        except Exception as ex:
            FreeCAD.Console.PrintLog(
                f"[FSmakeWeldNut] metric thread sweep failed for "
                f"{fa.baseType} {fa.calc_diam}, falling back to legacy "
                f"thread cutter: {ex}\n"
            )

    if is_asme:
        eff_tpi = None
        if _TAI is not None:
            try:
                eff_tpi = _TAI.resolve_nut_tpi(fa)
            except Exception:
                eff_tpi = None
        if not eff_tpi and getattr(fa, "calc_tpi", None):
            try:
                eff_tpi = float(fa.calc_tpi)
            except Exception:
                eff_tpi = None
        if not eff_tpi or eff_tpi <= 0:
            eff_tpi = 25.4 / P if P > 0 else 8.0
        p_thread = 25.4 / eff_tpi if eff_tpi > 0 else P
        thread_dia = dia + 0.05 / eff_tpi
        thread_cutter = self.CreateInnerThreadCutter(thread_dia, p_thread, depth + p_thread)
        return shape.cut(thread_cutter)

    if _TMI is not None:
        try:
            p_metric = _TMI.resolve_nut_pitch(fa)
            if p_metric and p_metric > 0:
                P = p_metric
        except Exception:
            pass
    elif getattr(fa, "calc_pitch", None):
        try:
            if fa.calc_pitch > 0:
                P = fa.calc_pitch
        except Exception:
            pass

    thread_dia = dia + 0.05 * P
    thread_cutter = self.CreateInnerThreadCutter(thread_dia, P, depth + P)
    return shape.cut(thread_cutter)


def _metric_thread_pitch_for_nut(fa, P_default):
    """Resolve metric nut pitch to keep bore/chamfer geometry aligned with thread cutter."""
    if _TMI is not None:
        try:
            p = _TMI.resolve_nut_pitch(fa)
            if p and p > 0:
                return p
        except Exception:
            pass
    try:
        cp = float(getattr(fa, "calc_pitch", 0) or 0)
        if cp > 0:
            return cp
    except Exception:
        pass
    return P_default


def _metric_bore_dia_for_nut(self, fa, dia, P):
    """Return bore diameter used by weld-nut pre-bore profile."""
    if _TMI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _p_s = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "") or "6H")
            if not _p_s:
                _p_s = str(_metric_thread_pitch_for_nut(fa, P))
            if _p_s:
                return _TMI.bore_dia_from_table(fa, _dia_s, _p_s, _cls_s)
        except Exception:
            pass
    return self.GetInnerThreadMinDiameter(dia, P, 0.0)


def makeWeldNut(self, fa):
    """Creates a nut with geometry optimized for resistance welding to a
    flat surface.
    Supported types:
    - DIN 928 square weld nuts
    - DIN 929 hexagon weld nuts
    - ISO 2167 hexagon weld nuts with flange
    """
    if fa.baseType == "DIN928":
        return _makeSquareWeldNut(self, fa)
    elif fa.baseType == "DIN929":
        return _makeHexWeldNut(self, fa)
    elif fa.baseType == "ISO21670":
        return _makeFlangedWeldNut(self, fa)
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")


def _makeHexWeldNut(self, fa):
    dia = self.getDia(fa.calc_diam, True)
    P, b, d2, d3, h1, h2, m, s = fa.dimTable
    P = _metric_thread_pitch_for_nut(fa, P)
    # overall hexagon shape
    shape = self.makeHexPrism(s, m)
    # add the chamfer to the top of the nut
    fm = FSFaceMaker()
    fm.AddPoint(s / 2, m)
    fm.AddPoint(s / sqrt3,  m)
    cham_ht = s * (1 / sqrt3 - 0.5) * math.tan(math.radians(30))
    fm.AddPoint(s / sqrt3, m - cham_ht)
    top_cham_cutter = self.RevolveZ(fm.GetFace())
    shape = shape.cut(top_cham_cutter)
    # make another shape to cut the protrusions on the bottom of the nut
    bottom_cutter = Part.makeCylinder(s, h1)
    fm.Reset()
    fm.AddPoint(s / sqrt3 - b, h1)
    lug_w = (h1 - h2) * math.tan(math.radians(25))
    fm.AddPoint(s / sqrt3 - b + lug_w, h1 - h2)
    fm.AddPoint(s, h1 - h2)
    fm.AddPoint(s, h1)
    lug_cutter = fm.GetFace().extrude(Base.Vector(0.0, 2 * s, 0.0))
    lug_cutter.translate(Base.Vector(0.0, -s, 0.0))
    for i in range(3):
        lug_cutter.rotate(Base.Vector(0.0, 0.0, 0.0),
                          Base.Vector(0.0, 0.0, 1.0), 120)
        bottom_cutter = bottom_cutter.cut(lug_cutter)
    inner_cyl = Part.makeCylinder(d2 / 2, h1)
    bottom_cutter = bottom_cutter.cut(inner_cyl)
    shape = shape.cut(bottom_cutter)
    # add the bore for the threads.
    # there is also a shallow counterbore at the top face of the nut
    fm.Reset()
    id = _metric_bore_dia_for_nut(self, fa, dia, P)
    bore_cham_ht = (dia * 1.05 - id) / 2 * math.tan(math.radians(30))
    fm.AddPoint(0.0, 0.0)
    fm.AddPoint(dia * 1.05 / 2, 0.0)
    fm.AddPoint(id / 2, bore_cham_ht)
    fm.AddPoint(id / 2, m - bore_cham_ht - 0.2)
    fm.AddPoint(dia * 1.05 / 2, m - 0.2)
    fm.AddPoint(d3 / 2, m - 0.2)
    fm.AddPoint(d3 / 2, m)
    fm.AddPoint(0.0, m)
    bore_cutter = self.RevolveZ(fm.GetFace())
    shape = shape.cut(bore_cutter)
    shape = _cut_weldnut_threads(self, shape, fa, dia, m, P)
    # transform so that the XY-plane relates better to the installed height
    mat = Base.Matrix()
    mat.move(Base.Vector(0.0, 0.0, -h1))
    shape = shape.SubShapes[0]
    shape.transformShape(mat)
    return Part.Compound([shape])


def _makeFlangedWeldNut(self, fa):
    dia = self.getDia(fa.calc_diam, True)
    P,b,c,d_a,d_c,e,f,g,m_min,m_max,s,r_1,r_2,_ = fa.dimTable
    P = _metric_thread_pitch_for_nut(fa, P)
    m = (m_min + m_max) / 2
    # main hexagonal body of the nut
    shape = self.makeHexPrism(s, m)
    # flanged section
    fm = FSFaceMaker()
    fm.AddPoint(0.0, f)
    fm.AddPoint(d_c/2 - r_2, f)
    fm.AddArc2(0.0, -r_2, -90)
    fm.AddPoint(d_c/2, 0.0)
    h3 = r_1 * math.sin(math.radians(15))
    h4 = r_1 * math.sin(math.radians(45))
    fm.AddPoint(d_c/2 - abs(-c+r_1-h3) * tan15 , -c+r_1-h3)
    fm.AddArc2(-h3/tan15, h3, -120)
    fm.AddPointRelative(-1*(c-r_1+h4),c-r_1+h4)
    fm.AddPoint(0.0, 0.0)
    shape = shape.fuse(self.RevolveZ(fm.GetFace()))
    # internal bore
    fm.Reset()
    id = _metric_bore_dia_for_nut(self, fa, dia, P)
    bore_cham_ht = (dia * 1.05 - id) / 2 * math.tan(math.radians(30))
    fm.AddPoint(0.0, 0.0)
    fm.AddPoint(dia * 1.05 / 2, 0.0)
    fm.AddPoint(id / 2, bore_cham_ht)
    fm.AddPoint(id / 2, m - bore_cham_ht - 0.2)
    fm.AddPoint(dia * 1.05 / 2, m)
    fm.AddPoint(0.0, m)
    bore_cutter = self.RevolveZ(fm.GetFace())
    shape = shape.cut(bore_cutter)
    # outer chamfer on the hex
    fm.Reset()
    fm.AddPoint(s / 2, m)
    fm.AddPoint(s / sqrt3,  m)
    cham_ht = s * (1 / sqrt3 - 0.5) * math.tan(math.radians(30))
    fm.AddPoint(s / sqrt3, m - cham_ht)
    top_cham_cutter = self.RevolveZ(fm.GetFace())
    shape = shape.cut(top_cham_cutter)
    # bottom notches in the weld tabs
    fm.Reset()
    fm.AddPoint(g/2,g/2*math.tan(math.radians(30)))
    fm.AddPoint(g/2, d_c/2)
    th1 = math.degrees(math.atan((g/2)/(d_c/2)))
    fm.AddArc2(-g/2, -d_c/2 , -(120-2*th1))
    cutter_face = fm.GetFace()
    cutter_face = cutter_face.rotated(Base.Vector(0.0, 0.0, 0.0), Base.Vector(1.0, 0.0, 0.0), 90)
    cutter = cutter_face.extrude(Base.Vector(0.0, 0.0, -20.0))
    for i in range(3):
        cutter.rotate(Base.Vector(0.0, 0.0, 0.0),
                          Base.Vector(0.0, 0.0, 1.0), 120)
        shape = shape.cut(cutter)
    shape = shape.removeSplitter()
    shape = _cut_weldnut_threads(self, shape, fa, dia, m, P)
    return shape


def _makeSquareWeldNut(self, fa):
    dia = self.getDia(fa.calc_diam, True)
    if fa.baseType == "DIN928":
        P, b, d2, d4, h1, h2, m, s = fa.dimTable
    P = _metric_thread_pitch_for_nut(fa, P)
    # the main body of the nut is a rectangular prism
    shape = Part.makeBox(s, s, m + h1 + h2)
    shape.translate(Base.Vector(-s / 2, -s / 2, 0.0))
    # make another shape to cut the protrusions on the bottom of the nut
    bottom_cutter = Part.makeCylinder(s, h1)
    fm = FSFaceMaker()
    fm.AddPoint(s, 0.0)
    fm.AddPoint(s * sqrt2 / 2 - b, 0.0)
    fm.AddPoint(s * sqrt2 / 2 - b - h1, h1)
    fm.AddPoint(s, h1)
    lug_cutter = fm.GetFace().extrude(Base.Vector(0.0, 2 * s, 0.0))
    lug_cutter.translate(Base.Vector(0.0, -s, 0.0))
    lug_cutter.rotate(Base.Vector(0.0, 0.0, 0.0),
                      Base.Vector(0.0, 0.0, 1.0), 45)
    for _ in range(4):
        lug_cutter.rotate(Base.Vector(0.0, 0.0, 0.0),
                          Base.Vector(0.0, 0.0, 1.0), 90)
        bottom_cutter = bottom_cutter.cut(lug_cutter)
    shape = shape.cut(bottom_cutter)
    # lay out a cutting tool to define the other features of the nut
    fm.Reset()
    id = _metric_bore_dia_for_nut(self, fa, dia, P)
    bore_cham_ht = (dia * 1.05 - id) / 2 * math.tan(math.radians(45))
    fm.AddPoint(s * sqrt2 / 2, 0.0)
    fm.AddPoint(dia * 1.05 / 2, 0.0)
    fm.AddPoint(dia * 1.05 / 2, h1)
    fm.AddPoint(id / 2, h1 + bore_cham_ht)
    fm.AddPoint(id / 2, m + h2 - bore_cham_ht)
    fm.AddPoint(dia * 1.05 / 2, m + h2 - 0.02)
    fm.AddPoint(d2 / 2, m + h2 - 0.02)
    fm.AddPoint(d2 / 2, m + h2)
    fm.AddPoint(d4 / 2, m + h2)
    fm.AddPoint(d4 / 2, m)
    fm.AddPoint(s / 2, m)
    top_cham_ht = s * (sqrt2 - 1) / 2 * tan15
    fm.AddPoint(s * sqrt2 / 2, m - top_cham_ht)
    revolve = self.RevolveZ(fm.GetFace())
    shape = shape.common(revolve)
    shape = _cut_weldnut_threads(self, shape, fa, dia, m + h1 + h2, P)
    # transform so that the XY-plane relates better to the installed height
    mat = Base.Matrix()
    mat.move(Base.Vector(0.0, 0.0, -h1))
    shape = shape.SubShapes[0]
    shape.transformShape(mat)
    return Part.Compound([shape])
