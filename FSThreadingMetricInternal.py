# -*- coding: utf-8 -*-
"""
FSThreadingMetricInternal.py — ISO metric INTERNAL thread module (nuts)
========================================================================
Responsibilities:
  1. Load metric_internal_thread_dia.csv (ISO 965-6-2025  D1max values)
  2. Table query helpers for FastenersCmd dashboard dropdowns
  3. Bore diameter with deviation (D1max + deviation)
  4. Cut ISO metric internal threads into a FreeCAD nut shape

NOT responsible for: hex geometry, nut height (m), chamfer, s, da.
Those stay in FSmakeHexNut.py.

Public API
----------
  valid_pitches_for_dia(dia_str)                -> list[str]
  valid_classes_for_dia_pitch(dia_str, p_str)   -> list[str]
  bore_dia_from_table(fa, dia_str, p_str, cls)  -> float mm  (D1max + deviation)
  set_nut_thread_visibility(fp, thread_on)      -> None
  cut_internal_thread(shape, fa, dia, depth, P) -> shape

Deviation system (bore — D1max PLUS deviation)
----------------------------------------------
Internal thread bore = D1max from CSV  +  small positive deviation.

Unlike the bolt (which SUBTRACTS from d_raw to make the shank thinner),
the nut bore ADDS a small amount to D1max so the bore is slightly wider
than the ISO minimum — this gives easier assembly and accounts for
real-world tap geometry while staying within the tolerance class limits.

  bore_eff  =  D1max  +  (D1max × pct / 100)

Deviation scales with diameter:
  Small nuts  (M1   ≈  1 mm)  →  DEVIATION_PCT_SMALL  (larger addition)
  Large nuts  (M300 ≈ 300 mm) →  DEVIATION_PCT_LARGE  (smaller addition)
  In between  →  linearly interpolated

Typical values per ISO 965 tolerance band analysis:
  M1    →  +1.00 % of D1max  (very small, tap wander matters)
  M6    →  +0.80 %
  M16   →  +0.60 %
  M48   →  +0.45 %
  M100+ →  +0.30 %

↓↓ Change only these two values — dia bounds read from CSV ↓↓
BORE_DEVIATION_PCT_SMALL = 1.0   # % ADDED at smallest dia in CSV
BORE_DEVIATION_PCT_LARGE = 0.3   # % ADDED at largest  dia in CSV
"""

import os as _os, math as _math, functools as _functools
_sqrt3 = _math.sqrt(3.0)

_CSV_DIR      = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "FsData")
_CSV_INTERNAL = _os.path.join(_CSV_DIR, "metric_internal_thread_dia.csv")

# ── Bore deviation (percentage, diameter-dependent) ───────────────────────────
#
# D1max from CSV is the ISO maximum minor diameter for the chosen class.
# A small positive deviation is ADDED to give real-world bore clearance.
#
# bore_eff = D1max + (D1max × pct / 100)
#
# BORE_DEVIATION_PCT_SMALL  →  applied at the smallest diameter in the CSV
# BORE_DEVIATION_PCT_LARGE  →  applied at the largest  diameter in the CSV
# In between                →  linearly interpolated by _interpolated_deviation_pct()
#
# Typical bore deviation guidance (ISO 965 / manufacturing practice):
#   M1   :  +1.00 %  — very small taps flex; extra clearance critical
#   M3   :  +0.90 %
#   M6   :  +0.80 %
#   M12  :  +0.65 %
#   M24  :  +0.50 %
#   M48  :  +0.40 %
#   M100 :  +0.33 %
#   M300 :  +0.30 %  — large nuts use precision boring, less scatter
#
BORE_DEVIATION_PCT_SMALL = 0.0    # % ADDED at smallest dia in metric_internal_thread_dia.csv
BORE_DEVIATION_PCT_LARGE = 0.0    # % ADDED at largest  dia in metric_internal_thread_dia.csv


# ── Dia bounds (read once from CSV) ──────────────────────────────────────────

def _internal_dia_bounds_mm():
    """Return (min_mm, max_mm) from CSV Dia_mm column. Falls back to (1.0, 300.0)."""
    import csv
    mm_vals = []
    try:
        with open(_CSV_INTERNAL, newline="", encoding="utf-8") as f:
            lines = f.readlines()
        for row in csv.DictReader(lines[1:]):
            try:
                mm_vals.append(float(str(row["Dia_mm"]).strip()))
            except Exception:
                pass
    except Exception:
        pass
    if len(mm_vals) >= 2:
        return (min(mm_vals), max(mm_vals))
    return (1.0, 300.0)


_BORE_DIA_MIN_MM, _BORE_DIA_MAX_MM = _internal_dia_bounds_mm()


def _interpolated_deviation_pct(dia_mm):
    """Linearly interpolate BORE_DEVIATION_PCT between SMALL (min dia) and LARGE (max dia)."""
    lo, hi = _BORE_DIA_MIN_MM, _BORE_DIA_MAX_MM
    if hi <= lo:
        return BORE_DEVIATION_PCT_SMALL
    t   = max(0.0, min(1.0, (float(dia_mm) - lo) / (hi - lo)))
    return BORE_DEVIATION_PCT_SMALL + t * (BORE_DEVIATION_PCT_LARGE - BORE_DEVIATION_PCT_SMALL)


# ── CSV loader (cached) ───────────────────────────────────────────────────────

@_functools.lru_cache(maxsize=1)
def _internal_table():
    """Return dict keyed (dia_str, pitch_str, class_str) → D1max_mm float.

    CSV structure:
      Row 0 : table name  "Metric_Internal_Thread_D1max_ISO965-6-2025"  ← skip
      Row 1 : headers     Dia_mm, Pitch_mm, Class, D1max_mm
      Row 2+: data

    dia_str and pitch_str are normalised to strip trailing zeros so that
    "6.0" and "6" both hit the same key.
    """
    import csv
    table = {}
    try:
        with open(_CSV_INTERNAL, newline="", encoding="utf-8") as f:
            lines = f.readlines()
        reader = csv.DictReader(lines[1:])   # skip row 0 (table name)
        for row in reader:
            try:
                dia_raw   = str(row["Dia_mm"]).strip()
                pitch_raw = str(row["Pitch_mm"]).strip()
                cls_raw   = str(row["Class"]).strip()
                d1max     = float(row["D1max_mm"])
                dia_key   = _norm(dia_raw)
                p_key     = _norm(pitch_raw)
                table[(dia_key, p_key, cls_raw)] = d1max
            except Exception:
                pass
    except Exception:
        pass
    return table


def _norm(val_str):
    """Normalise a numeric string: strip whitespace, remove trailing zeros.
    "6.0" → "6", "1.00" → "1", "0.75" → "0.75", "1.5" → "1.5"
    """
    try:
        f = float(str(val_str).strip())
        return str(f).rstrip("0").rstrip(".")
    except Exception:
        return str(val_str).strip()


def _dia_key_from_mm(dia_mm):
    """Convert a float mm dia to the normalised CSV key string."""
    return _norm(str(dia_mm))


# ── Dropdown helpers ──────────────────────────────────────────────────────────

def valid_pitches_for_dia(dia_str):
    """Return sorted list of pitch strings (ascending) available for this dia.

    dia_str may be "M6", "6.0", "6" — all normalised to float key.
    """
    dia_clean = dia_str.strip().lstrip("Mm")
    dia_key   = _norm(dia_clean)
    pitches   = sorted(
        {k[1] for k in _internal_table() if k[0] == dia_key},
        key=lambda x: float(x)
    )
    return pitches


def valid_classes_for_dia_pitch(dia_str, pitch_str):
    """Return sorted list of class strings for this dia+pitch.
    Returns e.g. ['4H', '5H', '6G', '6H', '7H'].
    """
    dia_key = _norm(dia_str.strip().lstrip("Mm"))
    p_key   = _norm(str(pitch_str).strip())
    classes = sorted({k[2] for k in _internal_table()
                      if k[0] == dia_key and k[1] == p_key})
    return classes


# ── Bore diameter ─────────────────────────────────────────────────────────────

def d1max_from_table(dia_str, pitch_str, cls_str):
    """Return raw D1max_mm from CSV (NO deviation). Returns None if not found.

    Parameters
    ----------
    dia_str   : nominal diameter string, e.g. "6.0", "M6", "6"
    pitch_str : pitch string mm, e.g. "1.0", "1"
    cls_str   : class string, e.g. "6H", "4H"
    """
    dia_key = _norm(dia_str.strip().lstrip("Mm"))
    p_key   = _norm(str(pitch_str).strip())
    return _internal_table().get((dia_key, p_key, str(cls_str).strip()))


def bore_dia_from_table(fa, dia_str, pitch_str, cls_str):
    """Return bore effective diameter mm = D1max + positive deviation.

    D1max (CSV) → bore_eff = D1max + (D1max × pct/100)

    The deviation makes the bore slightly wider than the ISO D1max value,
    accounting for tap geometry scatter and ensuring the bolt can always
    thread in without binding. Deviation scales with size:
      small nut → BORE_DEVIATION_PCT_SMALL (larger addition)
      large nut → BORE_DEVIATION_PCT_LARGE (smaller addition)

    Falls back to (nominal_mm - 1.0825×P) if not found in CSV.
    """
    d1max = d1max_from_table(dia_str, pitch_str, cls_str)
    try:
        dia_mm = float(str(dia_str).strip().lstrip("Mm"))
    except Exception:
        dia_mm = 6.0

    if d1max is None:
        # Fallback: ISO formula for D1 = nominal - 1.0825 × P
        try:
            p_mm = float(str(pitch_str).strip())
        except Exception:
            p_mm = 1.0
        d1max = dia_mm - 1.0825 * p_mm

    pct         = _interpolated_deviation_pct(dia_mm)
    deviation   = d1max * pct / 100.0
    bore_eff    = d1max + deviation

    try:
        import FreeCAD as _FC
        _FC.Console.PrintMessage(
            f"[NutBore] dia={dia_str} P={pitch_str} cls={cls_str}\n"
            f"  D1max (CSV)    = {d1max:.5f} mm\n"
            f"  deviation pct  = {pct:.4f} %\n"
            f"  deviation_mm   = {deviation:.5f} mm\n"
            f"  bore_eff       = {bore_eff:.5f} mm  (body bore radius = {bore_eff/2:.5f} mm)\n"
        )
    except Exception:
        pass

    return bore_eff


# ── Resolve pitch from fa ─────────────────────────────────────────────────────

def resolve_nut_pitch(fa):
    """Resolve metric pitch mm for a nut from fa attributes.

    Priority:
      1. fa.Thread_Pitch_Nut (dashboard dropdown selection)
      2. fa.calc_pitch (fallback / legacy override)
      3. Coarsest pitch from CSV for this dia
    """
    dia_str = str(getattr(fa, "calc_diam", "") or "")
    dia_key = _norm(dia_str.strip().lstrip("Mm"))

    p_prop = str(getattr(fa, "Thread_Pitch_Nut", "") or "")
    if p_prop == "Custom":
        try:
            p_custom = float(getattr(fa, "Thread_Pitch_Nut_Custom", 0) or 0)
            if p_custom > 0:
                return p_custom
        except Exception:
            pass
    if p_prop and p_prop != "Custom":
        try:
            return float(p_prop)
        except Exception:
            pass

    cp = getattr(fa, "calc_pitch", None)
    if cp:
        try:
            cp_f = float(cp)
            if cp_f > 0:
                return cp_f
        except Exception:
            pass

    pitches = valid_pitches_for_dia(dia_str)
    if pitches:
        return float(pitches[-1])   # coarsest = largest pitch number

    return None


# ── Internal thread cutter ────────────────────────────────────────────────────

def make_internal_thread_cutter(bore_dia, P, depth, root_round=False):
    """Return ISO metric internal thread cutter solid.

    Exact mirror of make_metric_thread_cutter (external).

    External: crest at d2 (outer),  root inward  at d2 - 0.625H
    Internal: crest at d2 (inner),  root outward at d2 + 0.625H

    root_round=False → flat root (into nut material)   standard
    root_round=True  → rounded root (ISO 68-1)         standard for nuts

    Parameters
    ----------
    bore_dia  : float  effective bore dia mm (D1max + deviation)
    P         : float  pitch mm
    depth     : float  thread depth mm (nut height m)
    root_round: bool   True → arc at root (outward), False → flat
    """
    import Part, FastenerBase
    import FreeCAD as _FC
    Base = _FC.Base

    H      = _sqrt3 / 2.0 * P
    d2     = bore_dia / 2.0          # bore wall radius = crest (innermost)
    trot   = int(depth // P) + 1
    ht     = trot * P

    # Root outward into nut material (mirror of external root inward)
    x_root = d2 + 0.625 * H
    h_root = P / 8.0

    # Profile — true negative image of bolt external cutter:
    #
    #   Bolt:  crest OUTER (d2+offset) flat always
    #          root  INNER (x_root)    Flat or Round  ← root_round applied here
    #
    #   Nut:   root  OUTER (x_root)    flat always    (standard, into material)
    #          crest INNER (d2)        Flat or Round  ← root_round applied here
    #
    # So root_round=True  → rounded CREST (toward center hole)
    #    root_round=False → flat    CREST (toward center hole)
    #
    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(x_root - _sqrt3 * 3 / 80.0 * P, -0.475 * P)  # near root flank bottom
    fm.AddPoint(d2, -h_root)                                    # crest bottom (inner)
    if root_round:
        # Arc midpoint goes OUTWARD from d2 — mirror of bolt arc going inward from x_root
        # Bolt:  fm.AddArc(x_root - 0.5*0.125*P, 0, x_root,  h_root)  ← inward
        # Nut:   fm.AddArc(d2     + 0.5*0.125*P, 0, d2,      h_root)  ← outward (mirror)
        fm.AddArc(d2 + 0.5 * 0.125 * P, 0, d2, h_root)
    else:
        fm.AddPoint(d2, h_root)                                 # flat crest top
    fm.AddPoint(x_root - _sqrt3 * 3 / 80.0 * P,  0.475 * P)  # near root flank top

    wire = fm.GetClosedWire()
    # Nut body is at z=0 to z=m (upward) — do NOT rotate 180°
    # Wire starts slightly below z=0 so helix lead-in is below nut face
    wire.translate(Base.Vector(0, 0, -P * 0.6))

    thread_depth = 0.625 * H
    # Helix goes UPWARD (z=0 to ht) to match nut body direction
    # No 180° rotation — nut is opposite direction to bolt shank
    helix      = Part.makeLongHelix(P, ht, bore_dia / 2.0, 0, False)
    lead_helix = Part.makeLongHelix(P, P / 2.0,
                                    bore_dia / 2.0 + 0.55 * thread_depth, 0, False)
    lead_helix.translate(Base.Vector(-0.55 * thread_depth, 0, 0))

    path  = Part.Wire([helix, lead_helix])
    sweep = Part.BRepOffsetAPI.MakePipeShell(path)
    sweep.setFrenetMode(True)
    sweep.setTransitionMode(1)
    sweep.add(wire)
    if sweep.isReady():
        sweep.build()
    else:
        raise RuntimeError("[FSThreadingMetricInternal] sweep failed")
    sweep.makeSolid()
    threads = sweep.shape()
    # Box clip — keep only the region from z=-P to z=depth+P
    # This trims the lead-in stubs above and below the nut face
    clip_r = x_root + P
    box = Part.makeBox(2 * clip_r, 2 * clip_r, depth + 2 * P,
                       Base.Vector(-clip_r, -clip_r, -P))
    return threads.common(box)


# ── Main entry point ──────────────────────────────────────────────────────────

def cut_internal_thread(nut_shape, fa, dia, depth, P_mm=None):
    """Cut ISO metric internal thread into nut_shape.

    Parameters
    ----------
    nut_shape : FreeCAD shape   — nut body (already cut to hex)
    fa        : fastener attrs  — calc_diam, calc_pitch, Thread_Pitch_Nut,
                                  Thread_Class_Nut, Thread_Root
    dia       : float mm        — nominal diameter (fallback reference)
    depth     : float mm        — thread depth = nut height m
    P_mm      : float mm        — pitch override (optional)
    """
    import FreeCAD as _FC

    P = P_mm if (P_mm and P_mm > 0) else resolve_nut_pitch(fa)
    if not P or P <= 0:
        _FC.Console.PrintError("[FSThreadingMetricInternal] pitch=0, skip\n")
        return nut_shape

    dia_str   = str(getattr(fa, "calc_diam", str(dia)) or str(dia))
    pitch_str = str(P)
    cls_str   = str(getattr(fa, "Thread_Class_Nut", "6H") or "6H")
    root_prop = str(getattr(fa, "Thread_Root", "Flat") or "Flat").strip()
    root_round = (root_prop == "Round")

    bore_eff  = bore_dia_from_table(fa, dia_str, pitch_str, cls_str)

    try:
        _FC.Console.PrintMessage(
            f"[NutThread] dia={dia_str} P={P:.4f}mm cls={cls_str}"
            f" root={'Round' if root_round else 'Flat'}\n"
            f"  bore_eff = {bore_eff:.5f} mm  depth = {depth:.3f} mm\n"
        )
    except Exception:
        pass

    cutter = make_internal_thread_cutter(bore_eff, P, depth, root_round=root_round)
    return nut_shape.cut(cutter)


# ── FreeCAD panel visibility ──────────────────────────────────────────────────

def set_nut_thread_visibility(fp, thread_on):
    """Show/hide metric internal thread properties in FreeCAD panel."""
    if hasattr(fp, "Thread_Pitch_Nut"):
        fp.setEditorMode("Thread_Pitch_Nut", 0 if thread_on else 2)
    _is_custom = False
    if hasattr(fp, "Thread_Pitch_Nut"):
        try:
            _is_custom = str(fp.Thread_Pitch_Nut) == "Custom"
        except Exception:
            _is_custom = False
    if hasattr(fp, "Thread_Pitch_Nut_Custom"):
        fp.setEditorMode("Thread_Pitch_Nut_Custom", 0 if (thread_on and _is_custom) else 2)
    _p = ""
    if hasattr(fp, "Thread_Pitch_Nut"):
        try:
            _p = str(fp.Thread_Pitch_Nut)
        except Exception:
            pass
    _cls_ready = thread_on and bool(_p)
    if hasattr(fp, "Thread_Class_Nut"):
        fp.setEditorMode("Thread_Class_Nut", 0 if _cls_ready else 2)
    if hasattr(fp, "Thread_Root"):
        fp.setEditorMode("Thread_Root", 0 if thread_on else 2)
