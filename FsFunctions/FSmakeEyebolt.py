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
