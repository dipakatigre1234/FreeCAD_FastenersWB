# -*- coding: utf-8 -*-
"""
***************************************************************************
*   FSmakeNibBolt.py                                                       *
*                                                                          *
*   DIN 604 — Countersunk (flat) bolt with nib  (Senkschraube mit Nase)    *
*                                                                          *
*   Geometry is a 1:1 port of the DIN 604 master macro.  The M10-specific  *
*   constants in that macro are replaced by values pulled from FsData via  *
*   fa.dimTable; values the standard gives as max/min pairs (dk, ds, g,    *
*   alpha) are averaged to their mean.  Length is user-selectable and an   *
*   optional ISO metric thread is cut on the lower b portion of the shank. *
*                                                                          *
*   CSV  DIN604def.csv  "DIN604def" table column order (fa.dimTable):      *
*     P, b1, b2, b3, dk_max, dk_min, ds_max, ds_min, g_max, g_min,         *
*     i, k, alpha_min, alpha_max                                           *
*   where                                                                  *
*     P            : thread pitch                                          *
*     b1, b2, b3   : thread length for l<=125 / 125<l<=200 / l>200         *
*     dk           : head diameter                                         *
*     ds           : shank diameter                                        *
*     g            : nib width                                             *
*     i            : nib depth (min) — not used by the geometry            *
*     k            : head height                                           *
*     alpha        : countersunk included angle (90° <=M16, 60° >=M20)     *
***************************************************************************
"""
from screw_maker import *

import sys as _sys_t, os as _os_t
_wb_t = _os_t.path.dirname(_os_t.path.dirname(_os_t.path.abspath(__file__)))
if _wb_t not in _sys_t.path:
    _sys_t.path.insert(0, _wb_t)


def makeNibBolt(self, fa):
    """Create a DIN 604 countersunk bolt with nib.

    Coordinate origin (matches the macro):
      z = 0      top bearing face of the countersunk head
      z = -k     head / shank junction
      z = -L     shank tip
    """
    SType = fa.baseType
    if SType != "DIN604":
        raise NotImplementedError(f"Unknown nib bolt type: {SType}")
    if fa.dimTable is None:
        raise ValueError("DIN604 nib bolt requires a standard diameter")

    length = fa.calc_len

    # ── CSV dimensions ────────────────────────────────────────────────────
    (P_tbl, b1, b2, b3,
     dk_max, dk_min,
     ds_max, ds_min,
     g_max, g_min,
     i_min, k,
     alpha_min, alpha_max) = (float(v) for v in fa.dimTable)

    # Mean values for the max/min pairs
    dk    = (dk_max + dk_min) / 2.0     # head diameter
    d     = (ds_max + ds_min) / 2.0     # shank diameter (macro: d)
    g     = (g_max + g_min) / 2.0       # nib width
    alpha = (alpha_min + alpha_max) / 2.0   # countersunk included angle

    # ── Pitch + thread length ─────────────────────────────────────────────
    raw_pitch = getattr(fa, "calc_pitch", None)
    pitch = raw_pitch if (raw_pitch is not None and raw_pitch > 0.0) else P_tbl

    # b by length band (DIN 604 b1/b2/b3), with dashboard override
    L_t = b1 if length <= 125 else (b2 if length <= 200 else b3)
    raw_tlen = getattr(fa, "calc_thread_length", 0.0) or 0.0
    if raw_tlen > 0.0:
        L_t = float(raw_tlen)
    # Thread cannot run into the head — clamp to the shank length
    L_t = max(0.0, min(L_t, length - k))

    # Fixed forging drafts (from the macro)
    angle_outer  = 5.0      # inward draft on the outer nib face
    angle_bottom = 15.0     # upward draft on the bottom nib face
    bottom_chamfer_size = d / 10.0

    # ─────────────────────────────────────────────────────────────────────
    # 1. Main body — shank + countersunk head
    # ─────────────────────────────────────────────────────────────────────
    shaft_main = Part.makeCylinder(d / 2.0, length - k - bottom_chamfer_size)
    shaft_main.translate(FreeCAD.Vector(0, 0, -length + bottom_chamfer_size))

    shaft_chamfer = Part.makeCone(d / 2.0 - bottom_chamfer_size, d / 2.0, bottom_chamfer_size)
    shaft_chamfer.translate(FreeCAD.Vector(0, 0, -length))

    half_alpha_rad = math.radians(alpha / 2.0)
    cone_height    = ((dk - d) / 2.0) / math.tan(half_alpha_rad)
    f_margin       = k - cone_height            # cylindrical flat under the head top

    head_flat = Part.makeCylinder(dk / 2.0, f_margin)
    head_flat.translate(FreeCAD.Vector(0, 0, -f_margin))

    head_cone = Part.makeCone(d / 2.0, dk / 2.0, cone_height)
    head_cone.translate(FreeCAD.Vector(0, 0, -k))

    main_body = shaft_main.fuse(shaft_chamfer).fuse(head_cone).fuse(head_flat)

    # ─────────────────────────────────────────────────────────────────────
    # 2. Revolved nib ring profile
    # ─────────────────────────────────────────────────────────────────────
    tan5  = math.tan(math.radians(angle_outer))
    tan15 = math.tan(math.radians(angle_bottom))

    term_in_bracket = ((dk - d) / 2.0) + (f_margin * tan5)
    numerator       = -k + term_in_bracket * tan15
    denominator     = 1.0 - (tan5 * tan15)
    z_int           = numerator / denominator
    x_int           = (dk / 2.0) + (z_int + f_margin) * tan5

    p0 = FreeCAD.Vector(0,        0, -f_margin)
    p1 = FreeCAD.Vector(dk / 2.0, 0, -f_margin)
    p2 = FreeCAD.Vector(x_int,    0, z_int)
    p3 = FreeCAD.Vector(d / 2.0,  0, -k)
    p4 = FreeCAD.Vector(0,        0, -k)

    nib_wire = Part.makePolygon([p0, p1, p2, p3, p4, p0])
    nib_face = Part.Face(nib_wire)
    nib_ring = nib_face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360)

    # ─────────────────────────────────────────────────────────────────────
    # 3. Notch + nib insert boolean logic
    # ─────────────────────────────────────────────────────────────────────
    box_length = dk + 5.0
    box_width  = g
    box_height = cone_height          # only the conical region, never the flat

    slice_box = Part.makeBox(box_length, box_width, box_height)
    slice_box.translate(FreeCAD.Vector(0, -g / 2.0, -k))

    notched_body = main_body.cut(slice_box)
    nib_insert   = nib_ring.common(slice_box)

    final_solid = notched_body.fuse(nib_insert)
    final_solid = final_solid.removeSplitter()

    # ─────────────────────────────────────────────────────────────────────
    # 4. Optional ISO metric thread on the lower b portion of the shank
    # ─────────────────────────────────────────────────────────────────────
    if getattr(fa, "Thread", False) and L_t > 1e-6 and pitch > 0:
        thread_cutter = self.CreateBlindThreadCutter(d, pitch, L_t)
        thread_cutter.translate(Base.Vector(0.0, 0.0, -(length - L_t)))
        final_solid = final_solid.cut(thread_cutter)

    return Part.Solid(final_solid)
