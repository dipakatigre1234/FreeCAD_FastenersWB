# -*- coding: utf-8 -*-
"""
FSThreadingASMEInternal.py — ASME UN/UNR INTERNAL thread module (nuts)
=======================================================================
Responsibilities:
  1. Load un_unr_internal_thread_minor_dia.csv (ASME B1.1 Table 3)
  2. Table query helpers for FastenersCmd dashboard dropdowns
  3. Bore diameter with deviation (Minor_Dia_Mean + deviation)
  4. Used by FSmakeHexNut for ASME nut bore geometry

CSV structure:
  Row 0 : table name   "UN_UNR_Internal_Thread_Minor_Dia_Table3_ASME_B1.1"  ← skip
  Row 1 : headers      Dia, TPI, Series, Class, Minor_Dia_Mean, Minor_Dia_Max, Minor_Dia_Min
  Row 2+: data         all values in INCHES — converted to mm on return

Key:  (dia_str, tpi_float, series_str, class_str) → Minor_Dia_Mean (inches)

Public API
----------
  valid_types_for_dia(dia_str)                      -> list[str]   e.g. ["UNC","UNF","UN"]
  valid_tpis_for_dia_type(dia_str, series_str)       -> list[str]   e.g. ["8","12"]
  valid_classes_for_dia_tpi_type(dia,tpi,series)     -> list[str]   e.g. ["1B","2B","3B"]
  bore_dia_from_table(fa, dia_str, tpi, series, cls) -> float mm    bore_eff with deviation
  set_asme_nut_visibility(fp, thread_on)             -> None

Deviation system
----------------
Minor_Dia_Mean from CSV is the ASME mean minor diameter.
A small positive deviation is ADDED to give real-world bore clearance.

  bore_eff = Minor_Dia_Mean_mm + (Minor_Dia_Mean_mm × pct / 100)

Deviation scales with diameter (same pattern as FSThreadingMetricInternal):
  Small (#0 ≈ 1.5mm)   → BORE_DEVIATION_PCT_SMALL (larger addition)
  Large (4in ≈ 101mm)  → BORE_DEVIATION_PCT_LARGE (smaller addition)
  In between           → linearly interpolated

↓↓ Change only these two values ↓↓
BORE_DEVIATION_PCT_SMALL = 1.0   # % ADDED at smallest dia in CSV
BORE_DEVIATION_PCT_LARGE = 0.3   # % ADDED at largest  dia in CSV
"""

import os as _os, math as _math, functools as _functools

_CSV_DIR       = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "FsData")
_CSV_ASME_NUT  = _os.path.join(_CSV_DIR, "un_unr_internal_thread_minor_dia.csv")

# ── Bore deviation constants ──────────────────────────────────────────────────
BORE_DEVIATION_PCT_SMALL = 1.0
BORE_DEVIATION_PCT_LARGE = 0.3


# ── Dia bounds (read once from CSV, converted to mm) ──────────────────────────

def _asme_dia_bounds_mm():
    """Return (min_mm, max_mm) from CSV. Falls back to (1.5, 102.0)."""
    import csv
    mm_vals = []
    try:
        with open(_CSV_ASME_NUT, newline="", encoding="utf-8") as f:
            lines = f.readlines()
        for row in csv.DictReader(lines[1:]):
            try:
                mm_vals.append(_inch_str_to_mm(row["Dia"].strip()))
            except Exception:
                pass
    except Exception:
        pass
    valid = [v for v in mm_vals if v and v > 0]
    if len(valid) >= 2:
        return (min(valid), max(valid))
    return (1.5, 102.0)


def _inch_str_to_mm(dia_str):
    """Convert ASME diameter string to mm for deviation interpolation.
    Examples: '1' → 25.4,  '1/4' → 6.35,  '#0' → 1.524,  '1 1/2' → 38.1
    """
    s = str(dia_str).strip()
    # Numbered sizes (#0 through #12)
    _num_map = {
        "#0": 0.060, "#1": 0.073, "#2": 0.086, "#3": 0.099,
        "#4": 0.112, "#5": 0.125, "#6": 0.138, "#8": 0.164,
        "#10": 0.190, "#12": 0.216
    }
    if s in _num_map:
        return _num_map[s] * 25.4
    # Fractional: "1/4", "3/8" etc.
    if "/" in s and " " not in s:
        n, d = s.split("/")
        return float(n) / float(d) * 25.4
    # Mixed: "1 1/2"
    if " " in s:
        parts = s.split(" ", 1)
        whole = float(parts[0])
        n, d = parts[1].split("/")
        return (whole + float(n) / float(d)) * 25.4
    # Integer or decimal
    return float(s) * 25.4


_BORE_DIA_MIN_MM, _BORE_DIA_MAX_MM = _asme_dia_bounds_mm()


def _interpolated_deviation_pct(dia_mm):
    """Linearly interpolate BORE_DEVIATION_PCT between SMALL and LARGE."""
    lo, hi = _BORE_DIA_MIN_MM, _BORE_DIA_MAX_MM
    if hi <= lo:
        return BORE_DEVIATION_PCT_SMALL
    t = max(0.0, min(1.0, (float(dia_mm) - lo) / (hi - lo)))
    return BORE_DEVIATION_PCT_SMALL + t * (BORE_DEVIATION_PCT_LARGE - BORE_DEVIATION_PCT_SMALL)


# ── CSV loader (cached) ───────────────────────────────────────────────────────

@_functools.lru_cache(maxsize=1)
def _asme_nut_table():
    """Return dict keyed (dia_str, tpi_float, series_str, class_str) → minor_dia_mean_inches.

    Row 0 is the table name — skipped.
    Row 1 is headers — used by DictReader.
    All values stored in INCHES. Conversion to mm done at lookup time.
    """
    import csv
    table = {}
    try:
        with open(_CSV_ASME_NUT, newline="", encoding="utf-8") as f:
            lines = f.readlines()
        reader = csv.DictReader(lines[1:])   # skip row 0 (table name)
        for row in reader:
            try:
                dia    = row["Dia"].strip()
                tpi    = float(row["TPI"].strip())
                series = row["Series"].strip()
                cls    = row["Class"].strip()
                mean   = float(row["Minor_Dia_Mean"].strip())
                table[(dia, tpi, series, cls)] = mean
            except Exception:
                pass
    except Exception:
        pass
    return table


# ── Dropdown helpers ──────────────────────────────────────────────────────────

def valid_types_for_dia(dia_str):
    """Return sorted list of series (thread types) available for this diameter.

    e.g. valid_types_for_dia("1") → ["UN", "UNC", "UNF"]
    UN/UNR share same rows — UNR added when UN present (same TPI/dia table).
    """
    dia = str(dia_str).strip()
    series_set = {k[2] for k in _asme_nut_table() if k[0] == dia}
    order  = ["UNC", "UNF", "UNEF", "UN", "UNS"]
    result = [s for s in order if s in series_set]
    if "UN" in result:
        result.append("UNR")   # UNR shares UN rows
    return result or ["UNC"]


def valid_tpis_for_dia_type(dia_str, series_str):
    """Return sorted list of TPI strings (descending) for this dia + series.

    UNR uses same rows as UN.
    """
    dia    = str(dia_str).strip()
    series = "UN" if series_str.strip() == "UNR" else series_str.strip()
    tpis   = sorted(
        {k[1] for k in _asme_nut_table() if k[0] == dia and k[2] == series},
        reverse=True
    )
    return [str(int(t)) if t == int(t) else str(t) for t in tpis]


def valid_classes_for_dia_tpi_type(dia_str, tpi, series_str):
    """Return sorted list of class strings for this dia + TPI + series.

    e.g. → ["1B", "2B", "3B"]
    """
    dia    = str(dia_str).strip()
    series = "UN" if series_str.strip() == "UNR" else series_str.strip()
    try:
        tpi_f = float(tpi)
    except (ValueError, TypeError):
        return ["2B"]
    classes = sorted({k[3] for k in _asme_nut_table()
                      if k[0] == dia and k[1] == tpi_f and k[2] == series})
    return classes or ["2B"]


# ── Bore diameter ─────────────────────────────────────────────────────────────

def minor_dia_from_table(dia_str, tpi, series_str, cls_str):
    """Return raw Minor_Dia_Mean in mm (NO deviation). Returns None if not found.

    Parameters
    ----------
    dia_str    : ASME diameter string e.g. "1", "1/2", "#10"
    tpi        : TPI float or string e.g. 8.0 or "8"
    series_str : series string e.g. "UNC", "UN", "UNR"
    cls_str    : class string e.g. "2B"
    """
    dia    = str(dia_str).strip()
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    try:
        tpi_f = float(tpi)
    except (ValueError, TypeError):
        return None
    val_in = _asme_nut_table().get((dia, tpi_f, series, str(cls_str).strip()))
    if val_in is not None:
        return val_in * 25.4   # convert inches → mm
    # Series fallback: if UN miss, try UNC/UNF/UNEF same TPI
    for fb in ("UNC", "UNF", "UNEF"):
        if fb == series:
            continue
        val_in = _asme_nut_table().get((dia, tpi_f, fb, str(cls_str).strip()))
        if val_in is not None:
            return val_in * 25.4
    return None


def bore_dia_from_table(fa, dia_str, tpi, series_str, cls_str):
    """Return bore effective diameter mm = Minor_Dia_Mean_mm + positive deviation.

    Falls back to ASME formula: nominal_mm - 1.0825 × P if not found.
    """
    minor_mm = minor_dia_from_table(dia_str, tpi, series_str, cls_str)
    try:
        dia_mm = _inch_str_to_mm(dia_str)
    except Exception:
        dia_mm = 25.4  # fallback 1 inch

    if minor_mm is None:
        # Fallback: ASME formula for minor diameter
        try:
            tpi_f = float(tpi)
            P_mm  = 25.4 / tpi_f if tpi_f > 0 else 1.0
        except (ValueError, TypeError):
            P_mm = 1.0
        minor_mm = dia_mm - 1.0825 * P_mm

    pct       = _interpolated_deviation_pct(dia_mm)
    deviation = minor_mm * pct / 100.0
    bore_eff  = minor_mm + deviation

    try:
        import FreeCAD as _FC
        _FC.Console.PrintMessage(
            f"[ASMENutBore] dia={dia_str} TPI={tpi} series={series_str} cls={cls_str}\n"
            f"  Minor_Dia_Mean (CSV) = {minor_mm:.5f} mm\n"
            f"  deviation pct        = {pct:.4f} %\n"
            f"  deviation_mm         = {deviation:.5f} mm\n"
            f"  bore_eff             = {bore_eff:.5f} mm"
            f"  (bore radius = {bore_eff/2:.5f} mm)\n"
        )
    except Exception:
        pass

    return bore_eff


# ── Resolve TPI from fa ───────────────────────────────────────────────────────

def resolve_nut_tpi(fa):
    """Resolve TPI for ASME nut from fa attributes.

    Priority:
      1. Thread_TPI_Nut  (dashboard dropdown)
      2. fa.calc_tpi     (custom TPI override)
      3. Coarsest TPI from CSV for this dia + type
    """
    tpi_prop = str(getattr(fa, "Thread_TPI_Nut", "") or "")
    if tpi_prop and tpi_prop != "Custom":
        try:
            return float(tpi_prop)
        except Exception:
            pass

    ct = getattr(fa, "calc_tpi", None)
    if ct and float(ct) > 0:
        return float(ct)

    dia_str    = str(getattr(fa, "calc_diam", "") or "")
    series_str = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
    tpis = valid_tpis_for_dia_type(dia_str, series_str)
    if tpis:
        return float(tpis[-1])   # coarsest = last in descending list

    return None


# ── FreeCAD panel visibility ──────────────────────────────────────────────────

def set_asme_nut_visibility(fp, thread_on):
    """Show/hide ASME internal nut thread properties in FreeCAD panel."""
    for prop in ("Thread_Type_Nut", "Thread_TPI_Nut", "Thread_Class_Nut"):
        if hasattr(fp, prop):
            fp.setEditorMode(prop, 0 if thread_on else 2)
    # Thread_TPI_Nut class ready only when TPI is selected
    _tpi = str(getattr(fp, "Thread_TPI_Nut", "") or "")
    _cls_ready = thread_on and bool(_tpi)
    if hasattr(fp, "Thread_Class_Nut"):
        fp.setEditorMode("Thread_Class_Nut", 0 if _cls_ready else 2)
