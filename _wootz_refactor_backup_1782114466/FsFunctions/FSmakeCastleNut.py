# -*- coding: utf-8 -*-
"""
***************************************************************************
*   Copyright (c) 2022                                                    *
*   Alex Neufeld <alex.d.neufeld@gmail.com>                               *
*                                                                         *
*   This file is a supplement to the FreeCAD CAx development system.      *
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU Lesser General Public License (LGPL)    *
*   as published by the Free Software Foundation; either version 2 of     *
*   the License, or (at your option) any later version.                   *
*   for detail see the LICENCE text file.                                 *
*                                                                         *
*   This software is distributed in the hope that it will be useful,      *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
*   GNU Library General Public License for more details.                  *
*                                                                         *
*   You should have received a copy of the GNU Library General Public     *
*   License along with this macro; if not, write to the Free Software     *
*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
*   USA                                                                   *
*                                                                         *
***************************************************************************
"""
from screw_maker import *
import Part
import re
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None
try:
    import FSThreadingASMEInternal as _TAI
except Exception:
    _TAI = None

def _resolve_asme_nut_thread(fa, P_fallback):
    """Return (tpi, pitch_mm) for ASME nut threading from dashboard properties."""
    tpi = None
    if _TAI is not None:
        try:
            tpi = _TAI.resolve_nut_tpi(fa)
        except Exception:
            tpi = None
    if not tpi or tpi <= 0:
        tpi = 25.4 / P_fallback if P_fallback > 0 else 8.0
    return tpi, (25.4 / tpi if tpi > 0 else P_fallback)

def _cut_asme_nut_thread(self, shape, fa, dia, depth, P_fallback):
    """Apply ASME internal thread cut using dashboard thread parameters."""
    tpi, P_thread = _resolve_asme_nut_thread(fa, P_fallback)
    bore_eff = None

    # Apply ASME bore (class/type/TPI aware) before helix cutter.
    if _TAI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _tpi_s = str(getattr(fa, "Thread_TPI_Nut", "") or "")
            _type_s = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
            _cls_s = str(getattr(fa, "Thread_Class_Nut_ASME", "2B") or "2B")
            if (_tpi_s == "Custom" or not _tpi_s):
                _tpi_s = str(tpi)
            bore_eff = _TAI.bore_dia_from_table(fa, _dia_s, _tpi_s, _type_s, _cls_s)
            bore_cyl = Part.makeCylinder(
                bore_eff / 2.0,
                depth + 2.0 * P_thread,
                Base.Vector(0.0, 0.0, -P_thread),
                Base.Vector(0, 0, 1),
            )
            shape = shape.cut(bore_cyl)
        except Exception:
            pass

    thread_dia = dia + 0.05 / tpi
    thread_cutter = self.CreateInnerThreadCutter(thread_dia, P_thread, depth + P_thread)
    shape = shape.cut(thread_cutter)

    # Final cleanup cut for ASME slotted/castle nuts:
    # removes any small residual material islands left in the thread recess.
    if bore_eff is None:
        bore_eff = max(0.1, dia - 1.0825 * P_thread)
    cleanup_cyl = Part.makeCylinder(
        bore_eff / 2.0,
        depth + 2.0 * P_thread,
        Base.Vector(0.0, 0.0, -P_thread),
        Base.Vector(0, 0, 1),
    )
    return shape.cut(cleanup_cyl)

def _resolve_metric_pitch(fa, P_fallback):
    """Resolve metric nut pitch from dashboard properties with safe fallback."""
    # 1) explicit nut pitch property from dashboard
    try:
        p_prop = str(getattr(fa, "Thread_Pitch_Nut", "") or "").strip()
        if p_prop:
            # Accept values like "1.75", "1,75", "P1.75", "1.75 mm"
            p_txt = p_prop.replace(",", ".")
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", p_txt)
            if m:
                p = float(m.group(0))
                if p > 0:
                    return p
    except Exception:
        pass
    # 2) calc_pitch from dynamic matching logic
    try:
        cp = float(getattr(fa, "calc_pitch", 0.0) or 0.0)
        if cp > 0:
            return cp
    except Exception:
        pass
    # 3) metric internal helper resolution
    if _TMI is not None:
        try:
            rp = _TMI.resolve_nut_pitch(fa)
            if rp and rp > 0:
                return rp
        except Exception:
            pass
    # 4) dimtable fallback
    return P_fallback

def _cut_metric_nut_thread(self, shape, fa, dia, depth, P_fallback):
    """Apply metric internal thread cut using dashboard pitch/class properties."""
    p_metric = _resolve_metric_pitch(fa, P_fallback)

    # Match HexNut behavior: bore diameter should follow metric internal table
    # (Thread_Pitch_Nut + Thread_Class_Nut), so parameter changes affect geometry.
    if _TMI is not None:
        try:
            _dia_s = str(getattr(fa, "calc_diam", "") or "")
            _cls_s = str(getattr(fa, "Thread_Class_Nut", "6H") or "6H")
            _bore_eff = _TMI.bore_dia_from_table(fa, _dia_s, str(p_metric), _cls_s)
            bore_cyl = Part.makeCylinder(
                _bore_eff / 2.0,
                depth + 2.0 * p_metric,
                Base.Vector(0.0, 0.0, -p_metric),
                Base.Vector(0, 0, 1),
            )
            shape = shape.cut(bore_cyl)
        except Exception:
            pass

    thread_dia = dia + 0.05 * p_metric
    thread_cutter = self.CreateInnerThreadCutter(thread_dia, p_metric, depth + p_metric)
    return shape.cut(thread_cutter)


# ═══════════════════════════════════════════════════════════════════════════
# Top-level entry points — one per screwTables function name
# ═══════════════════════════════════════════════════════════════════════════

def makeSlottedNut(self, fa):
    """Slotted nut: full hex body with slots cut directly into the hex.

    Registered types:
        DIN935          — DIN 935 slotted nuts (all sizes M4–M100)
        ASMEB18.2.2.6   — ASME B18.2.2 Table 6 hex slotted thin nuts
        ASMEB18.2.2.8   — ASME B18.2.2 Table 8 hex slotted wide nuts
    """
    return _makeSlottedNut(self, fa)


def makeCastleNut(self, fa):
    """Castle nut: hex body + cylindrical crown with slots in the crown.

    Registered types:
        DIN935C         — DIN 935 castle nuts (M12+ only)
        ASMEB18.2.2.15  — ASME B18.2.2 Table 15 hex castle nuts
    """
    return _makeCastleNut(self, fa)


# ═══════════════════════════════════════════════════════════════════════════
# Private geometry implementations
# ═══════════════════════════════════════════════════════════════════════════

def _makeCastleNut(self, fa):
    """Castle nut geometry: hex body (z=0 → z=w) + cylindrical crown (z=w → z=m).

    The hex body has standard 30° washer-face chamfers and bore chamfers.
    The cylindrical crown sits on top of the hex body with OD = d_e_max,
    ID = bore, and slots cut through the crown.

    CSV columns:
      DIN935Cdef (derived from DIN935def at startup):
        P, m, w, s, n, d_e_max, ns
      ASMEB18.2.2.15def:
        TPI, F_max, F_min, G_max, G_min, H_max, H_min,
        T_max, T_min, S_max, S_min, R_max, U_min
    """
    R = 0.0
    if fa.baseType == "DIN935C":
        P, m, w, s, n, d_e_max, ns = fa.dimTable
    elif fa.baseType == "ASMEB18.2.2.15":
        TPI, F_max, F_min, G_max, G_min, H_max, H_min, \
            T_max, T_min, S_max, S_min, R_max, U_min = fa.dimTable
        # Map ASME dimensions into DIN-style geometry inputs
        P = 25.4 / TPI
        m = (H_max + H_min) / 2
        w = (T_max + T_min) / 2
        s = (F_max + F_min) / 2
        n = (S_max + S_min) / 2
        d_e_max = U_min
        R = R_max
        ns = 6
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.baseType}")

    dia = self.getDia(fa.calc_diam, True)
    inner_rad = dia / 2 - P * 0.625 * sqrt3 / 2      # thread minor radius

    outer_rad = 0.505 * dia
    inner_cham_ht = tan15 * (outer_rad - inner_rad)    # bore chamfer height

    crown_r = d_e_max / 2          # crown outer radius

    # ── 1.  Hex body (z = 0 → z = w) ────────────────────────────────
    fm = FSFaceMaker()
    fm.AddPoint(inner_rad, inner_cham_ht)       # bottom bore chamfer start
    fm.AddPoint(outer_rad, 0.0)                 # bottom bore chamfer end
    fm.AddPoint(s / 2, 0.0)                     # outer bottom edge
    fm.AddPoint(s / 2 + w * sqrt3 / 2, w / 2)  # 30° chamfer peak at mid-height
    fm.AddPoint(s / 2, w)                       # outer top edge
    fm.AddPoint(outer_rad, w)                   # inner top (crown starts here)
    fm.AddPoint(inner_rad, w)                   # bore at top of hex body
    hex_profile = self.RevolveZ(fm.GetFace())
    hex_body = hex_profile.common(self.makeHexPrism(s, w))

    # ── 2.  Cylindrical crown (z = w → z = m) ───────────────────────
    fm.Reset()
    fm.AddPoint(inner_rad, m - inner_cham_ht)   # top bore chamfer start
    fm.AddPoint(outer_rad, m)                   # top bore chamfer end
    fm.AddPoint(crown_r, m)                     # crown outer top
    fm.AddPoint(crown_r, w)                     # crown outer bottom
    fm.AddPoint(outer_rad, w)                   # bore at crown bottom
    fm.AddPoint(inner_rad, w)                   # bore inner at crown bottom
    crown = self.RevolveZ(fm.GetFace())

    # ── 3.  Fuse hex body + crown ────────────────────────────────────
    shape = hex_body.fuse(crown)

    # For ASME B18.2.2.15, apply R_max on the OUTSIDE circular shoulder edge
    # (between upper cylinder wall and top hex face ring).
    if fa.baseType == "ASMEB18.2.2.15" and R > 0:
        R_eff = max(0.0, min(R, (m - w) * 0.49, max(0.0, crown_r - outer_rad) * 0.49))
        if R_eff > 0.001:
            ring_edges = []
            for e in shape.Edges:
                c = getattr(e, "Curve", None)
                if not isinstance(c, Part.Circle):
                    continue
                # Target: external shoulder circle at z ~= w and radius ~= crown_r
                if abs(c.Radius - crown_r) < 1e-3 and abs(c.Center.z - w) < 1e-3:
                    ring_edges.append(e)
            if ring_edges:
                try:
                    shape = shape.makeFillet(R_eff, ring_edges)
                except Exception:
                    pass

    # ── 4.  Cut slots into the crown ─────────────────────────────────
    fm.Reset()
    fm.AddPoint(-n / 2, m)
    fm.AddPoint(-n / 2, w + n / 2)
    fm.AddArc2(n / 2, 0.0, 180)
    fm.AddPoint(n / 2, m)
    slot_cutter = fm.GetFace().extrude(Base.Vector(0.0, 1.2 * s, 0))
    slot_cutter.translate(Base.Vector(0.0, -0.6 * s, 0.05 * P))

    for i in range(int(ns / 2)):
        slot_cutter.rotate(
            Base.Vector(0.0, 0.0, 0.0),
            Base.Vector(0.0, 0.0, 1.0),
            360 / ns,
        )
        shape = shape.cut(slot_cutter)

    # ── 5.  Internal thread (optional) ───────────────────────────────
    if fa.Thread:
        if fa.baseType == "ASMEB18.2.2.15":
            shape = _cut_asme_nut_thread(self, shape, fa, dia, m, P)
        else:
            shape = _cut_metric_nut_thread(self, shape, fa, dia, m, P)

    return shape


def _makeSlottedNut(self, fa):
    """Slotted nut geometry: full hex body with slots cut directly into it.

    Used for:
        DIN 935   — All sizes (M4–M100), slotted geometry
        ASME B18.2.2 Table 6 & 8 — hex slotted thin/wide nuts
    """
    if fa.baseType == "DIN935":
        P, m, w, s, n, d_e_max, ns = fa.dimTable
    elif fa.baseType in ("ASMEB18.2.2.6", "ASMEB18.2.2.8"):
        TPI, F_max, F_min, G_max, G_min, H_max, H_min, \
            T_max, T_min, S_max, S_min = fa.dimTable
        P = 1 / TPI * 25.4
        m = (H_max + H_min) / 2
        w = (T_max + T_min) / 2
        s = (F_max + F_min) / 2
        n = (S_max + S_min) / 2
        ns = 6
    else:
        raise NotImplementedError(f"Unknown fastener type: {fa.baseType}")

    dia = self.getDia(fa.calc_diam, True)
    inner_rad = dia / 2 - P * 0.625 * sqrt3 / 2
    outer_rad = 0.505 * dia
    inner_cham_ht = tan15 * (outer_rad - inner_rad)

    # ── 1.  Full hex body (z = 0 → z = m) ───────────────────────────
    fm = FSFaceMaker()
    fm.AddPoint(inner_rad, m - inner_cham_ht)
    fm.AddPoint(outer_rad, m)
    fm.AddPoint(s / 2, m)
    fm.AddPoint(s / 2 + m * sqrt3 / 2, m / 2)
    fm.AddPoint(s / 2, 0.0)
    fm.AddPoint(outer_rad, 0.0)
    fm.AddPoint(inner_rad, inner_cham_ht)
    shape = self.RevolveZ(fm.GetFace())
    shape = shape.common(self.makeHexPrism(s, m))

    # ── 2.  Cut slots ────────────────────────────────────────────────
    fm.Reset()
    fm.AddPoint(-n / 2, m)
    fm.AddPoint(-n / 2, w + n / 2)
    fm.AddArc2(n / 2, 0.0, 180)
    fm.AddPoint(n / 2, m)
    slot_cutter = fm.GetFace().extrude(Base.Vector(0.0, 1.2 * s, 0))
    slot_cutter.translate(Base.Vector(0.0, -0.6 * s, 0.0))

    for i in range(int(ns / 2)):
        slot_cutter.rotate(
            Base.Vector(0.0, 0.0, 0.0),
            Base.Vector(0.0, 0.0, 1.0),
            360 / ns,
        )
        shape = shape.cut(slot_cutter)

    # ── 3.  Internal thread (optional) ───────────────────────────────
    if fa.Thread:
        if fa.baseType in ("ASMEB18.2.2.6", "ASMEB18.2.2.8"):
            shape = _cut_asme_nut_thread(self, shape, fa, dia, m, P)
        else:
            shape = _cut_metric_nut_thread(self, shape, fa, dia, m, P)

    return shape
