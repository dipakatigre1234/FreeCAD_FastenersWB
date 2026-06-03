# -*- coding: utf-8 -*-
from screw_maker import *
import FastenerBase
import sys as _sys_wn, os as _os_wn
import math
import Part
from FreeCAD import Base

_wb_wn = _os_wn.path.dirname(_os_wn.path.dirname(_os_wn.path.abspath(__file__)))
if _wb_wn not in _sys_wn.path:
    _sys_wn.path.insert(0, _wb_wn)
import FSThreadingMetricInternal as _TMI
import FSThreadingASMEInternal as _TAI


def makeWingNut(self, fa):
    """Wing nut generator — DIN 315, ASME B18.6.9A, and ASME B18.6.9.3."""
    SType   = fa.baseType
    is_asme = SType.startswith("ASME")
    dia     = self.getDia(fa.calc_diam, True)

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

    elif SType == "ASMEB18.6.9.3":
        TPI, A_max, A_min, B_max, B_min, C_max, C_min, \
            D_max, D_min, E_max, E_min, G_max, G_min = fa.dimTable
        def avg(a, b): return (a + b) / 2 * 25.4
        P = 25.4 / TPI
        A = avg(A_max, A_min)   # overall wing span
        B = avg(B_max, B_min)   # overall height
        C = avg(C_max, C_min)   # wing thickness
        D = avg(D_max, D_min)   # body top OD
        E = avg(E_max, E_min)   # body base OD
        G = avg(G_max, G_min)   # body (nut) height
        d2 = D
        d3 = E
        m  = G
        g  = C
        h  = B
        e  = A
        wing_r = g / 5

    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    # ── Pitch resolution ──────────────────────────────────────────────────────
    if not is_asme and _TMI is not None:
        _p = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
        try:
            P = float(_p) if _p else (fa.calc_pitch if (getattr(fa, "calc_pitch", None) or 0) > 0 else P)
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

    # ── Main body + wings ─────────────────────────────────────────────────────
    if SType == "ASMEB18.6.9.3":
        overlap = 0.05
        fm_boss = FSFaceMaker()
        fm_boss.AddPoint(0.0, 0.0)
        fm_boss.AddPoint(E / 2.0, 0.0)
        fm_boss.AddPoint(D / 2.0, G)
        fm_boss.AddPoint(0.0, G)
        boss = self.RevolveZ(fm_boss.GetFace())
        
        try:
            circ_edges = [ed for ed in boss.Edges if isinstance(ed.Curve, Part.Circle)]
            if circ_edges:
                boss = boss.makeFillet(P / 2.0, circ_edges)
        except Exception:
            pass
        shape = boss

        r_tip = G / 2.0
        C_lobe = Base.Vector(A/2.0 - r_tip, 0.0, B - r_tip)

        # --- NEW AESTHETIC FIX: Stop the wing exactly where the base fillet ends ---
        fillet_z = P / 2.0 
        
        # Calculate the exact radius of the cone at the Z-height where the fillet ends
        if G > 0:
            R_bot_fillet = (E/2.0) - fillet_z * ((E/2.0) - (D/2.0)) / G
        else:
            R_bot_fillet = (E/2.0)

        val_bot = R_bot_fillet**2 - (C/2.0)**2
        val_top = (D/2.0)**2 - (C/2.0)**2
        
        X_bot = math.sqrt(val_bot if val_bot > 0 else 0) - overlap
        X_top = math.sqrt(val_top if val_top > 0 else 0) - overlap

        # The wing now starts at `fillet_z` instead of `0.0`
        P_bot = Base.Vector(X_bot, 0.0, fillet_z)
        P_top = Base.Vector(X_top, 0.0, G)
        # ---------------------------------------------------------------------------

        def get_tangent_sweep_arc(P_start, center_lobe, radius_lobe, angle_deg, reverse=False):
            ang = math.radians(angle_deg)
            u = Base.Vector(math.cos(ang), 0.0, math.sin(ang))
            P_tan = center_lobe + u * radius_lobe
            D_vec = P_tan - P_start
            dot_prod = D_vec.x * u.x + D_vec.z * u.z
            if dot_prod == 0: dot_prod = 1e-6
            R_sweep = - (D_vec.Length**2) / (2.0 * dot_prod)
            C_sweep = P_tan + u * R_sweep
            V1 = P_start - C_sweep
            V2 = P_tan - C_sweep
            V_mid = (V1 + V2)
            V_mid.normalize()
            P_mid = C_sweep + V_mid * R_sweep
            if reverse: return Part.Arc(P_tan, P_mid, P_start).toShape(), P_tan
            else: return Part.Arc(P_start, P_mid, P_tan).toShape(), P_tan

        def get_user_radius_arc(P_start, center_lobe, r_tip, R_user):
            x1, z1 = P_start.x, P_start.z
            x2, z2 = center_lobe.x, center_lobe.z
            d = math.sqrt((x2-x1)**2 + (z2-z1)**2)
            min_R = (d - r_tip) / 2.0
            if R_user < min_R: R_user = min_R * 1.001
            val = (d**2 + R_user**2 - (R_user + r_tip)**2) / (2 * d * R_user)
            cos_theta = max(-1.0, min(1.0, val))
            theta = math.acos(cos_theta)
            alpha = math.atan2(z2-z1, x2-x1)
            angle_c = alpha + theta
            C_arc = Base.Vector(x1 + R_user * math.cos(angle_c), 0.0, z1 + R_user * math.sin(angle_c))
            V_tan = center_lobe - C_arc
            if V_tan.Length == 0: V_tan = Base.Vector(1,0,0)
            V_tan.normalize()
            P_tan = C_arc + V_tan * R_user
            V_start = P_start - C_arc
            V_end = P_tan - C_arc
            V_mid = V_start + V_end
            if V_mid.Length == 0: V_mid = Base.Vector(0,1,0)
            V_mid.normalize()
            P_mid = C_arc + V_mid * R_user
            return Part.Arc(P_tan, P_mid, P_start).toShape(), P_tan

        arc_out, P_tan_out = get_tangent_sweep_arc(P_bot, C_lobe, r_tip, -35, False)
        arc_in, P_tan_in = get_user_radius_arc(P_top, C_lobe, r_tip, A)
        P_lobe_top = C_lobe + Base.Vector(0, 0, r_tip)
        arc_lobe = Part.Arc(P_tan_out, P_lobe_top, P_tan_in).toShape()

        wing_wire = Part.Wire([
            arc_out,
            arc_lobe,
            arc_in,
            Part.LineSegment(P_top, P_bot).toShape()
        ])

        wing_face = Part.Face(wing_wire)
        wing = wing_face.extrude(Base.Vector(0, C, 0))
        wing.translate(Base.Vector(0, -C/2.0, 0))
        
        # --- Adjusted Edge Filter to protect the newly shifted face ---
        edges_to_fillet = []
        for e in wing.Edges:
            on_mating_face = True
            for v in e.Vertexes:
                pt = v.Point
                
                # Check if point falls vertically outside our new mating face
                if pt.z < fillet_z - 0.05 or pt.z > G + 0.05:
                    on_mating_face = False
                    break
                
                # Check if point lies on the slanted profile of the cone
                dz = pt.z - fillet_z
                dz_total = G - fillet_z
                expected_x = X_bot + dz * (X_top - X_bot) / dz_total if dz_total > 0 else X_bot
                
                if abs(pt.x - expected_x) > 0.05:
                    on_mating_face = False
                    break
            
            if not on_mating_face:
                edges_to_fillet.append(e)

        try:
            if edges_to_fillet:
                wing = wing.makeFillet(wing_r, edges_to_fillet)
        except Exception:
            pass
        # --------------------------------------------------------------

        shape = shape.fuse(wing)
        wing.rotate(Base.Vector(0,0,0), Base.Vector(0,0,1), 180)
        shape = shape.fuse(wing)

        try:
            shape = shape.removeSplitter()
        except Exception:
            pass

    else:
        # === STANDARD WING GEN (DIN315 & ASMEB18.6.9A) ===
        fm = FSFaceMaker()
        fm.AddPoint(0.0, 0.0)
        fm.AddPoint(d2 / 2, 0.0)
        fm.AddPoint(d3 / 2, m)
        fm.AddPoint(0.0, m)
        shape = self.RevolveZ(fm.GetFace())
        try:
            shape = shape.makeFillet(P / 2, shape.Edges)
        except Exception:
            pass

        fm.Reset()
        fm.AddPoint(d2 / 4, g * 0.75)
        fm.AddPoint(d2 / 4 + (h - g * 0.75) * math.tan(math.radians(20)), h)
        fm.AddArc(0.375 * e, 0.95 * h, e / 2, 0.8 * h)
        fm.AddArc((d2 + e) / 4, 0.25 * h, d2 / 4, g / 4)
        wing = fm.GetFace().extrude(Base.Vector(0.0, g, 0.0))
        wing.translate(Base.Vector(0.0, -g / 2, 0.0))
        try:
            wing = wing.makeFillet(wing_r, wing.Edges)
        except Exception:
            pass
        shape = shape.fuse(wing)
        wing.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
        shape = shape.fuse(wing)

    # ── Bore radius (thread-class-aware, with fallback) ───────────────────────
    inner_rad = None
    try:
        if not is_asme and _TMI is not None:
            _ds = str(getattr(fa, "calc_diam", "") or "")
            _ps = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
            if not _ps:
                _pm = _TMI.resolve_nut_pitch(fa)
                _ps = str(_pm) if _pm else ""
            if _ps:
                inner_rad = _TMI.bore_dia_from_table(
                    fa, _ds, _ps,
                    str(getattr(fa, "Thread_Class_Nut", "") or "6H")) / 2.0
        elif is_asme and _TAI is not None:
            _ds = str(getattr(fa, "calc_diam", "") or "")
            _tp = str(getattr(fa, "Thread_TPI_Nut", "") or "")
            if not _tp:
                _tv = _TAI.resolve_nut_tpi(fa)
                _tp = str(_tv) if _tv else ""
            if _tp:
                inner_rad = _TAI.bore_dia_from_table(
                    fa, _ds, _tp,
                    str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC"),
                    str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")) / 2.0
    except Exception:
        pass

    if inner_rad is None:
        try:
            sqrt3_val = sqrt3
        except NameError:
            sqrt3_val = 1.73205
        inner_rad = dia / 2.0 - P * 0.625 * sqrt3_val / 2.0

    # ── Clamp bore inside body wall (Fixed Diameter Math) ─────────────────────
    body_wall_dia = min(d2, d3) if SType == "ASMEB18.6.9.3" else d2
    do = min(dia * 1.1, body_wall_dia - P)

    if do < inner_rad * 2.0 + P:
        inner_rad = max((do - P) / 2.0, inner_rad * 0.5)

    cham_val = (do / 2.0 - inner_rad) * math.tan(math.radians(15))
    inner_cham_ht = min(max(cham_val, 0.0), m * 0.20)

    # ── Bore cutter ───────────────────────────────────────────────────────────
    fm = FSFaceMaker()
    fm.AddPoint(0.0, 0.0)
    fm.AddPoint(do / 2, 0.0)
    fm.AddPoint(inner_rad, inner_cham_ht)
    fm.AddPoint(inner_rad, m - inner_cham_ht)
    fm.AddPoint(do / 2, m)
    fm.AddPoint(0.0, m)
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
            tc = self.CreateInnerThreadCutter(do, P, (m - 2.0 * inner_cham_ht) + P)
            tc.translate(Base.Vector(0.0, 0.0, inner_cham_ht))
            shape = shape.cut(tc)

    return shape