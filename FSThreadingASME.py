# -*- coding: utf-8 -*-
"""
FSThreadingASME.py — ASME UN/UNR thread cutting module
=======================================================
Responsibilities:
  1. Load un_unr_limits_of_size.csv (ASME B1.1 Thread Outer Dia)
  2. Table query helpers for FastenersCmd dashboard dropdowns
  3. Cut ASME UN/UNR threads into a FreeCAD shape

NOT responsible for: b_tbl, r, thread length, bolt length.
Those are computed by the calling FsMake file.

Public API
----------
  outer_dia_mm(nominal, series, tpi, cls)        -> float mm  (raw CSV, no deviation)
  bolt_nominal(diam_str)                          -> str
  valid_thread2types_for_dia(nominal)             -> list
  tpi_enum_options(nominal, thread_type)          -> list
  valid_classes_for_series_tpi(nominal, s, tpi)   -> list
  all_classes_for_nominal(nominal)                -> list
  resolve_thread_params(nominal, fa)              -> dict
  thread_dia_limits_asme(...)                     -> dict
  get_shank_dia(fa, dia_fallback)                -> float mm  ← SINGLE SOURCE of d_eff
  cut_thread(shape, fa, dia, tl, offset_z, P_mm) -> shape
"""

import os as _os, math as _math, functools as _functools
_sqrt3 = _math.sqrt(3.0)

_CSV_DIR  = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "FsData")
_CSV_ASME = _os.path.join(_CSV_DIR, "un_unr_limits_of_size.csv")

# ── Diameter deviation (percentage, diameter-dependent) ──────────────────────
#
# A percentage of Thread_Outer_Dia (from un_unr_limits_of_size.csv) is
# SUBTRACTED to get d_eff — the effective diameter used for:
#   — bolt shank + tip profile  (body making in every FsMake file)
#   — thread cutter OD          (cut_thread helix cutter)
#
#   deviation_mm  =  Thread_Outer_Dia  ×  pct / 100
#   d_eff         =  Thread_Outer_Dia  −  deviation_mm
#
# Small diameters  → DEVIATION_PCT_SMALL  (larger subtraction)
# Large diameters  → DEVIATION_PCT_LARGE  (smaller subtraction)
# In between       → linearly interpolated automatically
#
# Example with defaults:
#   1/4 in  ( 6.35 mm)  → 2.000 % subtracted
#   5/8 in  (15.88 mm)  → 1.834 % subtracted  (interpolated)
#   1   in  (25.40 mm)  → 1.724 % subtracted  (interpolated)
#   2   in  (50.80 mm)  → 1.552 % subtracted  (interpolated)
#   2.5 in  (63.50 mm)  → 1.500 % subtracted
#
# ↓↓ Change only these two values — dia bounds are read from the CSV ↓↓
DEVIATION_PCT_SMALL  = 0    # % subtracted at the smallest dia in un_unr_limits_of_size.csv
DEVIATION_PCT_LARGE  = 0    # % subtracted at the largest  dia in un_unr_limits_of_size.csv


def _asme_dia_bounds_mm():
    """Return (min_mm, max_mm) by reading all nominal diameters from the CSV.

    Called once at first use — result cached in _ASME_DIA_MIN_MM / _ASME_DIA_MAX_MM.
    Converts each Dia string ('1/4', '1-1/4', '2' …) to mm and takes min/max.
    Falls back to (6.0, 64.0) if the CSV cannot be read.
    """
    import csv, io
    mm_vals = []
    try:
        with open(_CSV_ASME, newline="", encoding="utf-8") as f:
            content = f.read()
        lines = content.splitlines()
        reader = csv.DictReader(io.StringIO("\n".join(lines[1:])))
        for row in reader:
            try:
                dia_str = row["Dia"].strip().strip('"')
                mm_vals.append(_nominal_str_to_mm(dia_str))
            except Exception:
                pass
    except Exception:
        pass
    if not mm_vals:
        return 6.0, 64.0
    return min(mm_vals), max(mm_vals)


def _nominal_str_to_mm(s):
    """Convert nominal dia string to mm.  '5/8' → 15.875,  '1-1/4' → 31.75"""
    s = str(s).strip().replace("-", " ")
    total = 0.0
    for p in s.split():
        if "/" in p:
            n, d = p.split("/")
            total += float(n) / float(d)
        else:
            total += float(p)
    return total * 25.4


# Dia bounds loaded from CSV — do NOT edit these; change DEVIATION_PCT_* above
_ASME_DIA_MIN_MM, _ASME_DIA_MAX_MM = _asme_dia_bounds_mm()
DEVIATION_DIA_MIN_MM = _ASME_DIA_MIN_MM   # smallest nominal dia in CSV (mm)
DEVIATION_DIA_MAX_MM = _ASME_DIA_MAX_MM   # largest  nominal dia in CSV (mm)


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
def _limits():
    """(nominal_str, tpi_float, series_str, class_str) -> outer_dia_inches"""
    import csv, io
    table = {}
    try:
        with open(_CSV_ASME, newline="", encoding="utf-8") as f:
            content = f.read()
        lines = content.splitlines()
        reader = csv.DictReader(io.StringIO("\n".join(lines[1:])))
        for row in reader:
            try:
                dia    = row["Dia"].strip().strip('"')
                tpi    = float(row["TPI"])
                series = row["Series"].strip().strip('"')
                cls    = row["Class"].strip().strip('"')
                key    = (dia, tpi, series, cls)
                table[key] = float(row["Thread_Outer_Dia"])
            except Exception:
                pass
    except Exception:
        pass
    return table


# ── Nominal helpers ───────────────────────────────────────────────────────────

def bolt_nominal(diam_str):
    """'5/8in' → '5/8',  '5/8"' → '5/8',  '1-1/4in' → '1-1/4'"""
    s = str(diam_str or "").strip()
    s = s.replace('"', "in")
    if not s or s == "Auto":
        return ""
    s = s.rstrip("in").rstrip()
    return s





# ── Dashboard query helpers ───────────────────────────────────────────────────

def valid_tpis_for_series(nominal, series):
    """Return sorted-descending TPI list for (nominal, series).

    For UN/UNR: CSV rows are stored under UNC/UNF/UNEF series names, not
    under a literal "UN" key.  Aggregate all series so the dropdown is never empty.
    For UNC/UNF/UNEF: use exact series match as before.
    """
    if series in ("UN", "UNR"):  # UNR shares UN rows in CSV
        raw = sorted({k[1] for k in _limits() if k[0] == nominal}, reverse=True)
    else:
        raw = sorted(
            {k[1] for k in _limits() if k[0] == nominal and k[2] == series},
            reverse=True)
    return [int(t) if t == int(t) else t for t in raw]


def valid_thread2types_for_dia(nominal):
    """Return only thread types that exist in the CSV for this diameter.
    UN/UNR only shown if the CSV has explicit rows for them.
    Never added unconditionally.
    """
    in_table = {k[2] for k in _limits() if k[0] == nominal}
    # UNR has no CSV rows — it shares UN diameter/TPI data, round root only.
    # Show UNR whenever UN is available for this diameter.
    order  = ["UNC", "UNF", "UNEF", "UN"]
    result = [s for s in order if s in in_table]
    # Add UNR alongside UN if UN is available
    if "UN" in result:
        result.append("UNR")
    return result or ["UNC"]


def valid_series_for_dia(nominal):
    order = ["UNC","UNF","UNEF","UN"]
    seen  = {k[2] for k in _limits() if k[0]==nominal}
    return [s for s in order if s in seen] or ["UNC"]


def valid_classes_for_series_tpi(nominal, series, tpi):
    """Return class list for (nominal, series, tpi).

    For UN/UNR: look across ALL stored series for that dia+tpi because rows are
    stored under UNC/UNF/UNEF series names in the CSV.
    """
    if series in ("UN", "UNR"):  # UNR shares UN rows in CSV
        classes = sorted({k[3] for k in _limits()
                          if k[0]==nominal and k[1]==float(tpi)})
    else:
        classes = sorted({k[3] for k in _limits()
                          if k[0]==nominal and k[2]==series and k[1]==float(tpi)})
    return classes or ["2A", "3A"]


def all_classes_for_nominal(nominal):
    return sorted({k[3] for k in _limits() if k[0]==nominal}) or ["2A","3A"]


def tpi_enum_options(nominal, thread_type):
    """Return TPI dropdown list: standard CSV values first, then 'Custom' last.

    Standard TPI values come from the CSV for this nominal + thread_type.
    For UN/UNR aggregates across all stored series — never returns only Custom.
    """
    tpis = valid_tpis_for_series(nominal, thread_type)
    return [str(t) for t in tpis] + ["Custom"]



def get_all_options(nominal):
    return {"types": valid_thread2types_for_dia(nominal),
            "series": valid_series_for_dia(nominal),
            "classes": all_classes_for_nominal(nominal)}


# ── Raw CSV lookup (no deviation) ────────────────────────────────────────────

def outer_dia_mm(nominal, series, tpi, cls):
    """Raw Thread_Outer_Dia mm from CSV — NO deviation applied.
    Use get_shank_dia() for the deviated effective diameter.

    Series fallback: UN/UNR have no rows for coarser pitches — those are stored
    under UNC/UNF/UNEF. If lookup fails, try same TPI under other series.
    """
    val = _limits().get((str(nominal), float(tpi), str(series), str(cls)))
    if val is not None:
        return val * 25.4
    # Series fallback — try same TPI under standard series
    for _fb_series in ("UNC", "UNF", "UNEF", "UN"):
        if _fb_series == series:
            continue
        val = _limits().get((str(nominal), float(tpi), _fb_series, str(cls)))
        if val is not None:
            return val * 25.4
    return None


def nearest_tpi_in_csv(nominal, series):
    """Return sorted list of all TPIs in CSV for this nominal across all series.
    Used for custom TPI diameter lookup — find nearest standard TPI.
    """
    # Collect all TPIs for this nominal across all series
    all_tpis = sorted({k[1] for k in _limits() if k[0] == nominal})
    return all_tpis


def nearest_tpi(custom_tpi, nominal, series):
    """Find the nearest standard TPI in CSV to the given custom TPI.
    Used ONLY for diameter lookup — thread geometry still uses custom_tpi.
    """
    candidates = nearest_tpi_in_csv(nominal, series)
    if not candidates:
        return custom_tpi
    return min(candidates, key=lambda t: abs(t - float(custom_tpi)))


def thread_dia_limits_asme(nominal_mm, P_mm, cls,
                            nominal_str="", series="UNC", tpi=0):
    H = _sqrt3 / 2.0 * P_mm
    es_mm = 0.0
    if tpi > 0 and cls in ("1A","2A"):
        pi = 25.4 / tpi
        es_in = (0.0015 * (nominal_mm/25.4)**(1/3)
                 + 0.0015 * pi**0.5 + 0.0015/tpi)
        es_mm = es_in * 25.4
    d_mean  = nominal_mm - es_mm - 0.6495 * P_mm
    Td_mm   = (0.0015*(nominal_mm**(1/3))
               + 0.0015*P_mm**0.5 + 0.0015*P_mm)
    d_min   = d_mean - Td_mm
    table_found = False
    d_final = nominal_mm - es_mm
    if nominal_str and tpi > 0:
        val = outer_dia_mm(nominal_str, series, tpi, cls)
        if val:
            d_final = val
            table_found = True
    dev_pct = abs(d_mean-d_final)/d_mean*100 if d_mean > 0 else 0
    return dict(d_mean=d_mean, d_final=d_final, d_min=d_min,
                es_mm=es_mm, Td_mm=Td_mm, dev_pct=dev_pct,
                table_found=table_found)


# ── Parameter resolver ────────────────────────────────────────────────────────

def resolve_thread_params(nominal, fa):
    thread_type = str(getattr(fa, "Thread_Type",       "UNC") or "UNC")
    tpi_sel     = str(getattr(fa, "Thread_TPI",        "")   or "")
    cust_tpi    = int(getattr(fa, "Thread_TPI_Custom",  0)   or 0)
    cls         = str(getattr(fa, "Thread_Class",      "2A") or "2A")
    calc_tpi    = getattr(fa, "calc_tpi",   None)
    calc_pitch  = getattr(fa, "calc_pitch", None)
    # UNR = UN with round root. Thread_Type=="UNR" is the only signal.
    # Thread_Root is not used for ASME — root is determined by thread_type alone.
    is_unr = (thread_type == "UNR")
    # series: UNC/UNF/UNEF use own CSV rows; UN and UNR both map to "UN"
    series = thread_type if thread_type in ("UNC","UNF","UNEF") else "UN"

    if tpi_sel == "Custom" and cust_tpi > 0:
        # User typed a specific custom TPI — use it
        tpi = cust_tpi
    elif calc_tpi and calc_tpi > 0:
        # Already resolved by FastenersCmd execute() — use it
        tpi = int(calc_tpi)
    elif tpi_sel and tpi_sel != "Custom":
        # Standard dropdown value — parse directly
        try:
            tpi = float(tpi_sel)
            tpi = int(tpi) if tpi == int(tpi) else tpi
        except Exception:
            tpi = 0
    else:
        tpi = 0

    # ── Resolve tpi from pitch when still 0 ─────────────────────────────
    # Priority order for zero-tpi recovery:
    #   1. calc_pitch set by FastenersCmd (most accurate — reflects actual
    #      pitch being used, e.g. 1.27mm → TPI=20 for 1/4in)
    #   2. Standard TPI nearest to the nominal from CSV table
    # This ensures deviation is ALWAYS applied — never returns nominal.
    if tpi == 0:
        if calc_pitch and float(calc_pitch) > 0:
            # Derive TPI from the pitch already resolved by FastenersCmd
            tpi = round(25.4 / float(calc_pitch))
        elif nominal:
            # Last resort: use coarsest standard TPI for this diameter
            _std = valid_tpis_for_series(nominal, thread_type)
            if _std:
                tpi = _std[0]

    P_mm = (25.4/tpi) if tpi > 0 else (float(calc_pitch) if calc_pitch else 1.27)
    return dict(tpi=tpi, series=series, cls=cls,
                P_mm=P_mm, is_unr=is_unr, thread_type=thread_type)


# ── Thread cutter geometry ────────────────────────────────────────────────────

def make_UN_thread_cutter(dia, P, blen, unr=False):
    """Return UN/UNR thread cutter solid.
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
    if unr:
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
        raise RuntimeError("[FSThreadingASME] sweep failed")
    sweep.makeSolid()
    threads = sweep.shape()
    box = Part.makeBox(2*dia, 2*dia, dia, Base.Vector(-dia, -dia, -P*0.1))
    return threads.cut(box)


# ── Single source of effective shank/cutter diameter ─────────────────────────

def get_shank_dia(fa, dia_fallback):
    """Return d_eff mm — deviated effective diameter for ASME threads.

    Called by EVERY FsMake file to get both:
      — shank + tip body profile diameter
      — thread cutter OD

    Flow:
        fa.calc_diam → bolt_nominal() → CSV key
        Thread_Type + Thread_TPI + Thread_Class
            → resolve_thread_params() → outer_dia_mm() → raw d (mm)
            → _interpolated_deviation_pct(dia_fallback) → pct
            → d_eff = d − (d × pct / 100)

    Falls back to dia_fallback (no deviation) if TPI=0 or not in table.

    Parameters
    ----------
    fa           : fastener attributes object
    dia_fallback : float  nominal mm — fallback + interpolation reference
    """
    nominal = bolt_nominal(getattr(fa, "calc_diam", "") or "")
    params  = resolve_thread_params(nominal, fa)
    tpi     = params["tpi"]
    series  = params["series"]
    cls     = params["cls"]

    if not nominal or tpi <= 0:
        return dia_fallback

    # Check if this is a custom TPI (not in CSV as an exact row)
    _is_cust_tpi = str(getattr(fa, "Thread_TPI", "")) == "Custom"

    if _is_cust_tpi:
        # Custom TPI: find nearest standard TPI for diameter lookup
        # Thread geometry (pitch/helix) uses actual custom TPI from calc_pitch
        _near = nearest_tpi(tpi, nominal, series)
        d = outer_dia_mm(nominal, series, _near, cls)
    else:
        # Standard TPI: exact CSV lookup with series fallback
        d = outer_dia_mm(nominal, series, float(tpi), cls)

    if not d or d <= 0:
        return dia_fallback

    pct          = _interpolated_deviation_pct(dia_fallback)
    deviation_mm = d * pct / 100.0
    return d - deviation_mm


# ── Main entry point ──────────────────────────────────────────────────────────

def cut_thread(shape, fa, dia, tl, offset_z, P_mm=None):
    """Cut ASME UN/UNR thread into shape.

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
    import FreeCAD
    nominal = bolt_nominal(fa.calc_diam)
    params  = resolve_thread_params(nominal, fa)
    tpi     = params["tpi"]
    series  = params["series"]
    cls     = params["cls"]
    is_unr  = params["is_unr"]
    if P_mm is None or P_mm <= 0:
        P_mm = params["P_mm"]

    # d_cutter — deviated, via get_shank_dia (same as bolt body diameter)
    d_cutter = get_shank_dia(fa, dia)

    # console log — all values guarded against None
    try:
        _is_cust_tpi_log = str(getattr(fa, "Thread_TPI", "")) == "Custom"
        if _is_cust_tpi_log and nominal and tpi > 0:
            _near_log = nearest_tpi(tpi, nominal, series)
            _d_raw = outer_dia_mm(nominal, series, _near_log, cls)
        else:
            _d_raw = outer_dia_mm(nominal, series, float(tpi), cls) if (nominal and tpi > 0) else dia
        _d_raw = _d_raw if _d_raw is not None else dia
        _pct   = _interpolated_deviation_pct(float(dia)) if (dia and float(dia) > 0) else 0.0
        _dev   = (_d_raw * _pct / 100.0) if (_d_raw and _d_raw > 0) else 0.0
        _dc    = d_cutter if d_cutter is not None else dia
        FreeCAD.Console.PrintMessage(
            f"[ASME cut] nom={nominal or '?'}  series={series or '?'}"
            f"  tpi={tpi}  cls={cls or '?'}\n"
            f"  P                      = {float(P_mm):.4f} mm\n"
            f"  Thread_Outer_Dia (CSV) = {float(_d_raw):.5f} mm\n"
            f"  deviation pct          = {float(_pct):.4f} %\n"
            f"  deviation_mm           = {float(_dev):.5f} mm\n"
            f"  d_eff (body + cutter)  = {float(_dc):.5f} mm\n"
            f"  tl={float(tl):.3f} mm  offset_z={float(offset_z):.3f} mm\n")
    except Exception as _log_err:
        FreeCAD.Console.PrintMessage(f"[ASME cut] log error: {_log_err}\n")

    fa.calc_tpi = tpi
    tc = make_UN_thread_cutter(d_cutter, P_mm, tl, unr=is_unr)
    tc.translate(FreeCAD.Base.Vector(0, 0, offset_z))
    return shape.cut(tc)