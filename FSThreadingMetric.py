# -*- coding: utf-8 -*-
"""
FSThreadingMetric.py — ISO metric thread cutting module
=======================================================
Responsibilities:
  1. Load metric_thread_dia.csv (ISO 965-6 Thread Mean Dia)
  2. Table query helpers for FastenersCmd dashboard dropdowns
  3. Cut ISO metric threads into a FreeCAD shape

NOT responsible for: b_tbl, r, thread length, bolt length.
Those are computed by the calling FsMake file.

Public API
----------
  mean_dia_from_table(dia_str, pitch_str, cls)    -> float mm  (raw CSV, no deviation)
  valid_pitches_for_dia(dia_str)                  -> list
  valid_classes_for_dia_pitch(dia_str, pitch_str) -> list
  resolve_metric_pitch(fa)                        -> float mm
  get_shank_dia(fa, dia_fallback)                -> float mm  ← SINGLE SOURCE of d_eff
  set_metric_thread_visibility(fp, thread_on)     -> None
  is_metric_type(fp_type_str)                     -> bool
  cut_thread(shape, fa, dia, tl, offset_z, P_mm)  -> shape
"""

import os as _os, math as _math, functools as _functools
_sqrt3 = _math.sqrt(3.0)

_CSV_DIR    = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "FsData")
_CSV_METRIC = _os.path.join(_CSV_DIR, "metric_thread_dia.csv")

# ── Diameter deviation (percentage, diameter-dependent) ──────────────────────
#
# A percentage of Thread_Mean_Dia (from metric_thread_dia.csv) is
# SUBTRACTED to get d_eff — the effective diameter used for:
#   — bolt shank + tip profile  (body making in every FsMake file)
#   — thread cutter OD          (cut_thread helix cutter)
#
#   deviation_mm  =  Thread_Mean_Dia  ×  pct / 100
#   d_eff         =  Thread_Mean_Dia  −  deviation_mm
#
# Small diameters  → DEVIATION_PCT_SMALL  (larger subtraction)
# Large diameters  → DEVIATION_PCT_LARGE  (smaller subtraction)
# In between       → linearly interpolated automatically
#
# Example with defaults:
#   M6   ( 6 mm)  → 2.000 % subtracted
#   M16  (16 mm)  → 1.914 % subtracted  (interpolated)
#   M24  (24 mm)  → 1.845 % subtracted  (interpolated)
#   M48  (48 mm)  → 1.655 % subtracted  (interpolated)
#   M64  (64 mm)  → 1.500 % subtracted
#
# ↓↓ Change only these two values — dia bounds are read from the CSV ↓↓
DEVIATION_PCT_SMALL  = 2.0    # % subtracted at the smallest dia in metric_thread_dia.csv
DEVIATION_PCT_LARGE  = 1.5    # % subtracted at the largest  dia in metric_thread_dia.csv


def _metric_dia_bounds_mm():
    """Return (min_mm, max_mm) by reading all Dia_mm values from the CSV.

    Called once at load time — result stored in DEVIATION_DIA_MIN/MAX_MM.
    Falls back to (6.0, 64.0) if the CSV cannot be read.
    """
    import csv
    mm_vals = []
    try:
        with open(_CSV_METRIC, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    mm_vals.append(float(str(row["Dia_mm"]).strip()))
                except Exception:
                    pass
    except Exception:
        pass
    if not mm_vals:
        return 6.0, 64.0
    return min(mm_vals), max(mm_vals)


# Dia bounds loaded from CSV — do NOT edit these; change DEVIATION_PCT_* above
_METRIC_DIA_MIN_MM, _METRIC_DIA_MAX_MM = _metric_dia_bounds_mm()
DEVIATION_DIA_MIN_MM = _METRIC_DIA_MIN_MM   # smallest Dia_mm in CSV
DEVIATION_DIA_MAX_MM = _METRIC_DIA_MAX_MM   # largest  Dia_mm in CSV


def _interpolated_deviation_pct(dia_mm):
    """Return linearly interpolated deviation % for dia_mm."""
    if dia_mm <= DEVIATION_DIA_MIN_MM:
        return DEVIATION_PCT_SMALL
    if dia_mm >= DEVIATION_DIA_MAX_MM:
        return DEVIATION_PCT_LARGE
    t = (dia_mm - DEVIATION_DIA_MIN_MM) / (DEVIATION_DIA_MAX_MM - DEVIATION_DIA_MIN_MM)
    return DEVIATION_PCT_SMALL + t * (DEVIATION_PCT_LARGE - DEVIATION_PCT_SMALL)


# ── CSV loader ────────────────────────────────────────────────────────────────

@_functools.lru_cache(maxsize=1)
def _metric_table():
    """(dia_str, pitch_str, class_str) -> (Thread_Mean_Dia_mm, dmax_mm, dmin_mm)

    CSV has a table-name row on line 0, real headers on line 1.
    Skip line 0 before passing to DictReader.
    """
    import csv, io
    table = {}
    try:
        with open(_CSV_METRIC, newline="", encoding="utf-8") as f:
            raw = f.read()
        lines = raw.splitlines()
        # Skip the table-name row (line 0), pass lines[1:] to DictReader
        reader = csv.DictReader(io.StringIO("\n".join(lines[1:])))
        for row in reader:
            try:
                key = (str(row["Dia_mm"]).strip().strip('"'),
                       str(row["Pitch_mm"]).strip().strip('"'),
                       str(row["Class"]).strip().strip('"'))
                table[key] = (float(row["Thread_Mean_Dia_mm"]),
                              float(row["dmax_mm"]),
                              float(row["dmin_mm"]))
            except Exception:
                pass
    except Exception:
        pass
    return table


def _dia_key(diam_str):
    """'M6' → '6.0',  '6' → '6.0'"""
    s = str(diam_str or "").strip()
    if s.upper().startswith("M"):
        s = s[1:]
    try:
        return str(float(s))
    except Exception:
        return s


# ── Dashboard query helpers ───────────────────────────────────────────────────

def valid_pitches_for_dia(dia_str):
    """Return only pitches that exist in metric_thread_dia.csv for this diameter.
    Never returns a hardcoded fallback - empty list means dia not in CSV.
    """
    key = _dia_key(dia_str)
    return sorted({k[1] for k in _metric_table() if k[0] == key}, key=float)


def valid_classes_for_dia_pitch(dia_str, pitch_str):
    """Return only classes that exist in CSV for this (diameter, pitch) pair.
    Never returns a hardcoded fallback - empty list means combo not in CSV.
    """
    key_d = _dia_key(dia_str)
    key_p = str(pitch_str).strip()
    return sorted({k[2] for k in _metric_table()
                   if k[0] == key_d and k[1] == key_p})



def mean_dia_from_table(dia_str, pitch_str, cls):
    """Raw Thread_Mean_Dia_mm from CSV — NO deviation applied.
    Use get_shank_dia() for the deviated effective diameter.
    """
    key = (_dia_key(dia_str), str(pitch_str).strip(), str(cls).strip())
    row = _metric_table().get(key)
    return row[0] if row else None


def get_metric_options(dia_str):
    return {"pitches": valid_pitches_for_dia(dia_str)}


# ── Pitch resolver ────────────────────────────────────────────────────────────

def resolve_metric_pitch(fa):
    """Priority: Thread_Pitch > calc_pitch > coarsest from CSV.
    Never returns a hardcoded 1.0 fallback.
    """
    mp = getattr(fa, "Thread_Pitch", None)
    if mp:
        try:
            v = float(str(mp))
            if v > 0:
                return v
        except Exception:
            pass
    cp = getattr(fa, "calc_pitch", None)
    if cp:
        try:
            v = float(cp)
            if v > 0:
                return v
        except Exception:
            pass
    # Coarsest pitch from CSV for this diameter (first = smallest = coarsest)
    pitches = valid_pitches_for_dia(getattr(fa, "calc_diam", "") or "")
    if pitches:
        try:
            return float(pitches[0])
        except Exception:
            pass
    # Absolute last resort - derive from nominal if CSV has nothing
    return None



# ── Thread cutter geometry ────────────────────────────────────────────────────

def make_metric_thread_cutter(dia, P, blen, root_round=False):
    """Return ISO metric external thread cutter solid.
    dia = d_eff (deviated) — passed from cut_thread via get_shank_dia().
    """
    import Part, FastenerBase
    import FreeCAD as _FC
    Base   = _FC.Base
    H      = _sqrt3 / 2.0 * P
    d2     = dia / 2.0
    trot   = blen // P + 1
    ht     = trot * P
    x_root = d2 - 0.625 * H
    h_root = P / 8.0

    fm = FastenerBase.FSFaceMaker()
    fm.AddPoint(d2 + _sqrt3*3/80.0*P, -0.475*P)
    fm.AddPoint(x_root, -h_root)
    if root_round:
        fm.AddArc(x_root - 0.5*0.125*P, 0, x_root, h_root)
    else:
        fm.AddPoint(x_root, h_root)
    fm.AddPoint(d2 + _sqrt3*3/80.0*P,  0.475*P)

    wire = fm.GetClosedWire()
    wire.translate(Base.Vector(0, 0, -ht - P*0.6))

    depth      = 0.625 * H
    helix      = Part.makeLongHelix(P, ht, dia/2.0, 0, False)
    lead_helix = Part.makeLongHelix(P, P/2.0, dia/2.0 + 0.55*depth, 0, False)
    helix.rotate(Base.Vector(0,0,0), Base.Vector(1,0,0), 180)
    lead_helix.translate(Base.Vector(-0.55*depth, 0, 0))

    path  = Part.Wire([helix, lead_helix])
    sweep = Part.BRepOffsetAPI.MakePipeShell(path)
    sweep.setFrenetMode(True)
    sweep.setTransitionMode(1)
    sweep.add(wire)
    if sweep.isReady():
        sweep.build()
    else:
        raise RuntimeError("[FSThreadingMetric] sweep failed")
    sweep.makeSolid()
    threads = sweep.shape()
    box = Part.makeBox(2*dia, 2*dia, dia, Base.Vector(-dia, -dia, -P*0.1))
    return threads.cut(box)


# ── Single source of effective shank/cutter diameter ─────────────────────────

def get_shank_dia(fa, dia_fallback):
    """Return d_eff mm — deviated effective diameter for metric threads.

    Called by EVERY FsMake file to get both:
      — shank + tip body profile diameter
      — thread cutter OD

    Flow:
        fa.calc_diam + fa.Thread_Pitch + fa.Thread_Class_ISO
            → mean_dia_from_table() → raw val (mm)
            → _interpolated_deviation_pct(dia_fallback) → pct
            → d_eff = val − (val × pct / 100)

    Falls back to dia_fallback (no deviation) if pitch/class not set or not in table.

    Parameters
    ----------
    fa           : fastener attributes object
    dia_fallback : float  nominal mm — fallback + interpolation reference
    """
    # ── Resolve pitch — never skip deviation ─────────────────────────────
    # Priority:
    #   1. Thread_Pitch property (user-selected from dashboard dropdown)
    #   2. calc_pitch already resolved by FastenersCmd
    #   3. Coarsest pitch from CSV for this diameter (always available)
    # This ensures CSV lookup always has a valid pitch → deviation always fires.
    mp = getattr(fa, "Thread_Pitch", None)
    if not mp or not str(mp).strip():
        # Fallback to calc_pitch
        cp = getattr(fa, "calc_pitch", None)
        if cp:
            try:
                mp = str(float(cp))
            except Exception:
                pass
    if not mp or not str(mp).strip():
        # Last resort: coarsest pitch from CSV
        _dia_s = getattr(fa, "calc_diam", "") or ""
        _std_p = valid_pitches_for_dia(_dia_s)
        if _std_p:
            mp = _std_p[0]

    mc = getattr(fa, "Thread_Class_ISO", None)
    if not mc or not str(mc).strip():
        mc = "6g"   # standard class default

    if mp and mc:
        try:
            val = mean_dia_from_table(
                getattr(fa, "calc_diam", "") or "",
                str(float(str(mp))),
                str(mc))
            if val and val > 0:
                pct          = _interpolated_deviation_pct(dia_fallback)
                deviation_mm = val * pct / 100.0
                return val - deviation_mm
        except Exception:
            pass
    return dia_fallback


# ── Main entry point ──────────────────────────────────────────────────────────

def cut_thread(shape, fa, dia, tl, offset_z, P_mm=None):
    """Cut ISO metric thread into shape.

    d_cutter comes from get_shank_dia() — same deviated value used for
    bolt body profile. Consistent diameter throughout.

    Parameters
    ----------
    shape    : FreeCAD shape
    fa       : fastener attributes
    dia      : nominal mm — fallback + interpolation reference
    tl       : thread length mm
    offset_z : z offset mm
    P_mm     : pitch mm (optional)
    """
    import FreeCAD as _FC

    P = P_mm if (P_mm and P_mm > 0) else resolve_metric_pitch(fa)

    # d_cutter — deviated, via get_shank_dia (same as bolt body diameter)
    d_cutter = get_shank_dia(fa, dia)

    root_round = str(getattr(fa, "Thread_Root", "Flat") or "Flat").strip() == "Round"
    mc = getattr(fa, "Thread_Class_ISO", None)
    mp = getattr(fa, "Thread_Pitch",     None)

    # console log — all values guarded against None
    try:
        _d_raw = None
        if mp and mc:
            try:
                _d_raw = mean_dia_from_table(
                    getattr(fa, "calc_diam", "") or "",
                    str(float(str(mp))), str(mc))
            except Exception:
                pass
        _d_raw = float(_d_raw) if _d_raw else float(dia)
        _pct   = _interpolated_deviation_pct(float(dia)) if dia else 0.0
        _dev   = _d_raw * _pct / 100.0
        _dc    = float(d_cutter) if d_cutter is not None else float(dia)
        _FC.Console.PrintMessage(
            f"[Metric cut] pitch={float(P):.4f} mm  class={mc or '-'}\n"
            f"  Thread_Mean_Dia (CSV)  = {_d_raw:.5f} mm\n"
            f"  deviation pct          = {_pct:.4f} %\n"
            f"  deviation_mm           = {_dev:.5f} mm\n"
            f"  d_eff (body + cutter)  = {_dc:.5f} mm\n"
            f"  root={'Round' if root_round else 'Flat'}"
            f"  tl={float(tl):.3f} mm  offset_z={float(offset_z):.3f} mm\n")
    except Exception as _log_err:
        _FC.Console.PrintMessage(f"[Metric cut] log error: {_log_err}\n")

    tc = make_metric_thread_cutter(d_cutter, P, tl, root_round=root_round)
    tc.translate(_FC.Base.Vector(0, 0, offset_z))
    return shape.cut(tc)


# ── FastenersCmd helper ───────────────────────────────────────────────────────

def is_metric_type(fp_type_str):
    return not str(fp_type_str).startswith("ASME")


def set_metric_thread_visibility(fp, thread_on):
    """Show/hide metric thread properties in FreeCAD panel."""
    if hasattr(fp, "Thread_Pitch"):
        fp.setEditorMode("Thread_Pitch", 0 if thread_on else 2)
    _pitch_sel = ""
    if hasattr(fp, "Thread_Pitch"):
        try:
            _pitch_sel = str(fp.Thread_Pitch)
        except Exception:
            pass
    _cls_ready = thread_on and bool(_pitch_sel)
    if hasattr(fp, "Thread_Class_ISO"):
        fp.setEditorMode("Thread_Class_ISO", 0 if _cls_ready else 2)
    if hasattr(fp, "Thread_Root"):
        fp.setEditorMode("Thread_Root", 0 if thread_on else 2)
    # Thread_Length — show when thread is on so user can set custom thread length
    if hasattr(fp, "Thread_Length"):
        fp.setEditorMode("Thread_Length", 0 if thread_on else 2)
    if hasattr(fp, "MetricMeanDia"):
        fp.setEditorMode("MetricMeanDia", 2)