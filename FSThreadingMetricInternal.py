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
  valid_tpis_for_dia_type(dia_str, series_str)           -> list[str]   e.g. ["8","12","Custom"]
  valid_classes_for_dia_tpi_type(dia, tpi, series)       -> list[str]   e.g. ["1B","2B","3B"]
  custom_tpi_range_for_dia(dia_str)                      -> (min_tpi, max_tpi)
  bore_dia_from_table(fa, dia_str, tpi, series, cls)     -> float mm    bore_eff with deviation
  resolve_nut_tpi(fa)                                    -> float
  set_asme_nut_visibility(fp, thread_on)                 -> None

FreeCAD property names used (ASME nut, distinct from metric nut and ASME bolt props)
-----------------------------------------------------------------------
  Thread_Type_Nut        — series dropdown  (UNC / UNF / UN / UNEF / UNS / UNR)
  Thread_TPI_Nut         — TPI dropdown     (e.g. "8", "20", "Custom")
  Thread_TPI_Nut_Custom  — integer field    shown only when Thread_TPI_Nut == "Custom"
  Thread_Class_Nut_ASME  — class dropdown   (1B / 2B / 3B)

Custom TPI behaviour
--------------------
When the user selects "Custom" in Thread_TPI_Nut:
  • Thread_TPI_Nut_Custom is shown (integer spinner).
  • The class dropdown is populated from the nearest standard TPI for that diameter.
  • bore_dia_from_table / resolve_nut_tpi fall back to the nearest standard TPI
    from the CSV to pick Minor_Dia_Max; the custom TPI is used for pitch / cutter.
  • custom_tpi_range_for_dia() returns (min_tpi, max_tpi) from the CSV for the
    selected diameter so callers can clamp the spinner.

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
BORE_DEVIATION_PCT_SMALL = 0.0   # % ADDED at smallest dia in CSV
BORE_DEVIATION_PCT_LARGE = 0.0   # % ADDED at largest  dia in CSV
"""

import os as _os, math as _math, functools as _functools

_CSV_DIR       = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "FsData")
_CSV_ASME_NUT  = _os.path.join(_CSV_DIR, "un_unr_internal_thread_minor_dia.csv")

# ── Bore deviation constants ──────────────────────────────────────────────────
BORE_DEVIATION_PCT_SMALL = 0.0
BORE_DEVIATION_PCT_LARGE = 0.0


# ── Diameter string normalisation ─────────────────────────────────────────────

def _clean_dia(dia_str):
    """Normalise ASME diameter string to match the CSV key format.

    The CSV uses hyphen-separated mixed fractions: "1-3/4", "2-1/4", etc.
    FreeCAD passes diameters with an 'in' suffix and space-separated fractions:
    "1 3/4in", "2 1/4in".

    Conversion steps:
      1. Strip surrounding whitespace.
      2. Remove 'in' suffix (and any stray '"' inch character).
      3. If a space AND a slash are both present → space-separated mixed
         fraction → replace the space with '-' to get "1-3/4".
      4. Strip again.

    Examples
    --------
    "1 3/4in"  → "1-3/4"    ← was broken before (returned "1 3/4")
    "1/4in"    → "1/4"
    "1in"      → "1"
    "2 1/4in"  → "2-1/4"
    "#10"      → "#10"
    "1-3/4"    → "1-3/4"    (CSV keys passed directly — idempotent)
    """
    s = str(dia_str).strip()
    # Remove inch markers
    s = s.replace("in", "").replace('"', "").strip()
    # "1 3/4" (space + fraction) → "1-3/4"
    if " " in s and "/" in s:
        parts = s.split(" ", 1)
        if "/" in parts[1]:
            s = parts[0].strip() + "-" + parts[1].strip()
    return s.strip()


# ── Inch string → mm conversion ───────────────────────────────────────────────

def _inch_str_to_mm(dia_str):
    """Convert ASME diameter string to mm for deviation interpolation.

    Accepts both CSV-key format ("1-3/4") and FreeCAD format ("1 3/4in").
    Always normalises through _clean_dia first.

    Examples:
      '#0'    → 1.524       (0.060 in)
      '1/4'   → 6.35
      '1-1/2' → 38.1
      '1 1/2' → 38.1
      '1'     → 25.4
      '6'     → 152.4
    """
    # Normalise to CSV key format first
    s = _clean_dia(dia_str)

    # Numbered sizes (#0 – #12)
    _num_map = {
        "#0": 0.060, "#1": 0.073, "#2": 0.086, "#3": 0.099,
        "#4": 0.112, "#5": 0.125, "#6": 0.138, "#8": 0.164,
        "#10": 0.190, "#12": 0.216,
    }
    if s in _num_map:
        return _num_map[s] * 25.4

    # Hyphen-separated mixed fractions: "1-3/4", "2-1/4", etc.
    if "-" in s and "/" in s:
        parts = s.split("-", 1)
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

    NOTE: CSV Dia column uses hyphen-separated mixed fractions ("1-3/4").
    All keys are stored in that canonical form. _clean_dia() normalises
    FreeCAD diameter strings to this form before any lookup.
    """
    import csv
    table = {}
    try:
        with open(_CSV_ASME_NUT, newline="", encoding="utf-8") as f:
            lines = f.readlines()
        reader = csv.DictReader(lines[1:])   # skip row 0 (table name)
        for row in reader:
            try:
                # Store CSV Dia as-is (already in "1-3/4" form) — normalise
                # for safety in case the CSV format ever changes.
                dia    = _clean_dia(row["Dia"].strip())
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


# ── Nearest standard TPI helper ───────────────────────────────────────────────

def nearest_standard_tpi(dia_str, series_str, custom_tpi):
    """Return the TPI from the CSV table nearest to custom_tpi.

    Used when the user picks "Custom" TPI so that the class dropdown and
    bore lookup can still use a valid standard value.

    Parameters
    ----------
    dia_str    : normalised diameter string (passed through _clean_dia internally)
    series_str : series string e.g. "UNC", "UN"
    custom_tpi : float  — user-entered custom TPI value
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    tpis   = sorted({k[1] for k in _asme_nut_table() if k[0] == dia and k[2] == series})
    if not tpis:
        # Try all series at this diameter
        tpis = sorted({k[1] for k in _asme_nut_table() if k[0] == dia})
    if not tpis:
        return float(custom_tpi)
    try:
        ctpi = float(custom_tpi)
    except (ValueError, TypeError):
        return tpis[0]
    return min(tpis, key=lambda t: abs(t - ctpi))


# ── Custom TPI range helper ───────────────────────────────────────────────────

def custom_tpi_range_for_dia(dia_str, series_str=""):
    """Return (min_tpi, max_tpi) integer tuple for the given diameter.

    Used to set sensible bounds on the Thread_TPI_Nut_Custom spinner.
    Returns (1, 80) as a safe fallback if no rows are found.

    Parameters
    ----------
    dia_str    : any ASME diameter string (normalised internally)
    series_str : optional series filter; if blank, uses all series for that dia
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    if series:
        tpis = sorted({k[1] for k in _asme_nut_table()
                       if k[0] == dia and k[2] == series})
    else:
        tpis = sorted({k[1] for k in _asme_nut_table() if k[0] == dia})

    if len(tpis) >= 2:
        return (int(min(tpis)), int(max(tpis)))
    if len(tpis) == 1:
        t = int(tpis[0])
        return (max(1, t - 4), t + 4)
    return (1, 80)


# ── Dropdown helpers ──────────────────────────────────────────────────────────

def valid_types_for_dia(dia_str):
    """Return ordered list of series (thread types) available for this diameter.

    e.g. valid_types_for_dia("1in") → ["UNC", "UNF", "UNEF", "UN", "UNS", "UNR"]

    UNR is appended when UN is present — UNR is an external-only form; the nut
    internal thread is the same UN table.

    FreeCAD passes diameters like "1 3/4in"; _clean_dia normalises to "1-3/4"
    so the CSV lookup succeeds.
    """
    dia = _clean_dia(dia_str)
    series_set = {k[2] for k in _asme_nut_table() if k[0] == dia}
    order  = ["UNC", "UNF", "UNEF", "UN", "UNS"]
    result = [s for s in order if s in series_set]
    if "UN" in result:
        result.append("UNR")   # UNR shares UN rows
    return result or ["UNC"]


def valid_tpis_for_dia_type(dia_str, series_str):
    """Return sorted TPI strings (descending = coarse first) plus "Custom".

    Always appends "Custom" as the last option so users can type any TPI.
    UNR maps to UN rows.
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()
    tpis   = sorted(
        {k[1] for k in _asme_nut_table() if k[0] == dia and k[2] == series},
        reverse=True,
    )
    std = [str(int(t)) if t == int(t) else str(t) for t in tpis]
    return std + ["Custom"]


def valid_classes_for_dia_tpi_type(dia_str, tpi, series_str):
    """Return sorted class strings for this dia + TPI + series.

    When tpi is "Custom", uses the nearest standard TPI to determine classes.
    e.g. → ["1B", "2B", "3B"]
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()

    tpi_str = str(tpi).strip()
    if tpi_str == "Custom":
        # Use all classes available for this dia+series across any TPI
        classes = sorted(
            {k[3] for k in _asme_nut_table()
             if k[0] == dia and k[2] == series}
        )
        return classes or ["2B"]

    try:
        tpi_f = float(tpi_str)
    except (ValueError, TypeError):
        return ["2B"]
    classes = sorted(
        {k[3] for k in _asme_nut_table()
         if k[0] == dia and k[1] == tpi_f and k[2] == series}
    )
    return classes or ["2B"]


# ── Bore diameter ─────────────────────────────────────────────────────────────

def minor_dia_from_table(dia_str, tpi, series_str, cls_str):
    """Return raw Minor_Dia_Max in mm (NO deviation). Returns None if not found.

    When tpi is "Custom" or a non-standard value, the nearest standard TPI is
    used for the CSV lookup so a meaningful bore size is always returned.

    Parameters
    ----------
    dia_str    : ASME diameter string e.g. "1 3/4in", "1/2in", "#10"
    tpi        : TPI float/string or "Custom"
    series_str : series string e.g. "UNC", "UN", "UNR"
    cls_str    : class string e.g. "2B"
    """
    dia    = _clean_dia(dia_str)
    series = "UN" if str(series_str).strip() == "UNR" else str(series_str).strip()

    tpi_str = str(tpi).strip()
    if tpi_str == "Custom":
        # No custom value to resolve here — return None; caller uses fallback formula
        return None

    try:
        tpi_f = float(tpi_str)
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

    For Custom TPI: uses nearest standard TPI from CSV for the bore lookup so
    the bore wall is correctly sized, while the helix pitch uses the custom value.

    Falls back to ASME formula  (nominal_mm − 1.0825 × P_mm)  if CSV miss.
    """
    tpi_str = str(tpi).strip()
    is_custom = (tpi_str == "Custom")

    # Resolve effective TPI for bore lookup
    if is_custom:
        # Read the custom integer value from fa
        custom_val = int(getattr(fa, "Thread_TPI_Nut_Custom", 0) or 0)
        if custom_val > 0:
            effective_tpi_for_lookup = nearest_standard_tpi(dia_str, series_str, custom_val)
        else:
            effective_tpi_for_lookup = None
    else:
        try:
            effective_tpi_for_lookup = float(tpi_str)
        except (ValueError, TypeError):
            effective_tpi_for_lookup = None

    minor_mm = None
    if effective_tpi_for_lookup is not None:
        minor_mm = minor_dia_from_table(dia_str, effective_tpi_for_lookup, series_str, cls_str)

    try:
        dia_mm = _inch_str_to_mm(_clean_dia(dia_str))
    except Exception:
        dia_mm = 25.4  # 1 inch fallback

    if minor_mm is None:
        # Fallback: ASME formula for minor diameter
        try:
            if is_custom:
                tpi_for_formula = float(getattr(fa, "Thread_TPI_Nut_Custom", 8) or 8)
            else:
                tpi_for_formula = float(tpi_str) if tpi_str else 8.0
            P_mm  = 25.4 / tpi_for_formula if tpi_for_formula > 0 else 1.0
        except (ValueError, TypeError):
            P_mm = 1.0
        minor_mm = dia_mm - 1.0825 * P_mm

    pct       = _interpolated_deviation_pct(dia_mm)
    deviation = minor_mm * pct / 100.0
    bore_eff  = minor_mm + deviation

    try:
        import FreeCAD as _FC
        _lookup_tpi_label = (
            f"Custom → nearest={effective_tpi_for_lookup}"
            if is_custom else tpi_str
        )
        _FC.Console.PrintMessage(
            f"[ASMENutBore] dia={dia_str} TPI={_lookup_tpi_label} "
            f"series={series_str} cls={cls_str}\n"
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
    """Resolve effective TPI (float) for ASME nut from fa attributes.

    Priority:
      1. Thread_TPI_Nut == "Custom"  → use Thread_TPI_Nut_Custom integer
      2. Thread_TPI_Nut  (standard dropdown value)
      3. fa.calc_tpi     (custom TPI override from elsewhere)
      4. Coarsest standard TPI from CSV for this dia + type

    Always returns a positive float or None.
    """
    tpi_prop = str(getattr(fa, "Thread_TPI_Nut", "") or "")

    if tpi_prop == "Custom":
        custom_val = int(getattr(fa, "Thread_TPI_Nut_Custom", 0) or 0)
        if custom_val > 0:
            return float(custom_val)
        # Custom selected but no value yet — fall through to coarsest

    elif tpi_prop and tpi_prop not in ("", "Custom"):
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
    # valid_tpis_for_dia_type always ends with "Custom" — skip it
    std_tpis = [t for t in tpis if t != "Custom"]
    if std_tpis:
        return float(std_tpis[-1])   # coarsest = last in descending list

    return None


# ── FreeCAD panel visibility ──────────────────────────────────────────────────

def set_asme_nut_visibility(fp, thread_on):
    """Show/hide ASME internal nut thread properties in FreeCAD panel.

    Property names (distinct from metric nut and ASME bolt props):
      Thread_Type_Nut        — series  (UNC / UNF / UN / UNEF / UNS / UNR)
      Thread_TPI_Nut         — TPI dropdown (standard values + "Custom")
      Thread_TPI_Nut_Custom  — integer spinner (only when TPI == "Custom")
      Thread_Class_Nut_ASME  — class   (1B / 2B / 3B)

    Cascade:
      Thread_Type_Nut   → shown whenever thread_on
      Thread_TPI_Nut    → shown whenever thread_on
      Thread_TPI_Nut_Custom → shown when thread_on AND Thread_TPI_Nut == "Custom"
      Thread_Class_Nut_ASME → shown when thread_on AND a TPI is effectively selected
    """
    # Thread_Type_Nut: visible whenever thread is on
    if hasattr(fp, "Thread_Type_Nut"):
        fp.setEditorMode("Thread_Type_Nut", 0 if thread_on else 2)

    # Thread_TPI_Nut: visible when thread is on
    if hasattr(fp, "Thread_TPI_Nut"):
        fp.setEditorMode("Thread_TPI_Nut", 0 if thread_on else 2)

    # Thread_TPI_Nut_Custom: visible only when TPI == "Custom"
    _tpi = ""
    if hasattr(fp, "Thread_TPI_Nut"):
        try:
            _tpi = str(fp.Thread_TPI_Nut)
        except Exception:
            pass
    _is_custom = thread_on and (_tpi == "Custom")
    if hasattr(fp, "Thread_TPI_Nut_Custom"):
        fp.setEditorMode("Thread_TPI_Nut_Custom", 0 if _is_custom else 2)

    # Thread_Class_Nut_ASME: visible when thread_on AND a TPI is selected
    _cls_ready = thread_on and bool(_tpi)
    if hasattr(fp, "Thread_Class_Nut_ASME"):
        fp.setEditorMode("Thread_Class_Nut_ASME", 0 if _cls_ready else 2)