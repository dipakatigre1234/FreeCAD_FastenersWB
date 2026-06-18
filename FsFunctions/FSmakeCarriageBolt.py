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

import FastenerBase

# ASMEB18.5.2 UNC Round head square neck bolts
# DIN603 Mushroom head square neck bolts
cos22_5 = math.cos(math.radians(22.5))
sin22_5 = math.sin(math.radians(22.5))


def makeCarriageBolt(self, fa):
    """Creates a carriage bolt (round head square neck).

    Supported types:
    - ASMEB18.5.2  UNC round head square neck bolts
    - DIN 603      Mushroom head square neck bolts

    Thread diameter formulas (Dipak):
      ASME/inch : thread_dia = dia - 0.15 / TPI
      Metric    : thread_dia = dia - 0.15 * P
    """
    SType   = fa.baseType
    length  = fa.calc_len
    d       = self.getDia(fa.calc_diam, False)
    is_asme = SType.startswith("ASME")

    # ── Unpack dimTable ───────────────────────────────────────────────────
    if SType == 'ASMEB18.5.2':
        tpi_tbl, _, A, H, O, P_dim, _, _ = fa.dimTable
        A, H, O, P_dim = (25.4 * x for x in (A, H, O, P_dim))
        P_tbl  = 25.4 / tpi_tbl
        L_t = (d * 2 + 6.35) if length <= 152.4 else (d * 2 + 12.7)

    elif SType == 'DIN603':
        P_tbl, b1, b2, b3, dk_max, dk_min, ds_max, ds_min, f_max, f_min, \
            k_max, k_min, r1_approx, r2_max, r2_max2, v_max, v_min = fa.dimTable
        A     = (dk_max + dk_min) / 2
        H     = k_max
        O     = v_max
        P_dim = f_max
        L_t   = b1 if length <= 125 else (b2 if length <= 200 else b3)

    else:
        raise NotImplementedError(f"Unknown fastener type: {SType}")

    # ── Pitch override (ThreadPitch mm / ThreadTPI) ───────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    pitch = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # ── Thread length override (ThreadLength from dashboard) ──────────────
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    L_t = min(float(raw_tlen), length) if raw_tlen > 0.0 else L_t

    # ── Thread diameter ───────────────────────────────────────────────────
    # ASME/inch : thread_dia = dia - 0.15 / TPI
    # Metric    : thread_dia = dia - 0.15 * P
    if is_asme:
        tpi = getattr(fa, "calc_tpi", None)
        if not tpi or tpi <= 0:
            tpi = round(25.4 / P_tbl)
        thread_dia = d - (0.15 / tpi)
        log_extra  = f"TPI={tpi}"
    else:
        thread_dia = d - 0.15 * pitch
        log_extra  = f"P={pitch:.3f}mm"

    tr = thread_dia / 2.0

    FreeCAD.Console.PrintMessage(
        f"[Dipak] Threading: dia={d:.4f}mm, "
        f"thread_dia={thread_dia:.4f}mm, {log_extra}, "
        f"allowance={d - thread_dia:.4f}mm, "
        f"thread_length={L_t:.2f}mm\n"
    )

    # ── Revolve profile ───────────────────────────────────────────────────
    # Head uses full d. Shaft uses tr (= thread_dia/2) so the revolved
    # solid is at thread_dia → volume changes correctly.
    head_r    = A / sqrt2
    flat_len  = length - P_dim
    r_fillet  = d * 0.05
    theta     = math.pi / 4

    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(0, H)
    fm.AddArc(
        head_r * math.sin(theta / 2),
        head_r * math.cos(theta / 2) - head_r + H,
        A / 2 - r_fillet + r_fillet * math.sin(theta),
        r_fillet * (1 + math.cos(theta)),
    )
    fm.AddArc(A / 2, r_fillet, A / 2 - r_fillet, 0)
    fm.AddPoint(sqrt2 / 2 * O,  0)
    fm.AddPoint(sqrt2 / 2 * O, -1 * P_dim + (sqrt2 / 2 * O - d / 2))
    fm.AddPoint(tr,             -1 * P_dim)   # shaft starts at thread radius

    if flat_len > L_t:
        if not fa.Thread:
            fm.AddPoint(tr, -length + L_t)
        thread_length = L_t
    else:
        thread_length = flat_len

    fm.AddPoint(tr,        -length + d / 10)
    fm.AddPoint(tr - d / 10, -length)
    fm.AddPoint(0,         -length)

    p_solid = self.RevolveZ(fm.GetFace())

    # ── Cut 4 flats under head ────────────────────────────────────────────
    d_mod    = d + 0.0002
    outerBox = Part.makeBox(
        A * 4, A * 4, P_dim + 0.0001,
        Base.Vector(-A * 2, -A * 2, -P_dim + 0.0001)
    )
    innerBox = Part.makeBox(
        d_mod, d_mod, P_dim * 3,
        Base.Vector(-d_mod / 2, -d_mod / 2, -P_dim * 2)
    )
    edgelist         = innerBox.Edges
    edges_to_fillet  = [
        e for e in edgelist
        if (abs(abs(e.CenterOfMass.x) - d_mod / 2) < 0.0001 and
            abs(abs(e.CenterOfMass.y) - d_mod / 2) < 0.0001)
    ]
    innerBox = innerBox.makeFillet(d * 0.08, edges_to_fillet)
    tool     = outerBox.cut(innerBox)
    p_solid  = p_solid.cut(tool)

    # ── Thread cutter ─────────────────────────────────────────────────────
    if fa.Thread:
        thread_cutter = self.CreateBlindThreadCutter(thread_dia, pitch, thread_length)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -1 * (length - thread_length)))
        p_solid = p_solid.cut(thread_cutter)

    return Part.Solid(p_solid)


def makeDIN608CarriageBolt(self, fa):
    """Create a DIN 608 flat countersunk head square neck bolt.

    Geometry is a 1:1 port of the DIN 608 master macro.  The M10-specific
    constants in that macro are replaced by values pulled from FsData via
    fa.dimTable; values the standard gives as max/min pairs (dk, ds, fn, v)
    are averaged to their mean.  Length is user-selectable and an optional
    ISO metric thread is cut on the lower b portion of the shank.

    DIN608def.csv column order (fa.dimTable):
      P, b, dk_max, dk_min, ds_max, ds_min, fn_max, fn_min, r, v_max, v_min, k
    where
      P       : thread pitch
      b       : thread length
      dk      : head diameter
      ds      : shank diameter            (macro: d)
      fn      : head + square-neck height (macro: S)
      r       : square corner radius      (macro: R_corner)
      v       : width across the square   (macro: B)
      k       : countersunk head height   (taken from the matching DIN 604
                head; the standard tabulates fn, not k separately)

    Coordinate origin (matches the macro):
      z = 0    top bearing face of the countersunk head
      z = -k   head / square-neck transition
      z = -S   square-neck / shaft transition
      z = -L   shaft tip
    """
    SType = fa.baseType
    if SType != "DIN608":
        raise NotImplementedError(f"Unknown carriage bolt type: {SType}")
    if fa.dimTable is None:
        raise ValueError("DIN608 carriage bolt requires a standard diameter")

    length = fa.calc_len

    # ── CSV dimensions ────────────────────────────────────────────────────
    (P_tbl, b,
     dk_max, dk_min,
     ds_max, ds_min,
     fn_max, fn_min,
     r, v_max, v_min, k) = (float(v) for v in fa.dimTable)

    # Mean values for the max/min pairs (per the standard's tolerance band)
    dk = (dk_max + dk_min) / 2.0     # head diameter
    d  = (ds_max + ds_min) / 2.0     # shank diameter (macro: d)
    S  = (fn_max + fn_min) / 2.0     # head + square-neck height (macro: S)
    B  = (v_max + v_min) / 2.0       # width across the square (macro: B)
    R_corner = r                     # square corner radius (single value)
    angle = 90.0                     # countersink included angle
    bottom_chamfer_size = d / 10.0

    # ── Pitch + thread length ─────────────────────────────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    pitch = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    L_t = b
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        L_t = float(raw_tlen)
    # Thread must not run into the square neck — clamp to the plain shaft
    L_t = max(0.0, min(L_t, length - S))

    # ── 1. Shaft with bottom chamfer ──────────────────────────────────────
    shaft_len  = length - S
    shaft_main = Part.makeCylinder(d / 2.0, shaft_len - bottom_chamfer_size)
    shaft_main.translate(FreeCAD.Vector(0, 0, -length + bottom_chamfer_size))

    shaft_chamfer = Part.makeCone(d / 2.0 - bottom_chamfer_size, d / 2.0, bottom_chamfer_size)
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -length))

    shaft = shaft_main.fuse(shaft_chamfer)

    # ── 2. Countersunk head with cylindrical flat ─────────────────────────
    half_angle_rad = math.radians(angle / 2.0)
    cone_height    = ((dk - d) / 2.0) / math.tan(half_angle_rad)
    f_margin       = k - cone_height          # cylindrical flat under the top

    head_cone = Part.makeCone(d / 2.0, dk / 2.0, cone_height)
    head_cone.translate(FreeCAD.Vector(0, 0, -k))

    if f_margin > 1e-6:
        head_flat = Part.makeCylinder(dk / 2.0, f_margin)
        head_flat.translate(FreeCAD.Vector(0, 0, -f_margin))
        head = head_flat.fuse(head_cone)
    else:
        head = head_cone

    # ── 3. Square neck with bottom conical taper ──────────────────────────
    R_diag  = (B / math.sqrt(2.0)) + 0.5      # diagonal radius enclosing the square
    H_taper = R_diag - d / 2.0                # height of the 45° bottom transition

    neck_cyl = Part.makeCylinder(R_diag, S - H_taper)
    neck_cyl.translate(FreeCAD.Vector(0, 0, -S + H_taper))

    neck_taper = Part.makeCone(d / 2.0, R_diag, H_taper)
    neck_taper.translate(FreeCAD.Vector(0, 0, -S))

    neck_raw = neck_cyl.fuse(neck_taper)

    outerBox = Part.makeBox(dk * 4, dk * 4, S * 3)
    outerBox.translate(FreeCAD.Vector(-dk * 2, -dk * 2, -S * 2))

    innerBox = Part.makeBox(B, B, S * 4)
    innerBox.translate(FreeCAD.Vector(-B / 2.0, -B / 2.0, -S * 2.5))

    vertical_edges = [e for e in innerBox.Edges
                      if abs(e.BoundBox.ZLength - S * 4) < 0.01]
    if vertical_edges and R_corner > 1e-4:
        innerBox = innerBox.makeFillet(R_corner, vertical_edges)

    tool       = outerBox.cut(innerBox)
    neck_final = neck_raw.cut(tool)

    # ── 4. Final assembly ─────────────────────────────────────────────────
    p_solid = shaft.fuse(neck_final).fuse(head)
    p_solid = p_solid.removeSplitter()

    # ── 5. Optional ISO metric thread on the lower b portion ──────────────
    if getattr(fa, "Thread", False) and L_t > 1e-6 and pitch > 0:
        thread_cutter = self.CreateBlindThreadCutter(d, pitch, L_t)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -(length - L_t)))
        p_solid = p_solid.cut(thread_cutter)

    return Part.Solid(p_solid)