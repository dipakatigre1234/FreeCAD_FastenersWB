# -*- coding: utf-8 -*-
from screw_maker import *
import FastenerBase
import sys as _sys_wn, os as _os_wn
import math
import Part
from FreeCAD import Base
import FreeCAD as App

_wb_wn = _os_wn.path.dirname(_os_wn.path.dirname(_os_wn.path.abspath(__file__)))
if _wb_wn not in _sys_wn.path:
    _sys_wn.path.insert(0, _wb_wn)
import FSThreadingMetricInternal as _TMI
import FSThreadingASMEInternal as _TAI


def makeWingNut(self, fa):
    """Wing nut generator — DIN 315, ASME B18.6.9A, ASME B18.6.9.3,
       ASME B18.6.9.2, ASME B18.6.9.4(A/B), and ASME B18.6.9.6."""
    SType   = fa.baseType
    is_asme = SType.startswith("ASME")
    dia     = self.getDia(fa.calc_diam, True)

    # ── Hardened curve-type check ─────────────────────────────────────────────
    def _curve_is(e, types):
        try:
            return isinstance(e.Curve, types)
        except Exception:
            return False

    # ── Safe bounded fillet ───────────────────────────────────────────────────
    def _safe_fillet(solid, edges, rad, edge_cap=0.40):
        if not edges or rad <= 0:
            return solid
        try:
            min_len = min((e.Length for e in edges if getattr(e, "Length", 0) > 1e-6),
                          default=0.0)
        except Exception:
            min_len = 0.0
        r = rad
        if min_len > 1e-6:
            r = min(r, min_len * edge_cap)
        if r <= 1e-4:
            return solid
        try:
            out = solid.makeFillet(r, edges)
            if out.isValid():
                return out
        except Exception:
            pass
        cur = solid
        for e in edges:
            try:
                el = getattr(e, "Length", 0.0)
                er = min(r, el * edge_cap) if el > 1e-6 else r
                if er <= 1e-4:
                    continue
                trial = cur.makeFillet(er, [e])
                if trial.isValid():
                    cur = trial
            except Exception:
                continue
        return cur

    # ── Dimension unpacking ───────────────────────────────────────────────────
    if SType == "DIN315":
        P, d2_max, d2_min, d3_max, d3_min, e_max, e_min, \
            m_max, m_min, g, h_max, h_min = fa.dimTable
        d2 = (d2_max + d2_min) / 2
        d3 = (d3_max + d3_min) / 2
        e, m, h, wing_r = (e_max+e_min)/2, (m_max+m_min)/2, (h_max+h_min)/2, g/4

    elif SType == "ASMEB18.6.9A":
        TPI, A_max, A_min, B_max, B_min, C_max, C_min, \
            D_max, D_min, E_max, E_min, G_max, G_min = fa.dimTable
        def avg(a, b): return (a + b) / 2 * 25.4
        P  = 25.4 / TPI
        d2, d3 = avg(E_max, E_min), avg(D_max, D_min)
        e, m, g, h = avg(A_max, A_min), avg(G_max, G_min), avg(C_max, C_min), avg(B_max, B_min)
        wing_r = g / 5

    elif SType in ["ASMEB18.6.9.3", "ASMEB18.6.9.2", "ASMEB18.6.9.6"]:
        TPI, A_max, A_min, B_max, B_min, C_max, C_min, \
            D_max, D_min, E_max, E_min, G_max, G_min = fa.dimTable
        def avg(a, b): return (a + b) / 2 * 25.4
        P = 25.4 / TPI
        A = avg(A_max, A_min)
        B = avg(B_max, B_min)
        C = avg(C_max, C_min)
        D = avg(D_max, D_min)
        E = avg(E_max, E_min)
        G = avg(G_max, G_min)
        d2 = D; d3 = E; m = G; g = C; h = B; e = A
        wing_r = g / 5

    elif SType in ["ASMEB18.6.9.4A", "ASMEB18.6.9.4B", "ASMEB18.6.9.4"]:
        TPI, A_max, A_min, B_max, B_min, C_max, C_min, \
            D_max, D_min, E_max, E_min, F_max, F_min, G_max, G_min = fa.dimTable
        def avg(a, b): return (a + b) / 2 * 25.4
        P = 25.4 / TPI
        A = avg(A_max, A_min); B = avg(B_max, B_min); C = avg(C_max, C_min)
        D = avg(D_max, D_min); E = avg(E_max, E_min); F = avg(F_max, F_min)
        G = avg(G_max, G_min)
        d2 = D; d3 = E; m = G; g = C; h = B; e = A
        wing_r = g / 5

    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    # ── Pitch resolution ──────────────────────────────────────────────────────
    if not is_asme and _TMI is not None:
        _p = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
        try:
            P = float(_p) if _p else (
                fa.calc_pitch if (getattr(fa, "calc_pitch", None) or 0) > 0 else P)
        except Exception:
            pass
    else:
        if (getattr(fa, "calc_pitch", None) or 0) > 0:
            P = fa.calc_pitch
        if is_asme and _TAI is not None:
            try:
                tpi = _TAI.resolve_nut_tpi(fa)
                if tpi and tpi > 0:
                    P = 25.4 / tpi
            except Exception:
                pass

    # ── Topology helpers ──────────────────────────────────────────────────────
    def make_line(p1, p2):
        return Part.LineSegment(p1, p2).toShape()

    def make_bezier(pts):
        curve = Part.BezierCurve()
        curve.setPoles(pts)
        return curve.toShape()

    # =========================================================================
    # ASMEB18.6.9.6  —  Type C Style 3
    # =========================================================================
    if SType == "ASMEB18.6.9.6":

        Z_cyl = G * 0.15

        # ── 1. BOSS (truncated cone) ──────────────────────────────────────────
        fm_boss = FSFaceMaker()
        fm_boss.AddPoint(0.0,       0.0)
        fm_boss.AddPoint(E / 2.0,   0.0)
        fm_boss.AddPoint(E / 2.0,   Z_cyl)
        fm_boss.AddPoint(D / 2.0,   G)
        fm_boss.AddPoint(0.0,       G)
        boss = self.RevolveZ(fm_boss.GetFace())
        try:
            circ_edges = [ed for ed in boss.Edges if _curve_is(ed, Part.Circle)]
            if circ_edges:
                boss = _safe_fillet(boss, circ_edges, 0.015)
        except Exception:
            pass
        shape = boss

        # ── 2. DERIVED DIMENSIONS ─────────────────────────────────────────────
        rA = A / 2.0          # overall wing-tip radius
        rD = D / 2.0          # boss top  outer radius
        rE = E / 2.0          # boss base outer radius
        W      = rA - rD      # radial wing width  (always > 0 per standard)
        H_wing = B - G        # axial  wing height (always > 0 per standard)

        # Approximate bore radius from nominal diameter + pitch
        # (exact value comes from _TAI later; we only need it here for
        #  safe-penetration depth, not for geometry correctness)
        try:
            sqrt3_v = math.sqrt(3.0)
            bore_r_approx = dia / 2.0 - P * 0.625 * sqrt3_v / 2.0
        except Exception:
            bore_r_approx = dia / 2.0 * 0.8

        # Wall thickness at boss base (rE) and top (rD)
        wall_E = max(rE - bore_r_approx, 0.05)
        wall_D = max(rD - bore_r_approx, 0.05)

        # ── ROOT CAUSE FIX ────────────────────────────────────────────────────
        # The wing extrusion must have SOLID OVERLAP with the boss so that
        # OCC fuse() works reliably.  A mere surface touch (0.08 mm) causes
        # the fuse to return the same volume and safe_fuse() discards the wing.
        #
        # Solution: anchor points v2 / v3 penetrate 30 % into the boss wall.
        # This is always safe: 30 % < 100 %, so anchors stay outside bore_r.
        #
        # Shift the top of the wing root down the conical body to prevent the inner bore/chamfer
        # from cutting through the wing and exposing the recess pocket.
        shift_frac = 0.12
        Z_top_wing = G - G * shift_frac
        if G - Z_cyl > 1e-5:
            r_boss_top = rE - (rE - rD) * (Z_top_wing - Z_cyl) / (G - Z_cyl)
        else:
            r_boss_top = rD
        wall_top = max(r_boss_top - bore_r_approx, 0.05)

        PEN_FRAC = 0.30
        x2_val = math.sqrt(max((rE - wall_E * PEN_FRAC)**2 - (C / 2.0)**2, 0.0))
        x3_val = math.sqrt(max((r_boss_top - wall_top * PEN_FRAC)**2 - (C / 2.0)**2, 0.0))
        v2 = Base.Vector(x2_val, 0.0, Z_cyl)
        v3 = Base.Vector(x3_val, 0.0, Z_top_wing)

        # ── 3. WING OUTLINE (bezier teardrop profile) ─────────────────────────
        # All X coordinates are rD + W*fraction so they scale with every size.
        P_in_CP1    = Base.Vector(rD + W * 0.138, 0.0, G + H_wing * 0.20)
        P_in_CP2    = Base.Vector(rD + W * 0.055, 0.0, G + H_wing * 0.64)
        P_in_end    = Base.Vector(rD + W * 0.138, 0.0, G + H_wing * 0.88)
        Corner_in   = Base.Vector(rD + W * 0.166, 0.0, B - H_wing * 0.01)
        P_top_start = Base.Vector(rD + W * 0.290, 0.0, B - H_wing * 0.01)
        P_top_end   = Base.Vector(rD + W * 0.708, 0.0, G + H_wing * 0.91)
        Corner_out  = Base.Vector(rD + W * 0.900, 0.0, G + H_wing * 0.88)
        P_out_end   = Base.Vector(rD + W * 0.900, 0.0, G + H_wing * 0.73)
        P_out_CP2   = Base.Vector(rD + W * 0.940, 0.0, G + H_wing * 0.29)
        P_out_CP1   = Base.Vector(rD + W * 0.630, 0.0, G * 0.50)

        edges_wing = [
            make_line(v2, v3),
            make_bezier([v3,       P_in_CP1, P_in_CP2, P_in_end]),
            make_bezier([P_in_end, Corner_in, P_top_start]),
            make_line(P_top_start, P_top_end),
            make_bezier([P_top_end, Corner_out, P_out_end]),
            make_bezier([P_out_end, P_out_CP2, P_out_CP1, v2]),
        ]

        wing_face = None
        try:
            w = Part.Wire(edges_wing)
            if w.isValid() and w.isClosed():
                f = Part.Face(w)
                if f.isValid() and not f.isNull() and f.Area > 1e-6:
                    wing_face = f
        except Exception:
            wing_face = None

        # Robust fallback: solid box that clearly overlaps the boss
        def _fallback_wing():
            box = Part.makeBox(W + wall_D * PEN_FRAC, C, H_wing)
            box.translate(Base.Vector(
                rD - wall_D * PEN_FRAC, -C / 2.0, G))
            return box

        wing_base = None
        if wing_face is not None:
            try:
                wb = wing_face.extrude(Base.Vector(0, C, 0))
                wb.translate(Base.Vector(0, -C / 2.0, 0))
                if wb.isValid() and wb.Volume > 1e-9:
                    wing_base = wb
            except Exception:
                pass

        wing = wing_base.copy() if wing_base is not None else None

        # ── 4. RECESS TRACK ───────────────────────────────────────────────────
        if wing is not None:
            recess_face = None
            try:
                R_in_bot     = Base.Vector(rD + W * 0.234, 0.0, G + H_wing * 0.15)
                R_in_CP1     = Base.Vector(rD + W * 0.166, 0.0, G + H_wing * 0.35)
                R_in_CP2     = Base.Vector(rD + W * 0.166, 0.0, G + H_wing * 0.60)
                R_in_top     = Base.Vector(rD + W * 0.207, 0.0, G + H_wing * 0.78)
                R_TopIn_CP1  = Base.Vector(rD + W * 0.234, 0.0, G + H_wing * 0.86)
                R_TopIn_CP2  = Base.Vector(rD + W * 0.305, 0.0, G + H_wing * 0.88)
                R_TopIn_End  = Base.Vector(rD + W * 0.388, 0.0, G + H_wing * 0.87)
                R_TopFlat_End= Base.Vector(rD + W * 0.666, 0.0, G + H_wing * 0.81)
                R_TopOut_CP1 = Base.Vector(rD + W * 0.749, 0.0, G + H_wing * 0.79)
                R_TopOut_CP2 = Base.Vector(rD + W * 0.820, 0.0, G + H_wing * 0.73)
                R_TopOut_End = Base.Vector(rD + W * 0.832, 0.0, G + H_wing * 0.63)
                R_out_CP1    = Base.Vector(rD + W * 0.861, 0.0, G + H_wing * 0.45)
                R_out_CP2    = Base.Vector(rD + W * 0.805, 0.0, G + H_wing * 0.28)
                R_out_bot    = Base.Vector(rD + W * 0.693, 0.0, G + H_wing * 0.12)
                R_bot_CP1    = Base.Vector(rD + W * 0.610, 0.0, G + H_wing * 0.02)
                R_bot_CP2    = Base.Vector(rD + W * 0.305, 0.0, G + H_wing * 0.03)

                edges_rec = [
                    make_bezier([R_in_bot,     R_in_CP1,    R_in_CP2,    R_in_top]),
                    make_bezier([R_in_top,     R_TopIn_CP1, R_TopIn_CP2, R_TopIn_End]),
                    make_line(R_TopIn_End, R_TopFlat_End),
                    make_bezier([R_TopFlat_End,R_TopOut_CP1,R_TopOut_CP2,R_TopOut_End]),
                    make_bezier([R_TopOut_End, R_out_CP1,   R_out_CP2,   R_out_bot]),
                    make_bezier([R_out_bot,    R_bot_CP1,   R_bot_CP2,   R_in_bot]),
                ]
                rw = Part.Wire(edges_rec)
                if rw.isValid() and rw.isClosed():
                    rf = Part.Face(rw)
                    if rf.isValid() and not rf.isNull() and rf.Area > 1e-6:
                        recess_face = rf
            except Exception:
                recess_face = None

            if recess_face is not None:
                try:
                    rec_depth = C / 4.0
                    rec_R = recess_face.extrude(Base.Vector(0,  rec_depth + 1.0, 0))
                    rec_R.translate(Base.Vector(0,  C / 2.0 - rec_depth, 0))
                    rec_L = recess_face.extrude(Base.Vector(0, -(rec_depth + 1.0), 0))
                    rec_L.translate(Base.Vector(0, -C / 2.0 + rec_depth, 0))
                    if rec_R.isValid() and rec_L.isValid():
                        trial = wing.cut(rec_R).cut(rec_L)
                        if trial.isValid() and trial.Volume > 1e-9:
                            wing = trial
                except Exception:
                    pass  # keep unrecessed wing

        # ── 5. EDGE FILLET ────────────────────────────────────────────────────
        if wing is not None:
            fillet_rad = C * 0.08
            edges_to_fillet = []
            for e in wing.Edges:
                if hasattr(e, "BoundBox"):
                    if (e.BoundBox.YMax - e.BoundBox.YMin) < 1e-3:
                        if e.CenterOfMass.x > rE:
                            if _curve_is(e, (Part.Line, Part.Circle,
                                             Part.LineSegment)):
                                edges_to_fillet.append(e)
            if edges_to_fillet:
                wing = _safe_fillet(wing, edges_to_fillet, fillet_rad)

            # Fillet the recess floor edges
            floor_edges = []
            for e in wing.Edges:
                if hasattr(e, "BoundBox"):
                    if (e.BoundBox.YMax - e.BoundBox.YMin) < 1e-4:
                        if abs(abs(e.CenterOfMass.y) - (C / 4.0)) < 1e-4:
                            floor_edges.append(e)
            if floor_edges:
                try:
                    # For recess floor, must fillet all edges together or not at all
                    # to prevent invalid shell topology (gaps/intersections at corners).
                    trial = wing.makeFillet(fillet_rad, floor_edges)
                    if trial.isValid() and trial.Volume > 1e-9:
                        wing = trial
                except Exception:
                    pass

        # ── 6. ASSEMBLE — cascading fallback ──────────────────────────────────
        def safe_fuse(base_s, wing_s):
            if wing_s is None or not wing_s.isValid() or wing_s.Volume <= 1e-9:
                return None
            try:
                res = base_s.fuse(wing_s)
                # Accept if result is valid and clearly larger than base alone
                if res.isValid() and res.Volume > base_s.Volume * 1.001:
                    return res
            except Exception:
                pass
            return None

        successful_wing = None
        for candidate in [wing, wing_base, _fallback_wing()]:
            tf = safe_fuse(shape, candidate)
            if tf is not None:
                shape = tf
                successful_wing = candidate
                break

        if successful_wing is not None:
            wing_left = successful_wing.copy()
            wing_left.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
            tf = safe_fuse(shape, wing_left)
            if tf is not None:
                shape = tf

        # ── 7. CONCAVE ROOT FILLET ────────────────────────────────────────────
        root_rad = C * 0.15
        root_edges = []
        for e in shape.Edges:
            try:
                cm = e.CenterOfMass
                dist = math.sqrt(cm.x ** 2 + cm.y ** 2)
                if (rD * 0.7) < dist < (rE * 1.3):
                    if _curve_is(e, (Part.Line, Part.Circle, Part.LineSegment)):
                        if (Z_cyl * 0.5) < cm.z < (G * 1.5):
                            root_edges.append(e)
            except Exception:
                pass
        if root_edges:
            shape = _safe_fillet(shape, root_edges, root_rad)

        try:
            # Copy shape before removeSplitter to prevent in-place OCC memory corruption if it fails
            temp_shape = shape.copy()
            cleaned = temp_shape.removeSplitter()
            # Only accept the cleaned shape if it is valid and does not have corrupted geometry/volume.
            # removeSplitter should not alter the volume significantly (certainly not exceeding 10% change).
            if cleaned.isValid() and 1e-9 < cleaned.Volume < shape.Volume * 1.1:
                shape = cleaned
        except Exception:
            pass

        try:
            if shape is None or not shape.isValid() or shape.Volume <= 1e-9:
                shape = boss
        except Exception:
            shape = boss

    # =========================================================================
    # ASMEB18.6.9.4A / 4B / 4  —  Type C Style 1
    # =========================================================================
    elif SType in ["ASMEB18.6.9.4A", "ASMEB18.6.9.4B", "ASMEB18.6.9.4"]:
        Z_cyl  = G * 0.15
        Z_chamf= G * 0.20

        fm_boss = FSFaceMaker()
        fm_boss.AddPoint(0.0,     0.0)
        fm_boss.AddPoint(E/2.0,   0.0)
        fm_boss.AddPoint(E/2.0,   Z_cyl)
        fm_boss.AddPoint(F/2.0,   Z_cyl + Z_chamf)
        fm_boss.AddPoint(D/2.0,   G)
        fm_boss.AddPoint(0.0,     G)
        boss = self.RevolveZ(fm_boss.GetFace())
        try:
            circ_edges = [ed for ed in boss.Edges if _curve_is(ed, Part.Circle)]
            if circ_edges:
                boss = _safe_fillet(boss, circ_edges, 0.015)
        except Exception:
            pass
        shape = boss

        rA = A/2.0; rD = D/2.0; rE = E/2.0; rF = F/2.0
        W     = rA - rD
        H     = B - G
        W_bot = rA - rE

        approx_inner_rad = dia / 2.0
        ov_E = max(0.1, (rE - approx_inner_rad) * 0.45)
        ov_F = max(0.1, (rF - approx_inner_rad) * 0.45)
        ov_D = max(0.1, (rD - approx_inner_rad) * 0.45)

        v1 = Base.Vector(rE - ov_E, 0.0, 0.0)
        v2 = Base.Vector(rE - ov_E, 0.0, Z_cyl)
        v3 = Base.Vector(rF - ov_F, 0.0, Z_cyl + Z_chamf)
        v4 = Base.Vector(rD - ov_D, 0.0, G)

        CP_in_1     = Base.Vector(rD + W * 0.210, 0.0, G + H * 0.265)
        CP_in_2     = Base.Vector(rD + W * 0.184, 0.0, G + H * 0.647)
        P_in_end    = Base.Vector(rD + W * 0.263, 0.0, G + H * 0.853)
        Corner_in   = Base.Vector(rD + W * 0.316, 0.0, B)
        P_top_start = Base.Vector(rD + W * 0.447, 0.0, B)
        P_top_end   = Base.Vector(rA - W * 0.263, 0.0, B - H * 0.059)
        Corner_out  = Base.Vector(rA - W * 0.053, 0.0, B - H * 0.088)
        P_out_start = Base.Vector(rA,             0.0, B - H * 0.265)
        CP_out_1    = Base.Vector(rA + W * 0.132, 0.0, G + H * 0.294)
        CP_out_2    = Base.Vector(rE + W_bot * 0.656, 0.0, G * 0.435)

        edges_wing = [
            make_line(v1, v2), make_line(v2, v3), make_line(v3, v4),
            make_bezier([v4, CP_in_1, CP_in_2, P_in_end]),
            make_bezier([P_in_end, Corner_in, P_top_start]),
            make_line(P_top_start, P_top_end),
            make_bezier([P_top_end, Corner_out, P_out_start]),
            make_bezier([P_out_start, CP_out_1, CP_out_2, v1]),
        ]
        wing_face = Part.Face(Part.Wire(edges_wing))

        R_v4        = Base.Vector(rD + W * 0.237, 0.0, G + H * 0.059)
        R_CP_in_1   = Base.Vector(rD + W * 0.342, 0.0, G + H * 0.353)
        R_CP_in_2   = Base.Vector(rD + W * 0.316, 0.0, G + H * 0.647)
        R_in_end    = Base.Vector(rD + W * 0.368, 0.0, G + H * 0.765)
        R_Corner_in = Base.Vector(rD + W * 0.421, 0.0, B - H * 0.147)
        R_top_start = Base.Vector(rD + W * 0.500, 0.0, B - H * 0.147)
        R_top_end   = Base.Vector(rA - W * 0.342, 0.0, B - H * 0.206)
        R_Corner_out= Base.Vector(rA - W * 0.184, 0.0, B - H * 0.235)
        R_out_start = Base.Vector(rA - W * 0.132, 0.0, B - H * 0.353)
        R_CP_out_1  = Base.Vector(rA,             0.0, G + H * 0.294)
        R_CP_out_2  = Base.Vector(rE + W_bot * 0.562, 0.0, G * 0.652)
        R_v1        = Base.Vector(rE + W_bot * 0.250, 0.0, G * 0.565)
        R_Bot_CP_1  = Base.Vector(rD + W * 0.237, 0.0, G * 0.522)
        R_Bot_CP_2  = Base.Vector(rD + W * 0.184, 0.0, G * 0.783)

        edges_rec = [
            make_bezier([R_v4,        R_CP_in_1,   R_CP_in_2,   R_in_end]),
            make_bezier([R_in_end,    R_Corner_in,  R_top_start]),
            make_line(R_top_start, R_top_end),
            make_bezier([R_top_end,   R_Corner_out, R_out_start]),
            make_bezier([R_out_start, R_CP_out_1,   R_CP_out_2,  R_v1]),
            make_bezier([R_v1,        R_Bot_CP_1,   R_Bot_CP_2,  R_v4]),
        ]
        rec_face = Part.Face(Part.Wire(edges_rec))

        wing = wing_face.extrude(Base.Vector(0, C, 0))
        wing.translate(Base.Vector(0, -C/2.0, 0))

        rec_depth = C / 4.0
        rec_R = rec_face.extrude(Base.Vector(0,  rec_depth + 1.0, 0))
        rec_R.translate(Base.Vector(0,  C/2.0 - rec_depth, 0))
        rec_L = rec_face.extrude(Base.Vector(0, -(rec_depth + 1.0), 0))
        rec_L.translate(Base.Vector(0, -C/2.0 + rec_depth, 0))
        wing = wing.cut(rec_R).cut(rec_L)

        fillet_rad = C * 0.08
        edges_to_fillet = []
        for e in wing.Edges:
            if hasattr(e, "BoundBox"):
                if (e.BoundBox.YMax - e.BoundBox.YMin) < 1e-3:
                    if e.CenterOfMass.x > (rF * 1.05):
                        edges_to_fillet.append(e)
        if edges_to_fillet:
            wing = _safe_fillet(wing, edges_to_fillet, fillet_rad)

        shape = shape.fuse(wing)
        wing_left = wing.copy()
        wing_left.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
        shape = shape.fuse(wing_left)

        root_rad = C * 0.15
        root_edges = []
        for e in shape.Edges:
            try:
                cm = e.CenterOfMass
                dist = math.sqrt(cm.x**2 + cm.y**2)
                if (rD * 0.7) < dist < (rF * 1.3):
                    if not _curve_is(e, (Part.Circle, Part.Line)):
                        if (Z_cyl * 0.5) < cm.z < (G * 1.5):
                            root_edges.append(e)
            except Exception:
                pass
        if root_edges:
            shape = _safe_fillet(shape, root_edges, root_rad)

        try:
            shape = shape.removeSplitter()
        except Exception:
            pass

    # =========================================================================
    # ASMEB18.6.9.3  —  Type B Style 3  (tangent sweep)
    # =========================================================================
    elif SType == "ASMEB18.6.9.3":
        approx_inner_rad = dia / 2.0
        overlap = max(0.5, (min(D/2.0, E/2.0) - approx_inner_rad) * 0.45)

        fm_boss = FSFaceMaker()
        fm_boss.AddPoint(0.0,     0.0)
        fm_boss.AddPoint(E/2.0,   0.0)
        fm_boss.AddPoint(D/2.0,   G)
        fm_boss.AddPoint(0.0,     G)
        boss = self.RevolveZ(fm_boss.GetFace())
        try:
            circ_edges = [ed for ed in boss.Edges if _curve_is(ed, Part.Circle)]
            if circ_edges:
                boss = _safe_fillet(boss, circ_edges, P / 2.0)
        except Exception:
            pass
        shape = boss

        r_tip  = G / 2.0
        C_lobe = Base.Vector(A/2.0 - r_tip, 0.0, B - r_tip)
        fillet_z = P / 2.0

        R_bot_fillet = ((E/2.0) - fillet_z * ((E/2.0) - (D/2.0)) / G
                        if G > 0 else E/2.0)

        val_bot = R_bot_fillet**2 - (C/2.0)**2
        val_top = (D/2.0)**2     - (C/2.0)**2
        X_bot = math.sqrt(val_bot if val_bot > 0 else 0) - overlap
        X_top = math.sqrt(val_top if val_top > 0 else 0) - overlap

        P_bot = Base.Vector(X_bot, 0.0, fillet_z)
        P_top = Base.Vector(X_top, 0.0, G)

        def get_tangent_sweep_arc(P_start, center_lobe, radius_lobe,
                                  angle_deg, reverse=False):
            ang = math.radians(angle_deg)
            u = Base.Vector(math.cos(ang), 0.0, math.sin(ang))
            P_tan = center_lobe + u * radius_lobe
            D_vec = P_tan - P_start
            dot_prod = D_vec.x * u.x + D_vec.z * u.z
            if dot_prod == 0:
                dot_prod = 1e-6
            R_sweep = -(D_vec.Length**2) / (2.0 * dot_prod)
            C_sweep = P_tan + u * R_sweep
            V1 = P_start - C_sweep
            V2 = P_tan   - C_sweep
            V_mid = V1 + V2
            V_mid.normalize()
            P_mid = C_sweep + V_mid * R_sweep
            if reverse:
                return Part.Arc(P_tan, P_mid, P_start).toShape(), P_tan
            return Part.Arc(P_start, P_mid, P_tan).toShape(), P_tan

        def get_user_radius_arc(P_start, center_lobe, r_tip, R_user):
            x1, z1 = P_start.x, P_start.z
            x2, z2 = center_lobe.x, center_lobe.z
            d = math.sqrt((x2-x1)**2 + (z2-z1)**2)
            min_R = (d - r_tip) / 2.0
            if R_user < min_R:
                R_user = min_R * 1.001
            val = (d**2 + R_user**2 - (R_user + r_tip)**2) / (2 * d * R_user)
            cos_theta = max(-1.0, min(1.0, val))
            theta = math.acos(cos_theta)
            alpha = math.atan2(z2-z1, x2-x1)
            angle_c = alpha + theta
            C_arc = Base.Vector(
                x1 + R_user * math.cos(angle_c), 0.0,
                z1 + R_user * math.sin(angle_c))
            V_tan = center_lobe - C_arc
            if V_tan.Length == 0:
                V_tan = Base.Vector(1, 0, 0)
            V_tan.normalize()
            P_tan = C_arc + V_tan * R_user
            V_start = P_start - C_arc
            V_end   = P_tan   - C_arc
            V_mid   = V_start + V_end
            if V_mid.Length == 0:
                V_mid = Base.Vector(0, 1, 0)
            V_mid.normalize()
            P_mid = C_arc + V_mid * R_user
            return Part.Arc(P_tan, P_mid, P_start).toShape(), P_tan

        arc_out, P_tan_out = get_tangent_sweep_arc(P_bot, C_lobe, r_tip, -35)
        arc_in,  P_tan_in  = get_user_radius_arc(P_top, C_lobe, r_tip, A)
        P_lobe_top = C_lobe + Base.Vector(0, 0, r_tip)
        arc_lobe = Part.Arc(P_tan_out, P_lobe_top, P_tan_in).toShape()

        wing_wire = Part.Wire([
            arc_out,
            arc_lobe,
            arc_in,
            Part.LineSegment(P_top, P_bot).toShape(),
        ])
        wing_face = Part.Face(wing_wire)
        wing = wing_face.extrude(Base.Vector(0, C, 0))
        wing.translate(Base.Vector(0, -C/2.0, 0))

        edges_to_fillet = []
        for e in wing.Edges:
            on_mating = True
            for v in e.Vertexes:
                pt = v.Point
                if pt.z < fillet_z - 0.05 or pt.z > G + 0.05:
                    on_mating = False; break
                dz_total = G - fillet_z
                expected_x = (X_bot + (pt.z - fillet_z) * (X_top - X_bot) / dz_total
                              if dz_total > 0 else X_bot)
                if abs(pt.x - expected_x) > 0.05:
                    on_mating = False; break
            if not on_mating:
                edges_to_fillet.append(e)
        if edges_to_fillet:
            wing = _safe_fillet(wing, edges_to_fillet, wing_r)

        shape = shape.fuse(wing)
        wing.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
        shape = shape.fuse(wing)
        try:
            shape = shape.removeSplitter()
        except Exception:
            pass

    # =========================================================================
    # ASMEB18.6.9.2  —  Type A Style 2  (dual tangent sweep)
    # =========================================================================
    elif SType == "ASMEB18.6.9.2":
        approx_inner_rad = dia / 2.0
        overlap = max(0.5, (min(D/2.0, E/2.0) - approx_inner_rad) * 0.45)

        fm_boss = FSFaceMaker()
        fm_boss.AddPoint(0.0,   0.0)
        fm_boss.AddPoint(E/2.0, 0.0)
        fm_boss.AddPoint(D/2.0, G)
        fm_boss.AddPoint(0.0,   G)
        boss = self.RevolveZ(fm_boss.GetFace())
        try:
            circ_edges = [ed for ed in boss.Edges if _curve_is(ed, Part.Circle)]
            if circ_edges:
                boss = _safe_fillet(boss, circ_edges, P / 2.0)
        except Exception:
            pass
        shape = boss

        r_tip = G / 2.0
        r_bot = B * 0.8
        r_top = A * 0.6
        C_lobe = Base.Vector(A/2.0 - r_tip, 0.0, B - r_tip)
        fillet_z = P / 2.0

        R_bot_fillet = ((E/2.0) - fillet_z * ((E/2.0) - (D/2.0)) / G
                        if G > 0 else E/2.0)

        val_bot = R_bot_fillet**2 - (C/2.0)**2
        val_top = (D/2.0)**2      - (C/2.0)**2
        X_bot = math.sqrt(val_bot if val_bot > 0 else 0) - overlap
        X_top = math.sqrt(val_top if val_top > 0 else 0) - overlap

        P_bot = Base.Vector(X_bot, 0.0, fillet_z)
        P_top = Base.Vector(X_top, 0.0, G)

        def get_tangent_arc_data(p_fixed, r_arc, center_tip, r_tip_val,
                                 maximize='z'):
            x0, y0 = center_tip.x, center_tip.z
            x1, y1 = p_fixed.x,    p_fixed.z
            d = math.sqrt((x1-x0)**2 + (y1-y0)**2)
            if d > r_tip_val + r_arc:
                r_arc = (d - r_tip_val) * 1.001
            r0 = r_tip_val + r_arc
            a  = (r0**2 - r_arc**2 + d**2) / (2*d) if d != 0 else 0
            val = r0**2 - a**2
            h  = math.sqrt(val if val > 0 else 0)
            x2 = x0 + a*(x1-x0)/d if d != 0 else x0
            y2 = y0 + a*(y1-y0)/d if d != 0 else y0
            rx = -h*(y1-y0)/d if d != 0 else 0
            ry =  h*(x1-x0)/d if d != 0 else 0
            c_A = Base.Vector(x2+rx, 0.0, y2+ry)
            c_B = Base.Vector(x2-rx, 0.0, y2-ry)
            ca  = ((c_A if c_A.z > c_B.z else c_B) if maximize == 'z'
                   else (c_A if c_A.x > c_B.x else c_B))
            v  = center_tip - ca
            if v.Length == 0: v = Base.Vector(1, 0, 0)
            v.normalize()
            p_tan = ca + v * r_arc
            v1 = p_fixed - ca;  v1 = v1 / v1.Length if v1.Length else Base.Vector(1,0,0)
            v2 = p_tan   - ca;  v2 = v2 / v2.Length if v2.Length else Base.Vector(1,0,0)
            vm = v1 + v2
            if vm.Length == 0: vm = Base.Vector(0, 1, 0)
            vm.normalize()
            return p_tan, ca + vm * r_arc

        p_tan_top, p_mid_top = get_tangent_arc_data(P_top, r_top, C_lobe, r_tip, 'z')
        p_tan_bot, p_mid_bot = get_tangent_arc_data(P_bot, r_bot, C_lobe, r_tip, 'x')
        P_tip_outer = Base.Vector(C_lobe.x + r_tip, 0.0, C_lobe.z)

        wing_wire = Part.Wire([
            Part.Arc(P_bot,      p_mid_bot,   p_tan_bot).toShape(),
            Part.Arc(p_tan_bot,  P_tip_outer, p_tan_top).toShape(),
            Part.Arc(p_tan_top,  p_mid_top,   P_top).toShape(),
            Part.LineSegment(P_top, P_bot).toShape(),
        ])
        wing_face = Part.Face(wing_wire)
        wing = wing_face.extrude(Base.Vector(0, C, 0))
        wing.translate(Base.Vector(0, -C/2.0, 0))

        edges_to_fillet = []
        for e in wing.Edges:
            on_mating = True
            for v in e.Vertexes:
                pt = v.Point
                if pt.z < fillet_z - 0.05 or pt.z > G + 0.05:
                    on_mating = False; break
                dz_total = G - fillet_z
                expected_x = (X_bot + (pt.z - fillet_z) * (X_top - X_bot) / dz_total
                              if dz_total > 0 else X_bot)
                if abs(pt.x - expected_x) > 0.05:
                    on_mating = False; break
            if not on_mating:
                edges_to_fillet.append(e)
        if edges_to_fillet:
            wing = _safe_fillet(wing, edges_to_fillet, wing_r)

        shape = shape.fuse(wing)
        wing.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
        shape = shape.fuse(wing)
        try:
            shape = shape.removeSplitter()
        except Exception:
            pass

    # =========================================================================
    # DIN315 & ASMEB18.6.9A  —  standard wing gen
    # =========================================================================
    else:
        fm = FSFaceMaker()
        fm.AddPoint(0.0,    0.0)
        fm.AddPoint(d2/2,   0.0)
        fm.AddPoint(d3/2,   m)
        fm.AddPoint(0.0,    m)
        shape = self.RevolveZ(fm.GetFace())
        shape = _safe_fillet(shape, list(shape.Edges), P / 2)

        fm.Reset()
        fm.AddPoint(d2/4, g * 0.75)
        fm.AddPoint(d2/4 + (h - g*0.75) * math.tan(math.radians(20)), h)
        fm.AddArc(0.375*e, 0.95*h, e/2, 0.8*h)
        fm.AddArc((d2+e)/4, 0.25*h, d2/4, g/4)
        wing = fm.GetFace().extrude(Base.Vector(0.0, g, 0.0))
        wing.translate(Base.Vector(0.0, -g/2, 0.0))
        wing = _safe_fillet(wing, list(wing.Edges), wing_r)
        shape = shape.fuse(wing)
        wing.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
        shape = shape.fuse(wing)

    # =========================================================================
    # BORE RADIUS  (thread-class-aware, with fallback)
    # =========================================================================
    inner_rad = None
    try:
        if not is_asme and _TMI is not None:
            _ds = str(getattr(fa, "calc_diam",       "") or "")
            _ps = str(getattr(fa, "Thread_Pitch_Nut","") or "")
            if not _ps:
                _pm = _TMI.resolve_nut_pitch(fa)
                _ps = str(_pm) if _pm else ""
            if _ps:
                inner_rad = _TMI.bore_dia_from_table(
                    fa, _ds, _ps,
                    str(getattr(fa, "Thread_Class_Nut", "") or "6H")) / 2.0
        elif is_asme and _TAI is not None:
            _ds = str(getattr(fa, "calc_diam",        "") or "")
            _tp = str(getattr(fa, "Thread_TPI_Nut",   "") or "")
            if not _tp:
                _tv = _TAI.resolve_nut_tpi(fa)
                _tp = str(_tv) if _tv else ""
            if _tp:
                inner_rad = _TAI.bore_dia_from_table(
                    fa, _ds, _tp,
                    str(getattr(fa, "Thread_Type_Nut",      "UNC") or "UNC"),
                    str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")) / 2.0
    except Exception:
        pass

    if inner_rad is None:
        try:
            sqrt3_val = sqrt3
        except NameError:
            sqrt3_val = 1.73205
        inner_rad = dia / 2.0 - P * 0.625 * sqrt3_val / 2.0

    # ── Clamp bore inside body wall ───────────────────────────────────────────
    body_wall_dia = (min(d2, d3)
                     if SType in ["ASMEB18.6.9.3", "ASMEB18.6.9.2",
                                  "ASMEB18.6.9.4A", "ASMEB18.6.9.4B",
                                  "ASMEB18.6.9.4",  "ASMEB18.6.9.6"]
                     else d2)
    do = min(dia * 1.1, body_wall_dia - P)

    if do < inner_rad * 2.0 + P:
        inner_rad = max((do - P) / 2.0, inner_rad * 0.5)

    cham_val      = (do / 2.0 - inner_rad) * math.tan(math.radians(15))
    inner_cham_ht = min(max(cham_val, 0.0), m * 0.20)

    # ── Bore cutter ───────────────────────────────────────────────────────────
    fm = FSFaceMaker()
    fm.AddPoint(0.0,          0.0)
    fm.AddPoint(do / 2,       0.0)
    fm.AddPoint(inner_rad,    inner_cham_ht)
    fm.AddPoint(inner_rad,    m - inner_cham_ht)
    fm.AddPoint(do / 2,       m)
    fm.AddPoint(0.0,          m)
    shape = shape.cut(self.RevolveZ(fm.GetFace()))

    # ── Thread cutter ─────────────────────────────────────────────────────────
    if fa.Thread:
        if is_asme:
            tpi = None
            if _TAI is not None:
                try:
                    tpi = _TAI.resolve_nut_tpi(fa)
                except Exception:
                    pass
            tpi = tpi if (tpi and tpi > 0) else (25.4 / P if P > 0 else 8.0)
            shape = shape.cut(
                self.CreateInnerThreadCutter(dia + 0.05 / tpi, P, m + P))
        else:
            tc = self.CreateInnerThreadCutter(
                do, P, (m - 2.0 * inner_cham_ht) + P)
            tc.translate(Base.Vector(0.0, 0.0, inner_cham_ht))
            shape = shape.cut(tc)

    return shape