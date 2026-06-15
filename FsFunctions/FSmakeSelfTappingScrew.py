# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2023, 2024                                              *
*   Original code by:                                                     *
*   hasecilu <hasecilu[at]tuta.io>                                        *
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
import math
import Part
from FreeCAD import Base
import FastenerBase
from FastenerBase import FsTitles
from screw_maker import FsData

def makeSelfTappingScrew(self, fa):
    """
    Make a self tapping screw, used on sheet metal and plastic holes
    Supported types:
    - ISO7049-[C/F/R]: Cross-recessed pan head tapping screws
    - DIN7504K: Hexagon head self-drilling tapping screws
    """
    if fa.baseType[:7] == "ISO7049":
        return makeISO7049(self, fa)
    if fa.baseType == "DIN7504K":
        return makeDIN7504K(self, fa)

    raise NotImplementedError(f"Unknown fastener type: {fa.baseType}")

def makeISO7049(self, fa):
    """
    Make an ISO7049 Cross-recessed pan head tapping screw
    Variations:
    - ISO7049-C: Self tapping screw with conical point
    - ISO7049-F: Self tapping screw with flat point
    - ISO7049-R: Self tapping screw with round point
    """
    SType = fa.baseType
    l = fa.calc_len
    # Convert from string "ST x.y" to x.y float
    dia = self.getDia(fa.calc_diam, False)

    # NOTE: The norm ISO1478 defines: "Tapping screws thread"
    # Read data from the thread norm definition
    # instead of duplicating it on the screw definition.
    P, _, _, d2, _, d3, _, _, rR, _, _, _, _ = FsData["iso1478def"][fa.calc_diam]
    _, D, _, K, _, r, _, PH, m, h, _ = fa.dimTable

    b = l # length for the thread from the tip
    full_length = True

    ri = d2 / 2.0   # inner thread radius
    ro = dia / 2.0  # outer thread radius

    # inner radius of screw section
    sr = ro
    if fa.Thread:
        sr = ri

    # length of cylindrical part where thread begins to grow.
    slope_length = ro - ri

    # Sharpness of screw tip is equal 45 degrees. If imagine half of screw tip
    # as a triangle, then acute-angled angle of the triangle (alpha) be which
    # is equal to half of the screw tip angle.
    alpha = 45
    # And the adjacent cathetus be which is equal to least screw radius (sr)
    # Then the opposite cathetus can be getted by formula: tip_length=sr/tg(alpha)
    tip_length = sr / math.tan(math.radians(alpha / 2))
    if SType == "ISO7049-F":
        tip_length = sr - d3 / 2

    fm = FastenerBase.FSFaceMaker()

    # 1) screw head
    fm.AddPoint(0, K)
    fm.AddBSpline(D/2, K, D/2, 0)

    # 2) add rounding under screw head
    rr = r
    fm.AddPoint(ro+rr, 0)      # first point of rounding
    if fa.Thread and full_length:
        fm.AddBSpline(ro, 0, sr, -slope_length) # create spline rounding
    else:
        fm.AddArc2(+0, -rr, 90) # in other cases create arc rounding

    # 3) cylindrical part (place where thread will be added)
    if not full_length:
        if fa.Thread:
            fm.AddPoint(ro, -l+b+slope_length)    # entery point of thread
        fm.AddPoint(sr, -l+b)   # start of full width thread b >= l*0.6

    # 4) tip shape
    if SType == "ISO7049-C":
        fm.AddPoint(sr, -l+tip_length)
        fm.AddPoint(0, -l)
    if SType == "ISO7049-F":
        fm.AddPoint(sr, -l+tip_length)
        fm.AddPoint(d3 / 2, -l)
        fm.AddPoint(0, -l)
    if SType == "ISO7049-R":
        fm.AddPoint(sr, -l+tip_length)
        fm.AddPoint(rR*math.cos(math.radians(alpha)), rR-l)
        fm.AddArc2(-rR*math.cos(math.radians(alpha)),
                   rR*math.sin(math.radians(alpha)), -alpha)

    # make screw solid body by revolve a profile
    screw = self.RevolveZ(fm.GetFace())

    # make cross slot in screw head
    recess = self.makeHCrossRecess(PH, m)
    recess = recess.translate(Base.Vector(0.0, 0.0, h))
    screw = screw.cut(recess)

    # make thread
    if fa.Thread:
        if SType == "ISO7049-C":
            # vanilla usage
            thread = self.makeDin7998Thread(-l+b+slope_length, -l+tip_length,
                                            -l, ri, ro, P)
        if SType == "ISO7049-F":
            # sent flag to omit the tip thread
            thread = self.makeDin7998Thread(-l+b+slope_length, -l+tip_length,
                                            -l, ri, ro, P, True)
        if SType == "ISO7049-R":
            # move the tip a little up to compensate roundness
            thread = self.makeDin7998Thread(-l+b+slope_length, -l+tip_length,
                                            -l+rR, ri, ro, P)
        screw = screw.fuse(thread)

    return screw


def makeDIN7504K(self, fa):
    """
    DIN 7504K hex head self-drilling tapping screw.

    All dimensions from CSV (din7504kdef.csv):
      dimTable indices (after Dia key):
        0  = screw thread dia   → thread major OD
        1  = dc_max             → head flange OD
        2  = dc_min
        3  = c_min              → flange thickness
        4  = k_max              → head height
        5  = k_min
        6  = s_nom              → wrench size
        7  = s_min
        8  = e_min
        9  = k_prime_min
        10 = dp                 → core shank / drill-point diameter
        11 = d1_minor           → thread minor (root) diameter
        12 = pitch              → thread pitch P

    Geometry:
      - Thread zone body at d1_minor (thread root), thread OD = screw_thread_dia
      - Thread extends from head underside down to dp chamfer transition
      - 45° chamfer bridges d1_minor ↔ dp at thread-to-drill transition
      - Drill point at 118° cone, shank at dp
    """
    l = fa.calc_len
    dia = self.getDia(fa.calc_diam, False)

    dt = fa.dimTable
    thread_dia = float(dt[0])
    dc_max     = float(dt[1])
    c_min      = float(dt[3])
    k_max      = float(dt[4])
    s_nom      = float(dt[6])
    dp         = float(dt[10])
    d1_minor   = float(dt[11])
    P          = float(dt[12])

    dc = dc_max
    k  = k_max
    s  = s_nom
    c  = c_min

    thread_ro = thread_dia / 2.0
    thread_ri = d1_minor / 2.0
    shank_ro  = dp / 2.0

    lg = max(_getDIN7504KThreadLength(fa, l), 0.0)
    thread_length  = min(lg, l)
    cutting_length = max(l - thread_length, 0.0)
    thread_stop_z  = -(l - 0.5 * cutting_length)

    point_angle = 118.0
    cone_length = shank_ro / math.tan(math.radians(point_angle / 2.0))
    chamfer_h   = abs(shank_ro - thread_ri)

    flange_ramp_height = max(k - c, 0.0) * 0.25
    hex_top_z = max(k - flange_ramp_height, c)

    # ── Head ─────────────────────────────────────────────────────────────
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(0.0, k)
    fm.AddPoint(s / 2.0, k)
    fm.AddPoint(s / math.sqrt(3.0), hex_top_z)
    fm.AddPoint(s / math.sqrt(3.0), c)
    fm.AddPoint(0.0, c)
    head = self.RevolveZ(fm.GetFace())

    hex_tool = self.makeHexPrism(s, k - c + 2.0)
    hex_tool.translate(Base.Vector(0.0, 0.0, c - 1.0))
    head = head.common(hex_tool)

    # ── Body profile ─────────────────────────────────────────────────────
    body_ro = thread_ri if fa.Thread else shank_ro

    fm.Reset()
    fm.AddPoint(0.0, c)
    fm.AddPoint(dc / 2.0, c)
    fm.AddPoint(dc / 2.0, 0.0)
    fm.AddPoint(body_ro, 0.0)

    if cutting_length > 0.0:
        fm.AddPoint(body_ro, thread_stop_z)
        if abs(body_ro - shank_ro) > 0.001:
            fm.AddPoint(shank_ro, thread_stop_z - chamfer_h)
    else:
        if abs(body_ro - shank_ro) > 0.001:
            z_cs = -l + cone_length + chamfer_h
            fm.AddPoint(body_ro, z_cs)
            fm.AddPoint(shank_ro, z_cs - chamfer_h)

    fm.AddPoint(shank_ro, -l + cone_length)
    fm.AddPoint(0.0, -l)

    body = head.fuse(self.RevolveZ(fm.GetFace()))
    body = _cutDIN7504KDrillFlutes(body, l, dia, cutting_length, self.LeftHanded)

    # ── Thread ───────────────────────────────────────────────────────────
    threaded_span = max(-thread_stop_z, 0.0)
    if fa.Thread and threaded_span > 0.01 and thread_ro > thread_ri:
        max_runout = max(threaded_span - 0.01, 0.01)
        runout_len = min(max(P * 1.5, thread_ro - thread_ri), max_runout)
        runout_start_z = -(threaded_span - runout_len)
        slope_length = thread_ro - thread_ri

        thread = self.makeDin7998Thread(
            slope_length,
            runout_start_z,
            thread_stop_z,
            thread_ri,
            thread_ro,
            P,
            False,
        )
        thread = _cutDIN7504KDrillFlutes(thread, l, dia, cutting_length, self.LeftHanded)
        return body.fuse(thread).removeSplitter()

    return body


def _getDIN7504KThreadLength(fa, length):
    thread_lengths = FsData.get("DIN7504Kthreadlength", {})
    length_key = str(length).rstrip("0").rstrip(".")
    titles = FsTitles.get("DIN7504Kthreadlength", ())
    if fa.calc_diam not in titles:
        return length

    idx = titles.index(fa.calc_diam)

    def _to_float(v):
        if v in ("", None):
            return None
        try:
            return float(v)
        except Exception:
            return None

    if length_key in thread_lengths:
        value = _to_float(thread_lengths[length_key][idx])
        if value is not None:
            return min(value, length)

    samples = []
    for l_key, row in thread_lengths.items():
        lg_val = _to_float(row[idx])
        if lg_val is None:
            continue
        try:
            l_std = float(l_key)
        except Exception:
            continue
        cutting_std = max(l_std - lg_val, 0.0)
        samples.append((l_std, cutting_std))

    if samples:
        l_near, cutting_near = min(samples, key=lambda x: abs(x[0] - length))
        lg_est = max(length - min(cutting_near, length), 0.0)
        return lg_est

    return length


def _cutDIN7504KDrillFlutes(screw, length, dia, cutting_length, left_handed=False):
    if cutting_length <= 0.0:
        return screw

    len1 = cutting_length * 0.60
    angle1 = 5.0
    z_rise1 = len1 * math.tan(math.radians(angle1))
    target_rise = dia / 2.0 + 0.1
    remaining_length = max(cutting_length - len1, 0.001)
    angle2 = math.degrees(math.atan((target_rise - z_rise1) / remaining_length))

    box_size = dia * 4.0
    cut_length = cutting_length
    z_rise2 = z_rise1 + (cut_length - len1) * math.tan(math.radians(angle2))
    tip_z = -length

    dir_sign = 1.0 if left_handed else -1.0

    points = [
        Base.Vector(0.0, 0.0, tip_z),
        Base.Vector(dir_sign * z_rise1, 0.0, tip_z + len1),
        Base.Vector(dir_sign * z_rise2, 0.0, tip_z + cut_length),
        Base.Vector(dir_sign * box_size, 0.0, tip_z + cut_length),
        Base.Vector(dir_sign * box_size, 0.0, tip_z),
        Base.Vector(0.0, 0.0, tip_z),
    ]

    cutter = Part.Face(Part.makePolygon(points)).extrude(Base.Vector(0.0, box_size, 0.0))
    cutter2 = cutter.copy()
    cutter2.rotate(Base.Vector(0.0, 0.0, 0.0), Base.Vector(0.0, 0.0, 1.0), 180)

    return screw.cut(cutter).cut(cutter2).removeSplitter()
