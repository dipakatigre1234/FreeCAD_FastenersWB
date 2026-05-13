# -*- coding: utf-8 -*-
from screw_maker import *
import FastenerBase
import sys as _sys_wn, os as _os_wn
_wb_wn = _os_wn.path.dirname(_os_wn.path.dirname(_os_wn.path.abspath(__file__)))
if _wb_wn not in _sys_wn.path:
    _sys_wn.path.insert(0, _wb_wn)
import FSThreadingMetricInternal as _TMI
import FSThreadingASMEInternal as _TAI



def makeWingNut(self, fa):
    """Wing nut generator — DIN 315 and ASME B18.6.9A."""
    SType   = fa.baseType
    is_asme = SType.startswith("ASME")
    dia     = self.getDia(fa.calc_diam, True)

    # --- Dimension unpacking ---
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
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.Type}")

    # --- Pitch resolution ---
    if not is_asme and _TMI is not None:
        _p = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
        try:    P = float(_p) if _p else (fa.calc_pitch if (getattr(fa, "calc_pitch", None) or 0) > 0 else P)
        except: pass
    else:
        if (getattr(fa, "calc_pitch", None) or 0) > 0: P = fa.calc_pitch
        if is_asme and _TAI is not None:
            try:
                tpi = _TAI.resolve_nut_tpi(fa)
                if tpi and tpi > 0: P = 25.4 / tpi
            except: pass

    # --- Main body ---
    fm = FSFaceMaker()
    fm.AddPoint(0.0, 0.0); fm.AddPoint(d2/2, 0.0)
    fm.AddPoint(d3/2, m);  fm.AddPoint(0.0, m)
    shape = self.RevolveZ(fm.GetFace())
    shape = shape.makeFillet(P/2, shape.Edges)

    # --- Wings ---
    fm.Reset()
    fm.AddPoint(d2/4, g*0.75)
    fm.AddPoint(d2/4 + (h - g*0.75) * math.tan(math.radians(20)), h)
    fm.AddArc(0.375*e, 0.95*h, e/2, 0.8*h)
    fm.AddArc((d2+e)/4, 0.25*h, d2/4, g/4)
    wing = fm.GetFace().extrude(Base.Vector(0.0, g, 0.0))
    wing.translate(Base.Vector(0.0, -g/2, 0.0))
    wing = wing.makeFillet(wing_r, wing.Edges)
    shape = shape.fuse(wing)
    wing.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 180)
    shape = shape.fuse(wing)

    # --- Bore radius (thread-class-aware, with fallback) ---
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
                    fa, _ds, _ps, str(getattr(fa, "Thread_Class_Nut", "") or "6H")) / 2.0
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
    except: pass
    if inner_rad is None:
        inner_rad = dia/2.0 - P*0.625*sqrt3/2.0

    # --- Clamp 'do' inside body wall; shrink inner_rad if needed ---
    do = min(dia*1.1, d2/2.0 - P)
    if do < inner_rad*2.0 + P:
        inner_rad = max((do - P)/2.0, inner_rad*0.5)

    # --- Chamfer height capped at 20 % of nut height ---
    inner_cham_ht = min((do/2.0 - inner_rad) * math.tan(math.radians(15)), m*0.20)

    # --- Bore cutter ---
    fm.Reset()
    fm.AddPoint(0.0, 0.0);               fm.AddPoint(do/2, 0.0)
    fm.AddPoint(inner_rad, inner_cham_ht)
    fm.AddPoint(inner_rad, m - inner_cham_ht)
    fm.AddPoint(do/2, m);                fm.AddPoint(0.0, m)
    shape = shape.cut(self.RevolveZ(fm.GetFace()))

    # --- Thread cutter ---
    if fa.Thread:
        if is_asme:
            tpi = None
            if _TAI is not None:
                try: tpi = _TAI.resolve_nut_tpi(fa)
                except: pass
            tpi = tpi if (tpi and tpi > 0) else (25.4/P if P > 0 else 8.0)
            shape = shape.cut(self.CreateInnerThreadCutter(dia + 0.05/tpi, P, m + P))
        else:
            # DIN315: use 'do' (actual bore dia) so cutter matches the drilled hole.
            # Offset by inner_cham_ht to cut only the cylindrical bore section.
            tc = self.CreateInnerThreadCutter(do, P, (m - 2.0*inner_cham_ht) + P)
            tc.translate(Base.Vector(0.0, 0.0, inner_cham_ht))
            shape = shape.cut(tc)

    return shape