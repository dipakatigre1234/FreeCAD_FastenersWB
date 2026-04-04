# -*- coding: utf-8 -*-
"""
FSThreadingASMEInternal.py — ASME UN/UNR INTERNAL thread module (nuts)
=======================================================================
Responsibilities:
  1. Load un_unr_internal_thread_minor_dia.csv (ASME B1.1 Table 3)
  2. Table query helpers for FastenersCmd dashboard dropdowns
  3. Bore diameter with deviation (Minor_Dia_Max + deviation)
  4. Used by FSmakeHexNut for ASME nut bore geometry

CSV structure:
  Row 0 : table name   "UN_UNR_Internal_Thread_Minor_Dia_Table3_ASME_B1.1"  ← skip
  Row 1 : headers      Dia, TPI, Series, Class, Minor_Dia_Mean, Minor_Dia_Max, Minor_Dia_Min
  Row 2+: data         all values in INCHES — converted to mm on return

Key:  (dia_str, tpi_float, series_str, class_str) → Minor_Dia_Max (inches)

Public API
----------
  valid_types_for_dia(dia_str)                           -> list[str]   e.g. ["UNC","UNF","UN"]
  valid_tpis_for_dia_type(dia_str, series_str)           -> list[str]   e.g. ["8","12"]
  valid_classes_for_dia_tpi_type(dia, tpi, series)       -> list[str]   e.g. ["1B","2B","3B"]
  bore_dia_from_table(fa, dia_str, tpi, series, cls)     -> float mm    bore_eff with deviation
  resolve_nut_tpi(fa)                                    -> float
  set_asme_nut_visibility(fp, thread_on)                 -> None

FreeCAD property names used (ASME nut, distinct from metric nut props)
-----------------------------------------------------------------------
  Thread_Type_Nut      — series dropdown  (UNC / UNF / UN / UNEF / UNS)
  Thread_TPI_Nut       — TPI dropdown     (e.g. "8", "20")
  Thread_Class_Nut_ASME — class dropdown  (1B / 2B / 3B)

Deviation system
----------------
Minor_Dia_Max from CSV is the ASME maximum minor diameter for the chosen class.
A small positive deviation is ADDED to give real-world bore clearance.

  bore_eff = Minor_Dia_Max_mm + (Minor_Dia_Max_mm × pct / 100)

Deviation scales with diameter (same pattern as FSThreadingMetricInternal):
  Small (#0 ≈ 1.5 mm)  → BORE_DEVIATION_PCT_SMALL (larger addition)
  Large (6 in ≈ 152 mm) → BORE_DEVIATION_PCT_LARGE (smaller addition)
  In between            → linearly interpolated

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


# ── Inch string → mm conversion ───────────────────────────────────────────────

def _inch_str_to_mm(dia_str):
    """Convert ASME diameter string to mm for deviation interpolation.

    Examples:
      '#0'    → 1.524       (0.060 in)
      '1/4'   → 6.35
      '1-1/2' → 38.1        (hyphen format from CSV)
      '1 1/2' → 38.1        (space format)
      '1'     → 25.4
      '6'     → 152.4
    """
    s = str(dia_str).strip()

    # Numbered sizes (#0 – #12)
    _num_map = {
        "#0": 0.060, "#1": 0.073, "#2": 0.086, "#3": 0.099,
        "#4": 0.112, "#5": 0.125, "#6": 0.138, "#8": 0.164,
        "#10": 0.190, "#12": 0.216,
    }
    if s in _num_map:
        return _num_map[s] * 25.4

    # Hyphen-separated mixed fractions: "1-1/2", "1-1/4", etc.
    if "-" in s and "/" in s:
        parts = s.split("-", 1)
        whole = float(parts[0])
        n, d  = parts[1].split("/")
        return (whole + float(n) / float(d)) * 25.4

    # Space-separated mixed fractions: "1 1/2"
    if " " in s and "/" in s:
        parts = s.split(" ", 1)
        whole = float(parts[0])
        n, d  = parts[1].split("/")
        return (whole + float(n) / float(d)) * 25.4

    # Simple fractions: "1/4", "3/8"
    if "/" in s:
        n, d = s.split("/")
        return float(n) / float(d) * 25.4

    # Integer or decimal inch: "1", "2", "6"
    return float(s) * 25.4


# ── Dia bounds (read once from CSV) ──────────────────────────────────────────

def _asme_dia_bounds_mm():
    """Return (min_mm, max_mm) from CSV Dia column. Falls back to (1.5, 152.4)."""
    import csv
    mm_vals = []
    try:
        with open(_CSV_ASME_NUT, newline="", encoding="utf-8") as f:
            lines = f.readlines()
        for row in csv.DictReader(lines[1:]):   # skip row 0 (table name)
            try:
                mm_vals.append(_inch_str_to_mm(row["Dia"].strip()))
            except Exception:
                pass
    except Exception:
        pass
    valid = [v for v in mm_vals if v and v > 0]
    if len(valid) >= 2:
        return (min(valid), max(valid))
    return (1.5, 152.4)


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
    """Return dict keyed (dia_str, tpi_float, series_str, class_str) → Minor_Dia_Max_inches.

    CSV layout:
      Row 0 : table name  ← skip
      Row 1 : headers  Dia, TPI, Series, Class, Minor_Dia_Mean, Minor_Dia_Max, Minor_Dia_Min
      Row 2+: data — all dimension values in INCHES

    Minor_Dia_Max is used (largest acceptable bore ensuring bolt fits freely).
    Conversion to mm is done at lookup time.
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
                d_max  = float(row["Minor_Dia_Max"].strip())
                table[(dia, tpi, series, cls)] = d_max
            except Exception:
                pass
    except Exception:
        pass
    return table


# ── Internal helpers ──────────────────────────────────────────────────────────

def _clean_dia(dia_str):
    """Strip 'in' suffix and whitespace — '1/4in' → '1/4', '1in' → '1'."""
    return str(dia_str).strip().replace("in", "").strip()


# ── Dropdown helpers ──────────────────────────────────────────────────────────

def valid_types_for_dia(dia_str):
    """Return ordered list of series (thread types) available for this diameter.

    e.g. valid_types_for_dia("1") → ["UNC", "UNF", "UNEF", "UN", "UNS", "UNR"]

    UNR is appended when UN is present — UNR shares the same CSV rows as UN
    (UNR is an external-only form; the nut internal thread is the same UN table).
    """
    dia = _clean_dia(dia_str)
    series_set = {k[2] for k in _asme_nut_table() if k[0] == dia}
    order  = ["UNC", "UNF", "UNEF", "UN", "UNS"]
    result = [s for s in order if s in series_set]
    if "UN" in result:
        result.append("UNR")   # UNR shares UN rows
    return result or ["UNC"]


def valid_tpis_for_dia_type(dia_str, series_str):
    """Return sorted TPI strings (descending = coarse first) for this dia + series.

    UNR maps to UN rows.
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    tpis   = sorted(
        {k[1] for k in _asme_nut_table() if k[0] == dia and k[2] == series},
        reverse=True,
    )
    return [str(int(t)) if t == int(t) else str(t) for t in tpis]


def valid_classes_for_dia_tpi_type(dia_str, tpi, series_str):
    """Return sorted class strings for this dia + TPI + series.

    When tpi is "Custom" returns ["1B","2B","3B"] as safe defaults.
    e.g. → ["1B", "2B", "3B"]
    """
    if str(tpi).strip() == "Custom":
        return ["1B", "2B", "3B"]
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    try:
        tpi_f = float(tpi)
    except (ValueError, TypeError):
        return ["2B"]
    classes = sorted(
        {k[3] for k in _asme_nut_table()
         if k[0] == dia and k[1] == tpi_f and k[2] == series}
    )
    return classes or ["2B"]


def nearest_tpi_for_nut(custom_tpi, dia_str, series_str):
    """Find the nearest standard TPI in the CSV to custom_tpi for this dia+series.

    Used ONLY for CSV bore/class lookup — actual thread geometry uses custom_tpi.
    Falls back across all series for the dia if none found in requested series.
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    all_tpis = sorted({k[1] for k in _asme_nut_table() if k[0] == dia and k[2] == series})
    if not all_tpis:
        all_tpis = sorted({k[1] for k in _asme_nut_table() if k[0] == dia})
    if not all_tpis:
        return float(custom_tpi)
    return min(all_tpis, key=lambda t: abs(t - float(custom_tpi)))


def tpi_enum_options_for_nut(dia_str, series_str):
    """Return TPI dropdown list: standard CSV values first, then 'Custom' last.

    Mirrors FSThreadingASME.tpi_enum_options for bolt/nut consistency.
    """
    return valid_tpis_for_dia_type(dia_str, series_str) + ["Custom"]


# ── Bore diameter ─────────────────────────────────────────────────────────────

def minor_dia_from_table(dia_str, tpi, series_str, cls_str):
    """Return raw Minor_Dia_Max in mm (NO deviation). Returns None if not found.

    Parameters
    ----------
    dia_str    : ASME diameter string e.g. "1", "1/2", "#10"
    tpi        : TPI float or string e.g. 8.0 or "8"
    series_str : series string e.g. "UNC", "UN", "UNR"
    cls_str    : class string e.g. "2B"
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    try:
        tpi_f = float(tpi)
    except (ValueError, TypeError):
        return None

    val_in = _asme_nut_table().get((dia, tpi_f, series, str(cls_str).strip()))
    if val_in is not None:
        return val_in * 25.4   # inches → mm

    # Series fallback: try common series at same TPI
    for fb in ("UNC", "UNF", "UNEF", "UN"):
        if fb == series:
            continue
        val_in = _asme_nut_table().get((dia, tpi_f, fb, str(cls_str).strip()))
        if val_in is not None:
            return val_in * 25.4
    return None


def bore_dia_from_table(fa, dia_str, tpi, series_str, cls_str):
    """Return bore effective diameter mm = Minor_Dia_Max_mm + positive deviation.

    Mirrors FSThreadingMetricInternal.bore_dia_from_table:
      bore_eff = Minor_Dia_Max_mm + (Minor_Dia_Max_mm × pct / 100)

    Falls back to ASME formula  (nominal_mm − 1.0825 × P_mm)  if CSV miss.

    Custom TPI handling:
      When tpi == "Custom", reads Thread_TPI_Nut_Custom from fa for the actual
      thread pitch, and finds the nearest standard TPI for the CSV bore lookup.
    """
    tpi_str = str(tpi).strip()
    if tpi_str == "Custom":
        custom_val = int(getattr(fa, "Thread_TPI_Nut_Custom", 0) or 0)
        tpi_actual = float(custom_val) if custom_val > 0 else (resolve_nut_tpi(fa) or 8.0)
        tpi_for_csv = nearest_tpi_for_nut(tpi_actual, dia_str, series_str)
    else:
        try:
            tpi_actual = float(tpi_str)
        except (ValueError, TypeError):
            tpi_actual = 8.0
        tpi_for_csv = tpi_actual

    minor_mm = minor_dia_from_table(dia_str, tpi_for_csv, series_str, cls_str)

    try:
        dia_mm = _inch_str_to_mm(_clean_dia(dia_str))
    except Exception:
        dia_mm = 25.4  # 1 inch fallback

    if minor_mm is None:
        # Fallback: ASME formula for minor diameter using actual (custom) TPI
        P_mm     = 25.4 / tpi_actual if tpi_actual > 0 else 1.0
        minor_mm = dia_mm - 1.0825 * P_mm

    pct       = _interpolated_deviation_pct(dia_mm)
    deviation = minor_mm * pct / 100.0
    bore_eff  = minor_mm + deviation

    try:
        import FreeCAD as _FC
        _FC.Console.PrintMessage(
            f"[ASMENutBore] dia={dia_str} TPI={tpi} series={series_str} cls={cls_str}\n"
            f"  Minor_Dia_Max  (CSV) = {minor_mm:.5f} mm\n"
            f"  deviation pct        = {pct:.4f} %\n"
            f"  deviation_mm         = {deviation:.5f} mm\n"
            f"  bore_eff             = {bore_eff:.5f} mm"
            f"  (bore radius = {bore_eff / 2:.5f} mm)\n"
        )
    except Exception:
        pass

    return bore_eff


# ── Resolve TPI from fa ───────────────────────────────────────────────────────

def resolve_nut_tpi(fa):
    """Resolve TPI for ASME nut from fa attributes.

    Priority:
      1. Thread_TPI_Nut == "Custom"  → use Thread_TPI_Nut_Custom integer value
      2. Thread_TPI_Nut  (standard dropdown selection)
      3. fa.calc_tpi     (custom TPI override)
      4. Coarsest TPI from CSV for this dia + type
    """
    tpi_prop = str(getattr(fa, "Thread_TPI_Nut", "") or "")
    if tpi_prop == "Custom":
        cust = int(getattr(fa, "Thread_TPI_Nut_Custom", 0) or 0)
        if cust > 0:
            return float(cust)
        # Custom selected but no value yet — fall through
    elif tpi_prop:
        try:
            return float(tpi_prop)
        except Exception:
            pass

    ct = getattr(fa, "calc_tpi", None)
    if ct is not None:
        try:
            ct_f = float(ct)
            if ct_f > 0:
                return ct_f
        except Exception:
            pass

    dia_str    = str(getattr(fa, "calc_diam", "") or "")
    series_str = str(getattr(fa, "Thread_Type_Nut", "UNC") or "UNC")
    tpis = valid_tpis_for_dia_type(dia_str, series_str)
    if tpis:
        return float(tpis[-1])   # coarsest = last in descending list

    return None


# ── FreeCAD panel visibility ──────────────────────────────────────────────────

def set_asme_nut_visibility(fp, thread_on):
    """Show/hide ASME internal nut thread properties in FreeCAD panel.

    Property names (distinct from metric nut and ASME bolt props):
      Thread_Type_Nut        — series  (UNC / UNF / UN / UNEF / UNS / UNR)
      Thread_TPI_Nut         — TPI     (e.g. "8", "20")
      Thread_Class_Nut_ASME  — class   (1B / 2B / 3B)

    Cascade visibility mirrors FSThreadingMetricInternal.set_nut_thread_visibility:
      Thread_Type_Nut   → always shown when thread_on
      Thread_TPI_Nut    → shown when thread_on (populated from Thread_Type_Nut)
      Thread_Class_Nut_ASME → shown only when thread_on AND TPI is selected
    """
    # Thread_Type_Nut: visible whenever thread is on
    if hasattr(fp, "Thread_Type_Nut"):
        fp.setEditorMode("Thread_Type_Nut", 0 if thread_on else 2)

    # Thread_TPI_Nut: visible when thread is on
    if hasattr(fp, "Thread_TPI_Nut"):
        fp.setEditorMode("Thread_TPI_Nut", 0 if thread_on else 2)

    # Thread_TPI_Nut_Custom: visible only when thread_on AND "Custom" is selected
    _tpi = ""
    if hasattr(fp, "Thread_TPI_Nut"):
        try:
            _tpi = str(fp.Thread_TPI_Nut)
        except Exception:
            pass
    _is_custom = thread_on and (_tpi == "Custom")
    if hasattr(fp, "Thread_TPI_Nut_Custom"):
        fp.setEditorMode("Thread_TPI_Nut_Custom", 0 if _is_custom else 2)

    # Thread_Class_Nut_ASME: visible only when thread_on AND a TPI is selected
    _cls_ready = thread_on and bool(_tpi)
    if hasattr(fp, "Thread_Class_Nut_ASME"):
        fp.setEditorMode("Thread_Class_Nut_ASME", 0 if _cls_ready else 2)
