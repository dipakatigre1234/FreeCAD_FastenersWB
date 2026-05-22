# -*- coding: utf-8 -*-
"""
ASME B18.21.1 Helical Spring Lock Washers

- ASMEB18.21.1.1  (regular series,    Table 1)
- ASMEB18.21.1.2  (heavy series,      Table 2)
- ASMEB18.21.1.3  (extra duty series, Table 3)

Geometry:
  Trapezoidal cross-section (inner edge thicker than outer, 10% taper)
  swept along a single-turn helix.  A sector is cut to produce
  two clean separate flat gap faces.  Small fillets on the top face only
  at inner bore and outer rim edges.

CSV columns (A_max, A_min, B_max, T_min, W_min, BW_min):
  A_max / A_min  — bore diameter tolerance band
  B_max          — outer diameter (max)
  T_min          — mean section thickness = (t_inner + t_outer) / 2
"""

import math
import Part
from FreeCAD import Base
from screw_maker import *


def _build_filleted_section(X_in, X_out, Z_in_bot, Z_out_bot, Z_in_top, Z_out_top, Ri, Ro):
    """
    Constructs a 2D trapezoidal wire profile in the XZ plane with mathematically 
    exact circular arcs at the top-inner and top-outer corners. By filleting 
    the 2D sketch BEFORE the 3D sweep, we guarantee perfectly uniform roundness 
    along the entire helix without OpenCASCADE 3D fillet glitches.
    """
    # Top line slope and normal vector
    dx = X_out - X_in
    dz = Z_out_top - Z_in_top
    m = dz / dx
    L = math.hypot(dx, dz)
    
    # Normal vector pointing DOWN/LEFT into the solid shape
    Nd_x = dz / L
    Nd_z = -dx / L

    # --- Inner Fillet (Top-Left) ---
    C1x = X_in + Ri
    Ps1x = X_in + Nd_x * Ri
    Ps1z = Z_in_top + Nd_z * Ri
    C1z = Ps1z + m * (C1x - Ps1x)

    T1v = Base.Vector(X_in, 0.0, C1z)
    T1t = Base.Vector(C1x - Nd_x * Ri, 0.0, C1z - Nd_z * Ri)

    V_v1 = Base.Vector(-Ri, 0.0, 0.0)
    V_t1 = Base.Vector(-Nd_x * Ri, 0.0, -Nd_z * Ri)
    V_mid1 = V_v1 + V_t1
    L_mid1 = math.hypot(V_mid1.x, V_mid1.z)
    P_mid1 = Base.Vector(C1x + (V_mid1.x/L_mid1)*Ri, 0.0, C1z + (V_mid1.z/L_mid1)*Ri)

    arc_inner = Part.Arc(T1t, P_mid1, T1v).toShape()

    # --- Outer Fillet (Top-Right) ---
    C2x = X_out - Ro
    Ps2x = X_out + Nd_x * Ro
    Ps2z = Z_out_top + Nd_z * Ro
    C2z = Ps2z + m * (C2x - Ps2x)

    T2v = Base.Vector(X_out, 0.0, C2z)
    T2t = Base.Vector(C2x - Nd_x * Ro, 0.0, C2z - Nd_z * Ro)

    V_v2 = Base.Vector(Ro, 0.0, 0.0)
    V_t2 = Base.Vector(-Nd_x * Ro, 0.0, -Nd_z * Ro)
    V_mid2 = V_v2 + V_t2
    L_mid2 = math.hypot(V_mid2.x, V_mid2.z)
    P_mid2 = Base.Vector(C2x + (V_mid2.x/L_mid2)*Ro, 0.0, C2z + (V_mid2.z/L_mid2)*Ro)

    arc_outer = Part.Arc(T2v, P_mid2, T2t).toShape()

    # --- Assembly of Continuous Wire ---
    p_bot_in = Base.Vector(X_in, 0.0, Z_in_bot)
    p_bot_out = Base.Vector(X_out, 0.0, Z_out_bot)

    wire = Part.Wire([
        Part.LineSegment(p_bot_in, p_bot_out).toShape(), # Bottom flat
        Part.LineSegment(p_bot_out, T2v).toShape(),      # Outer vertical wall
        arc_outer,                                       # Outer top rounded corner
        Part.LineSegment(T2t, T1t).toShape(),            # Top inclined flat
        arc_inner,                                       # Inner top rounded corner
        Part.LineSegment(T1v, p_bot_in).toShape()        # Inner vertical wall
    ])
    
    return wire


def makeHelicalSpringWasher(self, fa):
    """Entry point called from ScrewMaker for ASMEB18.21.1.1 / .2 / .3 / .4."""
    if str(fa.baseType) == "ASMEB18.21.1.4":
        return _make_hicollar_washer(fa)
    return _make_helical_washer(fa)


def _make_helical_washer(fa):
    # ── Read CSV dimensions ───────────────────────────────────────────────
    t = fa.dimTable
    if len(t) < 4:
        raise ValueError(
            "Helical spring lock washer: need at least 4 CSV columns "
            "(A_max, A_min, B_max, T_min)"
        )
    A_max = t[0]
    A_min = t[1]
    B_max = t[2]
    T     = t[3]   # mean section thickness

    # ── Derived radii ─────────────────────────────────────────────────────
    A_mean  = (A_max + A_min) / 2.0
    r_bore  = A_mean / 2.0
    r_outer = B_max  / 2.0
    r_mean  = (r_bore + r_outer) / 2.0

    if r_outer <= r_bore + 0.05:
        raise ValueError("B_max must be larger than A_mean for a valid washer")

    # ── Cross-section thickness ───────────────────────────────────────────
    t_i = T / 0.95
    t_o = 0.9 * t_i
    
    # ── Build Pre-Filleted Cross-Section ──────────────────────────────────
    Ri = T * 0.08    # Inner fillet is larger
    Ro = T * 0.035   # Outer fillet is smaller
    
    section_wire = _build_filleted_section(r_bore, r_outer, 0.0, 0.0, t_i, t_o, Ri, Ro)

    # ── Full 360° helix, pitch = t_i ─────────────────────────────────────
    helix = Part.makeHelix(t_i, t_i, r_mean)

    # ── Sweep to solid ────────────────────────────────────────────────────
    washer = Part.Wire(helix).makePipeShell([section_wire], True, True)
    try:
        washer = washer.removeSplitter()
    except Exception:
        pass

    # ── Cut sector gap ────────────────────────────────────────────────────
    try:
        gap_deg = 2.0 
        r_cut   = r_outer * 1.5 + 5.0
        z_bot   = -t_i * 3.0
        z_top_c = t_i * 5.0

        rp1 = Base.Vector(0.0,   0.0, z_bot)
        rp2 = Base.Vector(r_cut, 0.0, z_bot)
        rp3 = Base.Vector(r_cut, 0.0, z_top_c)
        rp4 = Base.Vector(0.0,   0.0, z_top_c)

        rect_face = Part.Face(Part.Wire([
            Part.makeLine(rp1, rp2),
            Part.makeLine(rp2, rp3),
            Part.makeLine(rp3, rp4),
            Part.makeLine(rp4, rp1),
        ]))

        mat = Base.Matrix()
        mat.rotateZ(math.radians(-gap_deg / 2.0))
        rect_face = rect_face.transformGeometry(mat)

        gap_tool = rect_face.revolve(
            Base.Vector(0, 0, 0),
            Base.Vector(0, 0, 1),
            gap_deg
        )
        washer = washer.cut(gap_tool)
        washer = washer.removeSplitter()
    except Exception:
        pass

    return washer


# ─────────────────────────────────────────────────────────────────────────────
#  TYPE 4 — hi-collar, both faces inclined
# ─────────────────────────────────────────────────────────────────────────────

def _make_hicollar_washer(fa):
    """
    ASMEB18.21.1.4 hi-collar helical spring lock washer.
    """
    t = fa.dimTable
    if len(t) < 4:
        raise ValueError("ASMEB18.21.1.4: need at least 4 CSV columns")

    A_mean  = (t[0] + t[1]) / 2.0
    r_bore  = A_mean / 2.0
    r_outer = t[2]   / 2.0
    T       = t[3]          

    if r_outer <= r_bore + 0.05:
        raise ValueError("B_max must be larger than A_mean")

    T_outer = 0.90 * T      
    T_diff  = T - T_outer   
    half    = T_diff / 2.0  

    # ── Build Pre-Filleted Cross-Section ──────────────────────────────────
    Ri = T * 0.08    
    Ro = T * 0.035   
    
    # For hi-collar, bottom is inclined, top is inclined
    section_wire = _build_filleted_section(r_bore, r_outer, 0.0, half, T, T_outer + half, Ri, Ro)

    # Helix pitch = T 
    r_mean = (r_bore + r_outer) / 2.0
    helix  = Part.makeHelix(T, T, r_mean)

    washer = Part.Wire(helix).makePipeShell([section_wire], True, True)
    try:
        washer = washer.removeSplitter()
    except Exception:
        pass

    # ── Cut sector gap ────────────────────────────────────────────────────
    try:
        gap_deg = 2.0
        r_cut   = r_outer * 1.5 + 5.0
        z_bot   = -T * 3.0
        z_top_c = T * 5.0

        rp1 = Base.Vector(0.0,   0.0, z_bot)
        rp2 = Base.Vector(r_cut, 0.0, z_bot)
        rp3 = Base.Vector(r_cut, 0.0, z_top_c)
        rp4 = Base.Vector(0.0,   0.0, z_top_c)

        rect_face = Part.Face(Part.Wire([
            Part.makeLine(rp1, rp2),
            Part.makeLine(rp2, rp3),
            Part.makeLine(rp3, rp4),
            Part.makeLine(rp4, rp1),
        ]))
        mat = Base.Matrix()
        mat.rotateZ(math.radians(-gap_deg / 2.0))
        rect_face = rect_face.transformGeometry(mat)
        gap_tool = rect_face.revolve(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), gap_deg)
        washer = washer.cut(gap_tool)
        washer = washer.removeSplitter()
    except Exception:
        pass

    return washer