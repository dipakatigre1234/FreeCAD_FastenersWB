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
