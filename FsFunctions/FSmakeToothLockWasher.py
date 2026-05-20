# -*- coding: utf-8 -*-
"""
ASME B18.21.1 Tooth Lock Washers
- ASMEB18.21.1.6A / 6B (internal tooth lock washer)
- ASMEB18.21.1.7A / 7B (heavy internal tooth lock washer)
- ASMEB18.21.1.8A / 8B (external tooth lock washer, flat)
- ASMEB18.21.1.9A / 9B (external tooth lock washer, conical / countersunk)

Type 9 construction (parallel-walled rectangular teeth):

  Step 1.  Build the cone body as a single revolved solid with cross-section
           shaped like a TRUE RHOMBUS in the r-z half-plane.  All four edges
           are either along the cone slope (top/bottom faces) or perpendicular
           to it (inner/outer end faces, both with length h_perp = CSV
           thickness).  This guarantees that no matter which face you measure
           the wall thickness on, you get the CSV value.

  Step 2.  Build a "removal solid" representing all outer-region material
           that should NOT be in the final washer:
             - Start with an OUTER-ANNULUS solid whose cross-section is a
               RHOMBUS matching the cone body's slope (parallel sides
               tilted at cone slope, end sides perpendicular to slope).
               When revolved, this gives an annulus whose inner end face
               is a TILTED DISK perpendicular to the cone slope direction.
             - Subtract n rectangular tooth boxes with parallel side walls
               at y = ±tooth_w/2.  The tooth boxes are made longer at the
               inner end (start at r_root - ox_ann instead of r_root) so
               they fully cover the annulus's tilted inner-edge band.
           The remaining solid is the inter-tooth material to be removed.

  Step 3.  Cut the removal solid from the cone body.  The teeth that
           survive have:
             - Parallel chord-line side walls → equal width root-to-tip
             - Top/bottom faces inherited from the cone body's slope
             - Inner end merges seamlessly into the inner conical ring
               (no triangular gap artifacts at the tooth-root junction)
           Between teeth, the gap back-wall is a TILTED DISK perpendicular
           to the cone slope — visually parallel to the cone slope.

  Step 4.  The outer-bottom corner of the rhombus is at z = 0, so the
           washer rim rests on a flat reference plane (z=0 is the bottom
           contact plane).

User-configurable parameters (FreeCAD model properties):
  ToothCount       — number of teeth (int)
  ToothTwistAngle  — twist angle in degrees at the free tip (Type 8 only)
  ToothWidth       — circumferential tooth width override in mm (else auto)
"""

import math
from screw_maker import *


def makeToothLockWasher(self, fa):
    """Single entry point for all tooth lock washers (internal and external)."""
    bt = str(fa.baseType)
    if bt.startswith("ASMEB18.21.1.8") or bt.startswith("ASMEB18.21.1.9"):
        return makeExternalToothLockWasher(self, fa)
    return makeInternalToothLockWasher(self, fa)


# ─────────────────────────────────────────────────────────────────────────────
#  SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _read_dims(fa):
    """Return (d1, d2, h) means from CSV; handles 3-col, 6-col, and 8-col formats."""
    t = fa.dimTable
    if len(t) >= 6:
        d1 = (t[0] + t[1]) / 2.0
        d2 = (t[2] + t[3]) / 2.0
        h  = (t[4] + t[5]) / 2.0
    else:
        d1, d2, h = t[0], t[1], t[2]
    return d1, d2, h


def _read_tooth_length(fa, r_inner, r_outer, default_tooth_frac):
    """
    Return (r_root, tooth_len, ring_len) given a user-supplied ToothLength.

    r_inner           — bore/wall radius (inner edge of the full radial span)
    r_outer           — outer tip radius
    default_tooth_frac — fraction of total span used as tooth length when
                         ToothLength is 0 or absent (e.g. 0.5 for 50/50 split)

    Total radial span = r_outer - r_inner  (fixed by CSV dimensions).
    tooth_len + ring_len = total span (always).
    r_root = r_inner + ring_len  (where teeth begin).
    """
    total = r_outer - r_inner
    tooth_len = total * default_tooth_frac   # fallback if property absent
    if hasattr(fa, "ToothLength") and fa.ToothLength:
        try:
            tooth_len = float(FreeCAD.Units.Quantity(str(fa.ToothLength)).Value)
        except Exception:
            pass
    tooth_len = max(min(tooth_len, total * 0.95), total * 0.05)
    ring_len = total - tooth_len
    r_root = r_inner + ring_len
    return r_root, tooth_len, ring_len


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL TOOTH LOCK WASHER  (Types 6 & 7)
# ─────────────────────────────────────────────────────────────────────────────

def _make_internal_gap_cut(r_tip, r_root, h, gap_w):
    """Annular-sector cut between two internal teeth (constant y-width gap)."""
    margin  = max(h, 0.5) + 0.1
    half_gw = gap_w / 2.0
    z_bot   = -h / 2.0 - margin
    z_h     = h + 2.0 * margin

    box = Part.makeBox(
        r_root - r_tip + 2.0 * margin,
        gap_w,
        z_h,
        Base.Vector(r_tip - margin, -half_gw, z_bot),
    )
    outer_cyl = Part.makeCylinder(r_root, z_h, Base.Vector(0, 0, z_bot), Base.Vector(0, 0, 1))
    inner_cyl = Part.makeCylinder(r_tip,  z_h, Base.Vector(0, 0, z_bot), Base.Vector(0, 0, 1))
    return box.common(outer_cyl).cut(inner_cyl)


def makeInternalToothLockWasher(self, fa):
    """ASME B18.21.1 internal tooth lock washer (Types 6 & 7)."""
    d1, d2, h = _read_dims(fa)
    is_type_b = str(fa.baseType).endswith("B")

    if hasattr(fa, "ToothCount") and fa.ToothCount >= 2:
        n = int(fa.ToothCount)
    else:
        n = 9 if is_type_b else 10

    r_tip = d1 / 2.0
    r_out = d2 / 2.0

    # Internal teeth go inward: r_root is the inner edge of the outer ring.
    # tooth_len = r_root - r_tip  (inward from ring toward bore).
    # ring_len  = r_out  - r_root (the solid outer ring band).
    # Increasing ToothLength moves r_root outward → longer teeth, shorter ring.
    _total = r_out - r_tip
    _tooth_frac = 0.45 if is_type_b else 0.50
    _tooth_len = _total * _tooth_frac   # default
    if hasattr(fa, "ToothLength") and fa.ToothLength:
        try:
            _tooth_len = float(FreeCAD.Units.Quantity(str(fa.ToothLength)).Value)
        except Exception:
            pass
    _tooth_len = max(min(_tooth_len, _total * 0.95), _total * 0.05)
    r_root = r_tip + _tooth_len

    pitch = 2.0 * math.pi / n

    _gap_frac = 0.35 if is_type_b else 0.30
    _recess_val = getattr(fa, "ToothRecessWidth", None)
    if _recess_val:
        try:
            gap_w = float(FreeCAD.Units.Quantity(str(_recess_val)).Value)
            gap_w = max(gap_w, 0.05)
        except Exception:
            gap_w = max(r_root * pitch * _gap_frac, 0.05)
    else:
        gap_w = max(r_root * pitch * _gap_frac, 0.05)
    gap_w = min(gap_w, r_root * pitch * 0.90)

    disk = Part.makeCylinder(r_out, h,
                             Base.Vector(0, 0, -h / 2.0), Base.Vector(0, 0, 1))
    bore = Part.makeCylinder(r_tip, h + 0.02,
                             Base.Vector(0, 0, -h / 2.0 - 0.01), Base.Vector(0, 0, 1))
    disk = disk.cut(bore)

    gap_cut = _make_internal_gap_cut(r_tip, r_root, h, gap_w)

    result = disk
    for i in range(n):
        g = gap_cut.copy()
        g.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 360.0 * i / n)
        result = result.cut(g)

    try:
        result = result.removeSplitter()
    except Exception:
        pass
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  EXTERNAL TOOTH LOCK WASHER  (Types 8 & 9)
# ─────────────────────────────────────────────────────────────────────────────

def _make_external_tooth_flat(r_wall, r_tip, h, tooth_width, ring_overlap, twist_deg):
    """3-profile twisted loft for Type 8 (flat) external tooth."""
    L  = max(r_tip - r_wall, 0.05)
    tw = tooth_width / 2.0
    zb, zt = -h / 2.0, h / 2.0

    root_pts = [
        Base.Vector(-ring_overlap, -tw, zb),
        Base.Vector(-ring_overlap,  tw, zb),
        Base.Vector(-ring_overlap,  tw, zt),
        Base.Vector(-ring_overlap, -tw, zt),
        Base.Vector(-ring_overlap, -tw, zb),
    ]
    root_wire = Part.Wire(Part.makePolygon(root_pts))

    edge_pts = [
        Base.Vector(+ring_overlap, -tw, zb),
        Base.Vector(+ring_overlap,  tw, zb),
        Base.Vector(+ring_overlap,  tw, zt),
        Base.Vector(+ring_overlap, -tw, zt),
        Base.Vector(+ring_overlap, -tw, zb),
    ]
    edge_wire = Part.Wire(Part.makePolygon(edge_pts))

    theta = math.radians(twist_deg)
    c, s = math.cos(theta), math.sin(theta)
    corners = [(-tw, zb), (tw, zb), (tw, zt), (-tw, zt)]
    tip_pts = [Base.Vector(+L, y*c - z*s, y*s + z*c) for y, z in corners]
    tip_pts.append(tip_pts[0])
    tip_wire = Part.Wire(Part.makePolygon(tip_pts))

    tooth = Part.makeLoft([root_wire, edge_wire, tip_wire], True, True, False)

    big = (L + ring_overlap + 1.0) * 2 + tooth_width * 2
    cut_top = Part.makeBox(big, big * 2, big, Base.Vector(-(ring_overlap + 1.0), -big, zt))
    cut_bot = Part.makeBox(big, big * 2, big, Base.Vector(-(ring_overlap + 1.0), -big, zb - big))
    tooth = tooth.cut(cut_top)
    tooth = tooth.cut(cut_bot)
    try:
        tooth = tooth.removeSplitter()
    except Exception:
        pass
    return tooth


# ─── Type 9 helpers ──────────────────────────────────────────────────────────

def _make_cone_body_rhombus(r_bore, r_tip, h_perp, tilt_deg):
    """
    Build the Type 9 cone body as a revolved RHOMBUS cross-section.

    All four edges of the rhombus carry physical meaning:
      - Top edge: along the cone slope (upper face of the sheet metal)
      - Bottom edge: along the cone slope, parallel to top (lower face)
      - Outer end edge: PERPENDICULAR to the slope, length h_perp
                         (this is the small face at the tooth tip)
      - Inner end edge: PERPENDICULAR to the slope, length h_perp
                         (this is the small face at the bore wall)

    Every measurable face of the wall has thickness h_perp, so whichever
    face you pick in FreeCAD's measure tool you get the CSV thickness.

    The bottom-outer corner is anchored at (r_tip - ox, 0) so the lowest
    point of the cone body sits in the z = 0 plane (flat-bottom reference).

    Returns: (body, z_min, z_max).
    """
    r_bore = max(r_bore, 0.05)
    r_tip  = max(r_tip, r_bore + 0.1)
    dr     = r_tip - r_bore
    tilt   = math.radians(tilt_deg)

    cos_t = math.cos(tilt)
    sin_t = math.sin(tilt)
    hh    = h_perp / 2.0

    # Perpendicular offset in (r, z): magnitude h_perp/2, pointing "up-out"
    # away from the cone axis.
    ox = hh * sin_t        # radial component
    oz = hh * cos_t        # vertical component

    # Outer mid-thickness centerline point at r = r_tip.
    # Choose z so that the bottom-outer corner (= mid_out - perp_offset) sits
    # at z = 0.
    #   bottom_outer.z = c_out_z - oz = 0  →  c_out_z = oz
    c_out_r = r_tip
    c_out_z = oz

    # Inner mid-thickness centerline point.
    # Going along the cone surface from outer to inner, r decreases by dr and
    # z increases by dr * tan(tilt).
    c_inn_r = r_bore
    c_inn_z = c_out_z + dr * math.tan(tilt)

    # Four rhombus corners (in r-z plane).  Order: bottom-outer → top-outer
    # → top-inner → bottom-inner, traversed counter-clockwise.
    p_bo = Base.Vector(c_out_r - ox, 0.0, c_out_z - oz)   # bottom-outer (z=0)
    p_to = Base.Vector(c_out_r + ox, 0.0, c_out_z + oz)   # top-outer
    p_ti = Base.Vector(c_inn_r + ox, 0.0, c_inn_z + oz)   # top-inner
    p_bi = Base.Vector(c_inn_r - ox, 0.0, c_inn_z - oz)   # bottom-inner

    wire = Part.Wire(Part.makePolygon([p_bo, p_to, p_ti, p_bi, p_bo]))
    face = Part.Face(wire)
    body = face.revolve(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 360.0)
    try:
        body = body.removeSplitter()
    except Exception:
        pass

    z_min = p_bo.z         # 0.0 by construction
    z_max = p_ti.z
    return body, z_min, z_max


def makeExternalToothLockWasher(self, fa):
    """
    ASME B18.21.1 external tooth lock washer.

    Type 8 (flat)    — twisted-loft teeth fused onto a flat ring.
    Type 9 (conical) — single revolved rhombus cone body with inter-tooth
                       gap wedges subtracted.  Always produces ONE connected
                       solid — no fusing of separate teeth, no floating
                       pieces.
    """
    is_type_b = str(fa.baseType).endswith("B")
    is_type9  = str(fa.baseType).startswith("ASMEB18.21.1.9")

    d1_bore, d2_out, h = _read_dims(fa)

    if hasattr(fa, "ToothCount") and fa.ToothCount >= 2:
        n = int(fa.ToothCount)
    else:
        n = 12 if is_type_b else 10

    if hasattr(fa, "ToothTwistAngle") and fa.ToothTwistAngle is not None and 0.0 < fa.ToothTwistAngle <= 45.0:
        twist_deg = float(fa.ToothTwistAngle)
    else:
        twist_deg = 15.0

    r_bore = d1_bore / 2.0
    r_tip  = d2_out  / 2.0

    # ─── Type 9: cone body with gap wedges cut between teeth ────────────────
    if is_type9:
        # Default 50/50 split; ToothLength overrides so tooth+ring = total span.
        r_root, _, _ = _read_tooth_length(fa, r_bore, r_tip, 0.50)

        # Cone tilt.  Type 9A mates with 82° countersink screw heads → cone
        # apex angle 82°, surface tilted 49° from horizontal.
        # Type 9B uses 80° → 50° tilt.
        cone_apex_deg = 80.0 if is_type_b else 82.0
        tilt_deg = 90.0 - cone_apex_deg / 2.0

        # Tooth circumferential width — constant from root to tip.
        # Each tooth is built as a RECTANGULAR BOX with side walls parallel
        # to the tooth's radial centerline, so the chord-width at the tip
        # equals the chord-width at the root (no taper).
        # Default: 30% of pitch arc at r_root for narrow tooth-lock spikes.
        pitch_arc_root = 2.0 * math.pi * r_root / n
        _tw_default = pitch_arc_root * (0.28 if is_type_b else 0.30)
        if hasattr(fa, "ToothWidth") and fa.ToothWidth:
            try:
                tooth_w = float(FreeCAD.Units.Quantity(str(fa.ToothWidth)).Value)
                tooth_w = max(tooth_w, 0.05)
            except Exception:
                tooth_w = _tw_default
        else:
            tooth_w = _tw_default
        tooth_w = min(tooth_w, pitch_arc_root * 0.80)
        tooth_w = max(tooth_w, 0.05)

        # Build cone body (single revolved rhombus solid).
        body, z_min, z_max = _make_cone_body_rhombus(
            r_bore, r_tip, h, tilt_deg,
        )

        # ── Build the outer-annulus removal solid ───────────────────────────
        # The annulus must follow the same slope as the cone body so that the
        # back wall exposed in the inter-tooth gap (at r=r_root) is tilted to
        # match the cone slope — not a vertical cylindrical wall.
        #
        # Construction: revolve a RHOMBUS cross-section that has the same
        # shape and tilt as the cone body, but extends from r_root to
        # r_outer_annulus and is thicker (so it fully covers the cone body
        # in the perpendicular direction).  The annulus's inner side face
        # (after revolving) is a tilted "disk" perpendicular to the cone
        # slope direction — so when the annulus is cut from the cone, the
        # exposed back-wall of the gap appears tilted at the cone slope
        # angle, visually continuous with the inner ring's outer surface.
        h_offset_radial = (h / 2.0) * math.sin(math.radians(tilt_deg))
        r_outer_annulus = r_tip + h_offset_radial + 1.0

        # Annulus perpendicular thickness — large enough to fully contain
        # the cone body's thickness on both sides of the slope.
        h_ann = h + 4.0
        tilt_rad = math.radians(tilt_deg)
        cos_t = math.cos(tilt_rad)
        sin_t = math.sin(tilt_rad)
        hh_ann = h_ann / 2.0
        ox_ann = hh_ann * sin_t
        oz_ann = hh_ann * cos_t

        # Cone body's centerline z reference at r=r_tip.  This must match
        # the construction inside _make_cone_body_rhombus, which places the
        # outer-bottom corner at z=0 and the outer-centerline at z=(h/2)*cos(tilt).
        cone_oz = (h / 2.0) * cos_t

        # Annulus shape (TILTED RHOMBUS in r-z plane, matching the cone slope):
        #   - Top/bottom edges along the cone slope (parallel to cone faces)
        #   - Inner/outer end edges perpendicular to the slope (tilted disks
        #     when revolved)
        #   The annulus inner end face (revolved) is a TILTED DISK
        #   perpendicular to the cone slope direction, so the back-wall of
        #   the gap between teeth visually continues the cone slope rather
        #   than being a vertical cylindrical wall.
        #
        # Centerlines at r=r_root and r=r_outer_annulus (along cone slope):
        c_inn_ann_r = r_root
        c_inn_ann_z = cone_oz + (r_tip - r_root) * math.tan(tilt_rad)
        c_out_ann_r = r_outer_annulus
        c_out_ann_z = cone_oz + (r_tip - r_outer_annulus) * math.tan(tilt_rad)

        # Four annulus rhombus corners — perpendicular offsets at each end.
        # The inner end edge spans radially from (r_root - ox_ann) to
        # (r_root + ox_ann) as z varies, which means the annulus's inner
        # boundary reaches slightly past r_root toward the bore on one side.
        ann_p1 = Base.Vector(c_out_ann_r - ox_ann, 0.0, c_out_ann_z - oz_ann)  # bot-outer
        ann_p2 = Base.Vector(c_out_ann_r + ox_ann, 0.0, c_out_ann_z + oz_ann)  # top-outer
        ann_p3 = Base.Vector(c_inn_ann_r + ox_ann, 0.0, c_inn_ann_z + oz_ann)  # top-inner
        ann_p4 = Base.Vector(c_inn_ann_r - ox_ann, 0.0, c_inn_ann_z - oz_ann)  # bot-inner
        ann_wire = Part.Wire(Part.makePolygon([ann_p1, ann_p2, ann_p3, ann_p4, ann_p1]))
        ann_face = Part.Face(ann_wire)
        annulus = ann_face.revolve(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 360.0)
        try:
            annulus = annulus.removeSplitter()
        except Exception:
            pass

        # Build ONE tooth box centred on +X axis.
        #
        # CRITICAL — tooth box inner extent:
        #   The annulus's inner edge (from p4 to p3) is tilted; its innermost
        #   radial reach is at r = r_root - ox_ann (at the bot-inner corner).
        #   If the tooth box only started at r_root, the cut between teeth
        #   would extend INWARD past r_root in the upper portion of the
        #   tooth, leaving a triangular cyan gap where the tooth should
        #   join the ring.
        #   To eliminate that gap, the tooth box must start at
        #   r = r_root - ox_ann - small overlap, so it FULLY covers the
        #   annulus's tilted inner-edge band across all z values.
        #   The extra material at the tooth root just merges into the inner
        #   ring (it's inside r_root, where the ring already exists).
        tooth_box_x_start = (r_root - ox_ann) - 0.1
        tooth_box_x_len   = (r_outer_annulus + ox_ann + 0.1) - tooth_box_x_start
        half_w = tooth_w / 2.0
        # The box z-extent must cover the annulus's full z range.
        ann_z_min = min(ann_p1.z, ann_p2.z, ann_p3.z, ann_p4.z) - 0.5
        ann_z_max = max(ann_p1.z, ann_p2.z, ann_p3.z, ann_p4.z) + 0.5
        box_z_lo = ann_z_min
        box_z_h  = ann_z_max - ann_z_min
        tooth_box_local = Part.makeBox(
            tooth_box_x_len,
            tooth_w,
            box_z_h,
            Base.Vector(tooth_box_x_start, -half_w, box_z_lo),
        )

        # Subtract n rotated tooth boxes from the annulus.  What remains is
        # the inter-tooth material — the wide arcs to be removed from the
        # cone, with proper parallel-walled tooth-shaped notches cut into it.
        pitch_deg = 360.0 / n
        removal = annulus
        for i in range(n):
            t = tooth_box_local.copy()
            t.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1),
                     i * pitch_deg)
            try:
                removal = removal.cut(t)
            except Exception:
                pass

        # Cut the removal solid from the cone body.  The surviving material
        # in the outer region is exactly the n teeth (rectangular shape,
        # equal width at root and tip), while the inner annular band
        # r_bore→r_root is left untouched by the cut.
        try:
            result = body.cut(removal)
        except Exception:
            result = body

        try:
            result = result.removeSplitter()
        except Exception:
            pass
        return result

    # ─── Type 8: flat washer with twisted teeth ─────────────────────────────
    # Default tooth fraction: 55% (B) / 60% (A) of total span.
    # ToothLength overrides; ring adjusts so tooth+ring = total span.
    _tooth_frac8 = 0.55 if is_type_b else 0.60
    r_wall, _, _ = _read_tooth_length(fa, r_bore, r_tip, _tooth_frac8)

    pitch_arc = r_wall * 2.0 * math.pi / n
    _wf_default = 0.45 if is_type_b else 0.50
    _default_tw = max(pitch_arc * _wf_default, 0.05)

    if hasattr(fa, "ToothWidth") and fa.ToothWidth:
        try:
            tooth_w = float(FreeCAD.Units.Quantity(str(fa.ToothWidth)).Value)
            tooth_w = max(tooth_w, 0.05)
        except Exception:
            tooth_w = _default_tw
    else:
        tooth_w = _default_tw
    tooth_w = min(tooth_w, pitch_arc * 0.90)

    ring_overlap = max(0.15 * (r_tip - r_wall), 0.15)

    ring = Part.makeCylinder(
        r_wall + ring_overlap, h,
        Base.Vector(0, 0, -h / 2.0), Base.Vector(0, 0, 1),
    )
    bore_hole = Part.makeCylinder(
        r_bore, h + 0.02,
        Base.Vector(0, 0, -h / 2.0 - 0.01), Base.Vector(0, 0, 1),
    )
    ring = ring.cut(bore_hole)

    tooth_local = _make_external_tooth_flat(
        r_wall, r_tip, h, tooth_w, ring_overlap, twist_deg,
    )
    tooth_local.translate(Base.Vector(r_wall, 0.0, 0.0))

    result = ring
    for i in range(n):
        t = tooth_local.copy()
        t.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 360.0 * i / n)
        try:
            new_result = result.fuse(t)
            try:
                new_result = new_result.removeSplitter()
            except Exception:
                pass
            result = new_result
        except Exception:
            pass

    try:
        result = result.removeSplitter()
    except Exception:
        pass
    return result