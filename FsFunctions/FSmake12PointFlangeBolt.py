# -*- coding: utf-8 -*-
"""
ASME B18.2.5M  12-Point Flange Bolt (metric)

CSV columns (after Dia):
  Pitch, S_Max, S_Min, K_Max, K_Min, Kw_Min,
  Dc_Max, Dc_Min, C_Max, C_Min, R1_Min, Da_Max, WireDia_Min

  S    -- width across flats (hex circumscribed circle)
  K    -- total head height
  Kw   -- wrenching height (height of 12-point star section)
  Dc   -- flange collar diameter
  C    -- flange edge thickness 
  R1   -- underhead fillet radius
  Da   -- shank-to-flange transition diameter
"""

import math
from screw_maker import *

import sys as _sys, os as _os
_wb = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _wb not in _sys.path:
    _sys.path.insert(0, _wb)
import FSThreadingMetric as _TM


def make12PointFlangeBolt(self, fa):
    """Generate ASME B18.2.5M 12-Point Flange Bolt."""

    # ── 1. Unpack dimensions from the CSV ─────────────────────────────────────
    try:
        (P_csv, S_max, S_min, K_max, K_min, Kw_min,
         Dc_max, Dc_min, C_max, C_min, R1_min, Da_max, WireDia_min) = fa.dimTable
    except ValueError:
        # Fallback to M10x1.5 baseline if CSV columns don't perfectly match
        P_csv = 1.5
        S_max, S_min = 10.0, 9.78
        K_max, K_min = 10.0, 9.78
        Kw_min = 5.28
        Dc_max, Dc_min = 16.27, 15.69
        C_max, C_min = 4.5, 4.13
        R1_min = 0.4
        Da_max = 11.2

    dia = self.getDia(fa.calc_diam, False)
    L   = float(fa.calc_len) if fa.calc_len else 50.0

    # Calculate nominal dimensions (averaging Max and Min)
    S  = (float(S_max)  + float(S_min))  / 2.0   
    K  = (float(K_max)  + float(K_min))  / 2.0   
    Kw = float(Kw_min)                     
    Dc = (float(Dc_max) + float(Dc_min)) / 2.0   
    C  = (float(C_max)  + float(C_min))  / 2.0   
    R1 = float(R1_min)                     

    # Pitch: prefer user-overridden value, fall back to CSV
    raw_pitch = getattr(fa, "calc_pitch", None)
    P = float(raw_pitch) if (raw_pitch and float(raw_pitch) > 0) else float(P_csv)

    # Effective shank diameter from threading module
    d_eff = _TM.get_shank_dia(fa, dia)
    tr    = d_eff / 2.0

    # Thread length
    raw_tlen = getattr(fa, "calc_thread_length", None) or 0.0
    b_default = 2.0 * dia + 12.0   # ISO approximation for metric bolts
    b = min(float(raw_tlen), L) if raw_tlen > 0.0 else min(b_default, L)

    # ── 2. Create the 12-point star head ──────────────────────────────────────
    r_hex = S / math.sqrt(3.0)  # Circumradius of each hexagon

    def _hex_prism(radius, height, rot_deg=0.0):
        pts = []
        for i in range(7):
            a = math.radians(i * 60.0 + rot_deg)
            pts.append(Base.Vector(radius * math.cos(a),
                                   radius * math.sin(a), 0.0))
        face = Part.Face(Part.Wire(Part.makePolygon(pts)))
        return face.extrude(Base.Vector(0, 0, height))

    # FIX: Extrude the star deeper (from Top K down to Flange Edge C) 
    # so the corners intersect the conical taper instead of floating.
    hex1 = _hex_prism(r_hex, K - C)
    hex2 = _hex_prism(r_hex, K - C, rot_deg=30.0)
    star = hex1.fuse(hex2)
    
    # Place the base of the star deep into the flange
    star.Placement.Base = Base.Vector(0, 0, C)

    # ── 3. Top contour chamfer envelope ───────────────────────────────────────
    chamfer_drop = (r_hex * 1.05 - S / 2.0) * math.tan(math.radians(30.0))
    env_pts = [
        Base.Vector(0,            0, K),
        Base.Vector(S / 2.0,      0, K),                         # Starts exactly at flats
        Base.Vector(r_hex * 1.05, 0, K - chamfer_drop),          # 30 deg drop
        Base.Vector(r_hex * 1.05, 0, C - 1.0),                   # Cut envelope goes all the way down
        Base.Vector(0,            0, C - 1.0),
        Base.Vector(0,            0, K),
    ]
    env_face = Part.Face(Part.Wire(Part.makePolygon(env_pts)))
    envelope  = env_face.revolve(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 360)
    
    # Apply chamfer to star
    head = star.common(envelope)

    # ── 4. Flange + shank profile (revolved) ──────────────────────────────────
    r1 = max(R1, 0.1)
    tl = b if (L - r1) > b else (L - r1)
    tip_cham = P  # tip entry chamfer depth = 1 pitch

    f = FSFaceMaker()
    
    # Flange top base (connecting center to the flats under the star)
    f.AddPoint(0, K - Kw)
    f.AddPoint(S / 2.0, K - Kw)
    
    # Flange inclined taper (from base of star down to flange edge C)
    f.AddPoint(Dc / 2.0, C)
    
    # Flange outer wall (vertical)
    f.AddPoint(Dc / 2.0, 0)
    
    # Bearing surface inward to fillet start
    f.AddPoint(tr + r1, 0)
    
    # Underhead fillet arc
    f.AddArc2(0.0, -r1, 90)
    
    # Shank cylinder (with optional unthreaded section)
    if (L - r1) > b and not getattr(fa, "Thread", False):
        f.AddPoint(tr, -(L - b))
        
    # Tip chamfer and bottom
    f.AddPoint(tr,                  -(L - tip_cham))
    f.AddPoint(tr - tip_cham * 0.5, -L)
    f.AddPoint(0,                   -L)

    flange_shank = self.RevolveZ(f.GetFace())

    # ── 5. Combine ────────────────────────────────────────────────────────────
    # The deeper star will now fuse into the tapered flange, closing the gap!
    shape = flange_shank.fuse(head)

    # ── 6. Thread cut ─────────────────────────────────────────────────────────
    if getattr(fa, "Thread", False):
        shape = _TM.cut_thread(shape, fa, d_eff, tl, -(L - tl), P)

    return shape