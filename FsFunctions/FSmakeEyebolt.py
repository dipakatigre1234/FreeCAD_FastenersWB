# -*- coding: utf-8 -*-
"""
***************************************************************************
*   FSmakeEyebolt.py                                                       *
*                                                                          *
*   ASME B18.15  Type 1 Plain Pattern (Straight Shank) Eyebolt             *
*     - ASMEB18.15.1A  Style A                                             *
*     - ASMEB18.15.1B  Style B                                             *
*                                                                          *
*   Shank geometry:                                                         *
*     Upper body  (L - G)  : diameter A from CSV  (forged body dia)        *
*     Threaded section (G) : diameter = nominal UNC thread OD (DiaList)    *
*     Short taper          : transition between the two diameters           *
*                                                                          *
*   Threading delegated to FSThreadingASME (ASME UN/UNR cut_thread).       *
***************************************************************************
"""
from screw_maker import *
import FSThreadingASME as _TA
import FSThreadingMetric as _TM


def makeEyebolt(self, fa):
    """Create a Type 1 Plain Pattern (straight shank) eyebolt.

    Geometry (ASME B18.15 Table 1):
      Eye    : elliptical torus (section E, inner C, outer width D).
      Shank  : two-diameter shaft
                 z = 0       … z = -(L-G)   →  body dia A  (CSV)
                 z = -(L-G)  … z = -L       →  thread dia  (DiaList)
               Short conical taper between the two sections.
      Tip    : small entry chamfer at z = -L.

    Threading: FSThreadingASME.cut_thread on the lower G section only,
               using the nominal UNC thread diameter so the helix profile
               sits on the correct outer surface.
    """
    SType = fa.baseType
    if SType not in ("ASMEB18.15.1A", "ASMEB18.15.1B"):
        raise NotImplementedError(f"Unknown eyebolt type: {SType}")

    # ── CSV dimensions ────────────────────────────────────────────────
    # Column order: TPI, A, B, C, D, E, F, G
    (TPI, A_in, B_in, C_in, D_in, E_in, F_in, G_in) = fa.dimTable

    inch = 25.4
    A    = float(A_in) * inch    # Forged body / shank OD  (mm)
    B    = float(B_in) * inch    # Shank length             (mm)
    C    = float(C_in) * inch    # Eye inner diameter       (mm)
    D    = float(D_in) * inch    # Eye outer width          (mm)
    E    = float(E_in) * inch    # Eye section diameter     (mm)
    G    = float(G_in) * inch    # Min full-thread length   (mm)

    L = B   # fixed by standard; EyeboltParameters has no Length dropdown

    # ── Nominal UNC thread diameter from DiaList ──────────────────────
    # fa.calc_diam = "1/4in", "1/2in", etc.
    # getDia returns the NOMINAL outer diameter, e.g. 6.35 mm for 1/4in.
    # This is the OD of the threaded section — distinct from A (body dia).
    d_thread = self.getDia(fa.calc_diam, False)   # mm, nominal thread OD

    # Lengths of each shank zone
    G_clamped  = min(G, L)                         # thread section
    body_len   = max(L - G_clamped, 0.0)           # upper body section

    # Taper height between body dia and thread dia (1 pitch, min 0.5 mm)
    try:
        tpi_csv = float(TPI)
    except (TypeError, ValueError):
        tpi_csv = 20.0
    P_mm      = 25.4 / tpi_csv
    taper_h   = max(P_mm, 0.5)
    # Shorten body_len to accommodate taper (only when there IS a body section)
    if body_len > taper_h:
        body_len -= taper_h
    else:
        taper_h = body_len
        body_len = 0.0

    # ─────────────────────────────────────────────────────────────────
    # 1. Eye (elliptical torus) shifted so bottom tangent is at z = 0
    # ─────────────────────────────────────────────────────────────────
    R_torus = (C + E) / 2.0
    r_minor = E / 2.0

    eye = Part.makeTorus(R_torus, r_minor)
    eye.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90),
    )
    scale_x = D / (C + 2.0 * E) if (C + 2.0 * E) > 0 else 1.0
    mat = FreeCAD.Matrix()
    mat.scale(scale_x, 1.0, 1.0)
    eye = eye.transformGeometry(mat)
    eye.translate(FreeCAD.Vector(0, 0, R_torus + r_minor))

    # ─────────────────────────────────────────────────────────────────
    # 2. Conical transition: eye section → shank body diameter A
    # ─────────────────────────────────────────────────────────────────
    cone_h = r_minor
    if cone_h > 1e-6 and abs(r_minor - A / 2.0) > 1e-6:
        neck_cone = Part.makeCone(A / 2.0, r_minor, cone_h)
        # base (r=A/2) at z=0, apex (r=r_minor) at z=+cone_h
    else:
        neck_cone = None

    # ─────────────────────────────────────────────────────────────────
    # 3a. Upper body cylinder  (diameter A, length body_len)
    #     z = 0  …  z = -body_len
    # ─────────────────────────────────────────────────────────────────
    parts = [eye]
    if neck_cone is not None:
        parts.append(neck_cone)

    if body_len > 1e-6:
        body_cyl = Part.makeCylinder(A / 2.0, body_len)
        body_cyl.translate(FreeCAD.Vector(0, 0, -body_len))
        parts.append(body_cyl)

    # ─────────────────────────────────────────────────────────────────
    # 3b. Taper from body dia A → thread dia d_thread
    #     z = -body_len  …  z = -(body_len + taper_h)
    # ─────────────────────────────────────────────────────────────────
    if taper_h > 1e-6 and abs(A - d_thread) > 1e-6:
        step_cone = Part.makeCone(d_thread / 2.0, A / 2.0, taper_h)
        step_cone.translate(FreeCAD.Vector(0, 0, -(body_len + taper_h)))
        parts.append(step_cone)

    # ─────────────────────────────────────────────────────────────────
    # 3c. Threaded section cylinder (diameter d_thread, length G_clamped)
    #     z = -(body_len + taper_h)  …  z = -L + chamfer_len
    # ─────────────────────────────────────────────────────────────────
    chamfer_len    = min(0.05 * inch, G_clamped * 0.15)
    thread_top_z   = -(body_len + taper_h)
    thread_cyl_len = G_clamped - chamfer_len
    if thread_cyl_len > 1e-6:
        thread_cyl = Part.makeCylinder(d_thread / 2.0, thread_cyl_len)
        thread_cyl.translate(FreeCAD.Vector(0, 0, thread_top_z - thread_cyl_len))
        parts.append(thread_cyl)

    # ─────────────────────────────────────────────────────────────────
    # 3d. Entry chamfer at shank tip
    # ─────────────────────────────────────────────────────────────────
    chamfer_r_tip = max(d_thread / 2.0 - chamfer_len, 0.1)
    tip = Part.makeCone(chamfer_r_tip, d_thread / 2.0, chamfer_len)
    tip.translate(FreeCAD.Vector(0, 0, -L))
    parts.append(tip)

    # ─────────────────────────────────────────────────────────────────
    # 4. Fuse all parts
    # ─────────────────────────────────────────────────────────────────
    solid = parts[0]
    for p in parts[1:]:
        solid = solid.fuse(p)
    solid = solid.removeSplitter()

    # ─────────────────────────────────────────────────────────────────
    # 5. ASME UN/UNR threading on the lower G section
    #
    #    d_eff via get_shank_dia(fa, d_thread) — uses the THREAD nominal
    #    diameter (not A) so the cutter OD matches the threaded cylinder.
    #    offset_z positions the cutter at the start of the thread zone.
    # ─────────────────────────────────────────────────────────────────
    if getattr(fa, "Thread", False):
        d_eff    = _TA.get_shank_dia(fa, d_thread)
        tl       = G_clamped
        offset_z = thread_top_z          # z where thread zone begins (negative)
        solid    = _TA.cut_thread(solid, fa, d_eff, tl, offset_z, P_mm)

    return Part.Solid(solid)


# ═══════════════════════════════════════════════════════════════════════════
#  Type 2 — Shoulder Pattern Eyebolt  (ASMEB18.15.2A / ASMEB18.15.2B)
# ═══════════════════════════════════════════════════════════════════════════

def makeEyeboltShoulder(self, fa):
    """Create a Type 2 Shoulder Pattern (straight shank) eyebolt.

    Geometry matches the ASME B18.15 macro exactly:
      Eye      : analytical torus centred at z = J, upright in XZ plane
      Shoulder : cylinder dia K, height L (= Ls from CSV), at z = 0
      Neck     : solid loft from circular wire at shoulder top → stadium
                 wire embedded in the torus body
      Fillet   : quarter-torus ring under the shoulder at z = 0
      Shank    : uniform dia A, z = 0 … z = -B (with entry chamfer at tip)

    Coordinate origin: bottom bearing face of the shoulder.
    Shank extends downward (−Z) to z = −B.
    Threading (optional) cuts the lower G section of the shank.
    """
    SType = fa.baseType
    if SType not in ("ASMEB18.15.2A", "ASMEB18.15.2B"):
        raise NotImplementedError(f"Unknown shoulder eyebolt type: {SType}")

    # CSV column order: TPI, A, B, C, D, E, G, J, K, Ls, R
    (TPI, A_in, B_in, C_in, D_in, E_in, G_in,
     J_in, K_in, Ls_in, R_in) = fa.dimTable

    inch     = 25.4
    A        = float(A_in)  * inch   # Forged body / shank OD       (mm)
    B        = float(B_in)  * inch   # Shank length tip→shoulder    (mm)
    C        = float(C_in)  * inch   # Eye inner diameter            (mm)
    E        = float(E_in)  * inch   # Eye material thickness        (mm)
    G        = float(G_in)  * inch   # Min full-thread length        (mm)
    J        = float(J_in)  * inch   # Eye centreline to shoulder    (mm)
    K        = float(K_in)  * inch   # Shoulder diameter             (mm)
    L        = float(Ls_in) * inch   # Shoulder height (Ls in CSV)  (mm)
    R_fillet = float(R_in)  * inch   # Fillet radius under shoulder  (mm)

    # Nominal UNC thread OD — distinct from A (forged body dia).
    # e.g. 6.35 mm for 1/4in, so thread cuts land on the correct surface.
    d_thread = self.getDia(fa.calc_diam, False)

    try:
        tpi_csv = float(TPI)
    except (TypeError, ValueError):
        tpi_csv = 20.0
    P_mm = 25.4 / tpi_csv

    # Shank zone lengths (same split logic as Type 1)
    chamfer_len   = 0.05 * inch          # Entry chamfer at shank tip
    G_clamped     = min(G, B)            # Thread section length
    body_len      = max(B - G_clamped, 0.0)
    taper_h       = max(P_mm, 0.5)       # Taper between body dia→thread dia
    if body_len > taper_h:
        body_len -= taper_h
    else:
        taper_h  = body_len
        body_len = 0.0
    thread_top_z  = -(body_len + taper_h)   # z where thread zone begins

    R_torus = (C + E) / 2.0
    r_minor = E / 2.0

    # ─────────────────────────────────────────────────────────────────
    # 1. Eye (analytical torus) — centred at z = J, upright
    # ─────────────────────────────────────────────────────────────────
    torus = Part.makeTorus(R_torus, r_minor)
    torus.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, J),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90),
    )

    # ─────────────────────────────────────────────────────────────────
    # 2. Shoulder cylinder  z = 0 … z = L
    # ─────────────────────────────────────────────────────────────────
    shoulder = Part.makeCylinder(K / 2.0, L)
    shoulder.translate(FreeCAD.Vector(0, 0, 0))

    # ─────────────────────────────────────────────────────────────────
    # 3. Neck loft — circular base at shoulder top → stadium top
    #    embedded in the torus body (matches macro geometry exactly)
    # ─────────────────────────────────────────────────────────────────
    def make_arc_3p(p_start, p_mid, p_end):
        return Part.Arc(p_start, p_mid, p_end).toShape()

    # Base wire at z = L: 4-arc circle at 85 % of shoulder radius
    R_b = (K / 2.0) * 0.85
    c   = R_b * 0.707106
    arc1_base = make_arc_3p(FreeCAD.Vector( c,  c, L), FreeCAD.Vector( 0,  R_b, L), FreeCAD.Vector(-c,  c, L))
    arc2_base = make_arc_3p(FreeCAD.Vector(-c,  c, L), FreeCAD.Vector(-R_b,  0, L), FreeCAD.Vector(-c, -c, L))
    arc3_base = make_arc_3p(FreeCAD.Vector(-c, -c, L), FreeCAD.Vector( 0, -R_b, L), FreeCAD.Vector( c, -c, L))
    arc4_base = make_arc_3p(FreeCAD.Vector( c, -c, L), FreeCAD.Vector( R_b,  0, L), FreeCAD.Vector( c,  c, L))
    w1 = Part.Wire([arc1_base, arc2_base, arc3_base, arc4_base])

    # Top wire: stadium (discorectangle) embedded in the torus ring
    W_top = K * 1.15
    D_top = E * 0.75
    # Z_t scales proportionally with J so the wire embeds into the
    # torus at every bolt size (matches 0.5" for the 1/2" reference size)
    Z_t   = J * 0.35
    r_t   = D_top / 2.0
    l_t   = W_top - D_top
    edge1_top = Part.makeLine(FreeCAD.Vector( l_t/2,  r_t, Z_t), FreeCAD.Vector(-l_t/2,  r_t, Z_t))
    arc2_top  = make_arc_3p(FreeCAD.Vector(-l_t/2,  r_t, Z_t), FreeCAD.Vector(-l_t/2 - r_t, 0, Z_t), FreeCAD.Vector(-l_t/2, -r_t, Z_t))
    edge3_top = Part.makeLine(FreeCAD.Vector(-l_t/2, -r_t, Z_t), FreeCAD.Vector( l_t/2, -r_t, Z_t))
    arc4_top  = make_arc_3p(FreeCAD.Vector( l_t/2, -r_t, Z_t), FreeCAD.Vector( l_t/2 + r_t, 0, Z_t), FreeCAD.Vector( l_t/2,  r_t, Z_t))
    w2 = Part.Wire([edge1_top, arc2_top, edge3_top, arc4_top])
    neck = Part.makeLoft([w1, w2], True, False)

    # ─────────────────────────────────────────────────────────────────
    # 4a. Upper body cylinder (dia A)  z = 0 … z = -body_len
    # ─────────────────────────────────────────────────────────────────
    shank_parts = []
    if body_len > 1e-6:
        body_cyl = Part.makeCylinder(A / 2.0, body_len)
        body_cyl.translate(FreeCAD.Vector(0, 0, -body_len))
        shank_parts.append(body_cyl)

    # ─────────────────────────────────────────────────────────────────
    # 4b. Taper body dia A → thread dia d_thread
    # ─────────────────────────────────────────────────────────────────
    if taper_h > 1e-6 and abs(A - d_thread) > 1e-6:
        step_cone = Part.makeCone(d_thread / 2.0, A / 2.0, taper_h)
        step_cone.translate(FreeCAD.Vector(0, 0, -(body_len + taper_h)))
        shank_parts.append(step_cone)

    # ─────────────────────────────────────────────────────────────────
    # 4c. Thread section cylinder (dia d_thread)
    # ─────────────────────────────────────────────────────────────────
    thread_cyl_len = G_clamped - chamfer_len
    if thread_cyl_len > 1e-6:
        thread_cyl = Part.makeCylinder(d_thread / 2.0, thread_cyl_len)
        thread_cyl.translate(FreeCAD.Vector(0, 0, thread_top_z - thread_cyl_len))
        shank_parts.append(thread_cyl)

    # ─────────────────────────────────────────────────────────────────
    # 4d. Entry chamfer at shank tip (based on thread dia)
    # ─────────────────────────────────────────────────────────────────
    chamfer_r1 = max(d_thread / 2.0 - chamfer_len, 0.1)
    entry_chamfer = Part.makeCone(chamfer_r1, d_thread / 2.0, chamfer_len)
    entry_chamfer.translate(FreeCAD.Vector(0, 0, -B))
    shank_parts.append(entry_chamfer)

    # ─────────────────────────────────────────────────────────────────
    # 5. Fillet ring under shoulder (quarter-torus cut from cylinder)
    #    Uses body dia A — this is the forged transition at z = 0.
    #    z = -R_fillet … z = 0
    # ─────────────────────────────────────────────────────────────────
    f_cyl   = Part.makeCylinder(A / 2.0 + R_fillet, R_fillet)
    f_cyl.translate(FreeCAD.Vector(0, 0, -R_fillet))
    f_torus = Part.makeTorus(A / 2.0 + R_fillet, R_fillet)
    f_torus.translate(FreeCAD.Vector(0, 0, -R_fillet))
    fillet_ring = f_cyl.cut(f_torus)

    # ─────────────────────────────────────────────────────────────────
    # 6. Step-by-step assembly
    # ─────────────────────────────────────────────────────────────────
    # Fuse all shank parts into one solid first
    shank_solid = shank_parts[0]
    for sp in shank_parts[1:]:
        shank_solid = shank_solid.fuse(sp)

    part1      = shoulder.fuse(shank_solid)
    part2      = part1.fuse(fillet_ring)
    part3      = part2.fuse(neck)
    base_shape = torus.fuse(part3)
    base_shape = base_shape.removeSplitter()

    # ─────────────────────────────────────────────────────────────────
    # 8. Assign final solid (no makeFillet — OCCT's fillet algorithm
    #    can SIGSEGV on complex multi-fuse edge topology; try/except
    #    cannot catch a C++ crash.  The sub-1 mm cosmetic fillets are
    #    omitted here; all structural geometry is intact.)
    # ─────────────────────────────────────────────────────────────────
    eyebolt_solid = base_shape

    # ─────────────────────────────────────────────────────────────────
    # 9. ASME threading on the lower G section (thread dia d_thread)
    # ─────────────────────────────────────────────────────────────────
    if getattr(fa, "Thread", False):
        d_eff = _TA.get_shank_dia(fa, d_thread)
        eyebolt_solid = _TA.cut_thread(
            eyebolt_solid, fa, d_eff, G_clamped, thread_top_z, P_mm
        )

    return Part.Solid(eyebolt_solid)


# ═══════════════════════════════════════════════════════════════════════════
#  DIN 580 — Lifting Eye Bolt (metric, forged)
#
#  Geometry is a 1:1 port of din_580_eyebolt.FCMacro.  Every M6-specific
#  constant in that macro is replaced by a value pulled from FsData via
#  fa.dimTable; values that the standard gives as max/min pairs are stored in
#  the CSV pre-averaged (mean = (max + min) / 2), so the columns read here are
#  already the mean values.
#
#  CSV  DIN580def.csv  column order (fa.dimTable):
#      d1, d2, d3, d4, e, f, dg, h, k, l, m, r1, r2, r3
#  where
#      d1 : thread nominal diameter            (M6 -> 6)
#      d2 : shoulder (collar) base diameter
#      d3 : eye outer diameter
#      d4 : eye inner diameter (the hole)
#      e  : shoulder height at the outer edge
#      f  : height of the thread undercut groove
#      dg : undercut groove / shank-tip diameter
#      h  : total height (axis tip-to-top reference)
#      k  : eye cross-section thickness, min side (near shoulder)
#      l  : shank length
#      m  : eye cross-section thickness, max side (top of eye)
#      r1 : saddle fillet radius (eye-to-shoulder blend)
#      r2 : undercut relief cut radius
#      r3 : undercut groove-floor fillet radius
# ═══════════════════════════════════════════════════════════════════════════

def _fillet_with_backoff(shape, edges, radius, label=""):
    """makeFillet that never raises and never asks for more than the geometry
    can give.

    OCCT returns ``StdFail_NotDone`` whenever the requested radius is larger
    than an adjacent face/edge can accommodate.  The DIN 580 standard radii
    (r1, r3) are full forged-transition radii and are frequently bigger than
    the small local steps the macro geometry actually offers, so we step the
    radius down until OCCT accepts it (or give up and return the input shape
    untouched — the fillet is cosmetic).
    """
    if not edges or radius is None or radius <= 1e-4:
        return shape
    for factor in (1.0, 0.75, 0.5, 0.35, 0.22, 0.12):
        r = radius * factor
        if r < 1e-3:
            break
        try:
            return shape.makeFillet(r, edges)
        except Exception:
            continue
    if label:
        FreeCAD.Console.PrintWarning(
            f"DIN580 {label} fillet skipped (geometry too tight)\n"
        )
    return shape


def makeDIN580Eyebolt(self, fa):
    """Create a DIN 580 forged lifting eye bolt.

    Coordinate origin (matches the macro):
      z = 0      bottom bearing face of the shoulder collar
      z > 0      shoulder, then the anti-twist forged eye
      z < 0      threaded shank, down to the tip at z = -l

    The eye is a closed B-spline loft with a variable cross-section
    (thickness sweeps k -> m), giving the characteristic forged ring.
    Optional ISO metric threading is cut on the straight shank below the
    undercut groove via FSThreadingMetric.cut_thread.
    """
    SType = fa.baseType
    if SType != "DIN580":
        raise NotImplementedError(f"Unknown eyebolt type: {SType}")
    if fa.dimTable is None:
        raise ValueError("DIN580 eye bolt requires a standard diameter")

    # ── CSV dimensions (already mean values) ──────────────────────────────
    (d1, d2, d3, d4, e, f, dg, h, k, l, m, r1, r2, r3) = (
        float(v) for v in fa.dimTable
    )

    # Effective (deviated) shank diameter — keeps the thread crest flush with
    # the shank surface, exactly as every other metric FsMake file does.
    # Falls back to the nominal d1 when no pitch/class is resolvable.
    d_shank = _TM.get_shank_dia(fa, d1)

    g               = dg     # undercut groove small diameter  (macro: g)
    chamfer_tip_dia = dg     # tip diameter after the 45° entry chamfer

    # 12° forging draft on the shoulder collar
    rad_draft  = math.radians(12.0)
    side_inset = e * math.tan(rad_draft)
    top_rise   = ((d2 / 2.0) - side_inset) * math.tan(rad_draft)

    cut_angle_rad     = math.radians(30.0)
    chamfer_angle_rad = math.radians(45.0)
    # axial length consumed by the 45° entry chamfer
    chamfer_axial = ((d_shank - chamfer_tip_dia) / 2.0) / math.tan(chamfer_angle_rad)

    # ─────────────────────────────────────────────────────────────────────
    # 1. Revolved base: shank (with undercut + entry chamfer) + shoulder
    # ─────────────────────────────────────────────────────────────────────
    def make_revolve_profile_clean():
        p_tip_axis  = FreeCAD.Vector(0,                   0, -l)
        p_tip_edge  = FreeCAD.Vector(chamfer_tip_dia / 2.0, 0, -l)
        p_chamf_top = FreeCAD.Vector(d_shank / 2.0,       0, -l + chamfer_axial)

        p2 = FreeCAD.Vector(d_shank / 2.0, 0, -f)
        p3 = FreeCAD.Vector(g / 2.0,       0, -f)
        p4 = FreeCAD.Vector(g / 2.0,       0, 0)        # top of groove, bottom-face plane
        p6 = FreeCAD.Vector(d2 / 2.0,      0, 0)        # flat bottom annular face
        p7 = FreeCAD.Vector((d2 / 2.0) - side_inset, 0, e)
        p8 = FreeCAD.Vector(0,             0, e + top_rise)

        edges = [
            Part.makeLine(p_tip_axis,  p_tip_edge),     # flat truncated tip face
            Part.makeLine(p_tip_edge,  p_chamf_top),    # 45° entry chamfer
            Part.makeLine(p_chamf_top, p2),             # full shank up to undercut
            Part.makeLine(p2, p3),
            Part.makeLine(p3, p4),
            Part.makeLine(p4, p6),                      # flat bottom annular face
            Part.makeLine(p6, p7),
            Part.makeLine(p7, p8),
            Part.makeLine(p8, p_tip_axis),              # close along axis
        ]
        return Part.Face(Part.Wire(edges)).revolve(
            FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360
        )

    base_solid = make_revolve_profile_clean()

    # R3 fillet on the inner concave groove-floor edge (low-risk: simple revolve).
    # The concave corner sits between the groove floor (radial width
    # (d_shank - g)/2) and the groove wall (height f); the fillet cannot exceed
    # the smaller of those, so clamp before applying.
    r3_edges = []
    for edge in base_solid.Edges:
        bbox = edge.BoundBox
        if abs(bbox.ZMax - (-f)) > 0.01 or abs(bbox.ZMin - (-f)) > 0.01:
            continue
        edge_radius = bbox.XMax
        if abs(edge_radius - g / 2.0) < 0.1 and edge_radius < d_shank / 2.0 - 0.1:
            r3_edges.append(edge)
    r3_safe = min(r3, 0.8 * min((d_shank - g) / 2.0, f))
    base_solid = _fillet_with_backoff(base_solid, r3_edges, r3_safe, "R3")

    # ─────────────────────────────────────────────────────────────────────
    # 2. Anti-twist forged eye — closed B-spline loft, thickness sweeps k->m
    # ─────────────────────────────────────────────────────────────────────
    spine_r  = (d3 + d4) / 4.0
    spine_z  = h - (d3 / 2.0)
    radial_w = (d3 - d4) / 2.0

    wires = []
    for deg in range(0, 360, 10):
        alpha     = math.radians(deg)
        thickness = k + (m - k) * (1 - math.cos(alpha)) / 2.0
        r_axial   = thickness / 2.0
        r_radial  = radial_w / 2.0

        cx     = spine_r * math.sin(alpha)
        cz     = spine_z + spine_r * math.cos(alpha)
        center = FreeCAD.Vector(cx, 0, cz)

        radial_dir = FreeCAD.Vector(math.sin(alpha), 0, math.cos(alpha))
        axial_dir  = FreeCAD.Vector(0, 1, 0)

        points = []
        for i in range(16):
            theta = math.radians(i * 360.0 / 16.0)
            lx    = r_radial * math.cos(theta)
            ly    = r_axial * math.sin(theta)
            points.append(center + (radial_dir * lx) + (axial_dir * ly))

        spline = Part.BSplineCurve()
        spline.interpolate(points, True)
        wires.append(Part.Wire(spline.toShape()))

    eye_solid = Part.makeLoft(wires, True, False, True)

    # ─────────────────────────────────────────────────────────────────────
    # 3. Fuse base + eye
    # ─────────────────────────────────────────────────────────────────────
    fused = base_solid.fuse(eye_solid).removeSplitter()

    # ─────────────────────────────────────────────────────────────────────
    # 4. R2 + 30° relief cut around the undercut, applied after the fuse
    # ─────────────────────────────────────────────────────────────────────
    def make_cut_tool():
        p_start  = FreeCAD.Vector(g / 2.0, 0, 0)
        arc_peak = FreeCAD.Vector(g / 2.0 + r2, 0, r2)
        arc_mid  = FreeCAD.Vector(
            g / 2.0 + r2 - r2 * math.cos(math.radians(45)),
            0,
            r2 * math.sin(math.radians(45)),
        )
        dx    = r2 / math.tan(cut_angle_rad)
        p_end = FreeCAD.Vector(g / 2.0 + r2 + dx, 0, 0)
        edges = [
            Part.Edge(Part.Arc(p_start, arc_mid, arc_peak)),
            Part.makeLine(arc_peak, p_end),
            Part.makeLine(p_end, p_start),
        ]
        face = Part.Face(Part.Wire(edges))
        return face.revolve(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360)

    try:
        final_solid = fused.cut(make_cut_tool()).removeSplitter()
    except Exception as ex:
        FreeCAD.Console.PrintWarning(f"DIN580 R2 cut skipped: {ex}\n")
        final_solid = fused

    # ─────────────────────────────────────────────────────────────────────
    # 5. R1 saddle fillet (eye-to-shoulder blend). Thresholds scaled by size
    #    so the same saddle edges are picked at every diameter. Best-effort:
    #    OCCT's fillet can fail on complex fused topology (see the shoulder
    #    eyebolt note above), so it is skipped on error rather than relied on.
    # ─────────────────────────────────────────────────────────────────────
    r1_edges = []
    for edge in final_solid.Edges:
        bbox = edge.BoundBox
        if bbox.ZMin > e * 0.08 and bbox.ZMax < (e + r1 + m):
            if (bbox.XMax - bbox.XMin) > d4 * 0.25 or (bbox.YMax - bbox.YMin) > d4 * 0.25:
                r1_edges.append(edge)
    # The standard r1 is the full forged saddle radius and is usually larger
    # than the room between the eye arms and the shoulder top; clamp it to the
    # local shoulder height / eye thickness, then back off if OCCT still balks.
    r1_safe = min(r1, 0.6 * min(e, k))
    final_solid = _fillet_with_backoff(final_solid, r1_edges, r1_safe, "R1")

    # ─────────────────────────────────────────────────────────────────────
    # 6. Optional ISO metric threading on the straight shank below the groove
    # ─────────────────────────────────────────────────────────────────────
    if getattr(fa, "Thread", False):
        P = _TM.resolve_metric_pitch(fa)
        tl = max(l - f, 0.0)
        if P and P > 0 and tl > 1e-6:
            final_solid = _TM.cut_thread(final_solid, fa, d1, tl, -f, P)

    try:
        return Part.Solid(final_solid)
    except Exception:
        return final_solid


# ═══════════════════════════════════════════════════════════════════════════
#  ISO 3266 — Forged Lifting Eye Bolt (metric)
#
#  Geometry is a 1:1 port of the ISO 3266 master macro.  The M10-specific
#  constants in that macro are replaced by values pulled from FsData via
#  fa.dimTable.  None of the ISO 3266 dimensions are given as max/min pairs
#  (E = min, F = max, r = min, B = min, H and s are exact), so the CSV columns
#  are used directly — no averaging needed.
#
#  CSV  ISO3266def.csv  column order (fa.dimTable):
#      d, E, H, F, r, B, s
#  where
#      d : nominal thread diameter
#      E : internal diameter of the eye
#      H : height from underside of collar to end of shank
#      F : diameter of the eye cross-section
#      r : radius of grooves and fillets
#      B : diameter of the collar (also the dome / saddle reference)
#      s : distance from collar to first thread
#
#  dg (shank diameter at the undercut) is not tabulated by the standard; it is
#  derived as d - 2r, which reproduces the macro's M10 value (8 = 10 - 2·1).
# ═══════════════════════════════════════════════════════════════════════════

def makeISO3266Eyebolt(self, fa):
    """Create an ISO 3266 forged lifting eye bolt.

    Coordinate origin (matches the macro):
      z = 0      underside of the collar (bearing face)
      z > 0      collar cylinder, hemispherical dome, then the circular eye
      z < 0      threaded shank, down to the tip at z = -H

    The eye is a plain torus fused into the dome; a semicircular relief groove
    is cut at the collar base and an adaptive saddle fillet blends the dome
    into the eye.  Optional ISO metric threading is cut on the shank below the
    collar-to-first-thread distance s.
    """
    SType = fa.baseType
    if SType != "ISO3266":
        raise NotImplementedError(f"Unknown eyebolt type: {SType}")
    if fa.dimTable is None:
        raise ValueError("ISO3266 eye bolt requires a standard diameter")

    # ── CSV dimensions (used directly — no max/min pairs in this standard) ──
    (d, E, H, F, r, B, s) = (float(v) for v in fa.dimTable)

    # Effective (deviated) thread/shank diameter — keeps the thread crest flush
    # with the shank surface (same convention as every metric FsMake file).
    thread_dia = _TM.get_shank_dia(fa, d)

    dg = d - 2.0 * r                # shank diameter at undercut (macro: d - 2r)

    e     = (B - d) / 2.0           # collar cylindrical height
    Z_eye = e + (E / 2.0 + 0.1) + (B / 2.0) - 0.5
    r1    = B / 2.0                 # target outer saddle fillet radius

    chamfer_angle_rad = math.radians(45.0)
    chamfer_tip_dia   = thread_dia - 1.5
    chamfer_axial     = ((thread_dia - chamfer_tip_dia) / 2.0) / math.tan(chamfer_angle_rad)

    # ─────────────────────────────────────────────────────────────────────
    # 1. Revolved base: shank + thread-to-shank fillet + collar + dome
    # ─────────────────────────────────────────────────────────────────────
    def make_iso_base():
        p_tip_axis   = FreeCAD.Vector(0,                     0, -H)
        p_tip_edge   = FreeCAD.Vector(chamfer_tip_dia / 2.0, 0, -H)
        p_chamf_top  = FreeCAD.Vector(thread_dia / 2.0,      0, -H + chamfer_axial)
        p_thread_top = FreeCAD.Vector(thread_dia / 2.0,      0, -s)

        # Concave fillet between thread (thread_dia) and shank neck (dg).
        # Clamp to 99% of the step so there is no zero-length connector line.
        step_width     = (thread_dia - dg) / 2.0
        actual_inner_r = min(r, step_width * 0.99)

        p_fillet_start = FreeCAD.Vector(dg / 2.0 + actual_inner_r, 0, -s)
        p_fillet_end   = FreeCAD.Vector(dg / 2.0,                  0, -s + actual_inner_r)
        arc_center_x   = dg / 2.0 + actual_inner_r
        arc_center_z   = -s + actual_inner_r
        p_fillet_mid   = FreeCAD.Vector(
            arc_center_x - actual_inner_r * math.cos(math.radians(45)),
            0,
            arc_center_z - actual_inner_r * math.sin(math.radians(45)),
        )

        p_collar_inner_sharp = FreeCAD.Vector(dg / 2.0, 0, 0)
        p_collar_outer       = FreeCAD.Vector(B / 2.0,  0, 0)
        p_collar_top         = FreeCAD.Vector(B / 2.0,  0, e)
        p_dome_top           = FreeCAD.Vector(0,        0, e + B / 2.0)

        edges = [
            Part.makeLine(p_tip_axis,  p_tip_edge),
            Part.makeLine(p_tip_edge,  p_chamf_top),
            Part.makeLine(p_chamf_top, p_thread_top),
        ]
        # Tiny horizontal line if there is leftover space before the fillet
        if p_thread_top.x > (p_fillet_start.x + 0.001):
            edges.append(Part.makeLine(p_thread_top, p_fillet_start))
        edges.append(Part.Edge(Part.Arc(p_fillet_start, p_fillet_mid, p_fillet_end)))
        edges.append(Part.makeLine(p_fillet_end, p_collar_inner_sharp))
        edges.append(Part.makeLine(p_collar_inner_sharp, p_collar_outer))
        edges.append(Part.makeLine(p_collar_outer, p_collar_top))
        dome_mid = FreeCAD.Vector(
            (B / 2.0) * math.cos(math.radians(45)),
            0,
            e + (B / 2.0) * math.sin(math.radians(45)),
        )
        edges.append(Part.Edge(Part.Arc(p_collar_top, dome_mid, p_dome_top)))
        edges.append(Part.makeLine(p_dome_top, p_tip_axis))

        return Part.Face(Part.Wire(edges)).revolve(
            FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360
        )

    base_solid = make_iso_base()

    # ─────────────────────────────────────────────────────────────────────
    # 2. Circular eye (torus) fused into the dome
    # ─────────────────────────────────────────────────────────────────────
    R_major   = (E / 2.0) + (F / 2.0)
    R_minor   = F / 2.0
    eye_torus = Part.makeTorus(R_major, R_minor)
    eye_torus.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, Z_eye),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90),
    )

    fused_solid = base_solid.fuse(eye_torus).removeSplitter()

    # ─────────────────────────────────────────────────────────────────────
    # 3. Semicircular relief groove cut at the collar base
    # ─────────────────────────────────────────────────────────────────────
    def make_cut_tool():
        p_start  = FreeCAD.Vector(dg / 2.0,         0, 0)
        arc_peak = FreeCAD.Vector(dg / 2.0 + r,     0, r)
        p_end    = FreeCAD.Vector(dg / 2.0 + 2 * r, 0, 0)
        edges = [
            Part.Edge(Part.Arc(p_start, arc_peak, p_end)),
            Part.makeLine(p_end, p_start),
        ]
        return Part.Face(Part.Wire(edges)).revolve(
            FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 360
        )

    try:
        final_solid = fused_solid.cut(make_cut_tool()).removeSplitter()
    except Exception as ex:
        FreeCAD.Console.PrintWarning(f"ISO3266 groove cut skipped: {ex}\n")
        final_solid = fused_solid

    # ─────────────────────────────────────────────────────────────────────
    # 4. Adaptive saddle fillet (outer dome-to-eye intersection)
    # ─────────────────────────────────────────────────────────────────────
    dome_top_z = e + B / 2.0
    r1_edges = []
    for edge in final_solid.Edges:
        cz   = edge.CenterOfMass.z
        bbox = edge.BoundBox
        if (e + 0.1) < cz < (dome_top_z + 0.1):
            if (bbox.XMax - bbox.XMin) > (E / 2.0) or (bbox.YMax - bbox.YMin) > (E / 2.0):
                r1_edges.append(edge)
    final_solid = _fillet_with_backoff(final_solid, r1_edges, r1, "saddle")

    # ─────────────────────────────────────────────────────────────────────
    # 5. Optional ISO metric threading on the shank below distance s
    # ─────────────────────────────────────────────────────────────────────
    if getattr(fa, "Thread", False):
        P = _TM.resolve_metric_pitch(fa)
        tl = max(H - s, 0.0)
        if P and P > 0 and tl > 1e-6:
            final_solid = _TM.cut_thread(final_solid, fa, d, tl, -s, P)

    try:
        return Part.Solid(final_solid)
    except Exception:
        return final_solid
