# -*- coding: utf-8 -*-
###############################################################################
#
#  FastenersCmd.py
#
#  Copyright 2015 Shai Seger <shiais at gmail dot com>
#  BSP modifications (c) 2025-2026 Andrey Bekhterev <info at bekhterev dot in>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
###############################################################################

import FreeCAD
import os
import re
import FastenerBase
from FastenerBase import FSParam
from FastenerBase import FSBaseObject
import ScrewMaker
import FSutils
from FSutils import iconPath
from FSAliases import FSGetIconAlias, FSGetTypeAlias
from FreeCAD import Units

import sys as _sys, os as _os
_wb_root = _os.path.dirname(_os.path.abspath(__file__))
if _wb_root not in _sys.path:
    _sys.path.insert(0, _wb_root)

import FSThreadingASME   as _TA
import FSThreadingMetric as _TM
try:
    import FSThreadingMetricInternal as _TMI
except Exception:
    _TMI = None
try:
    import FSThreadingASMEInternal as _TAI
except Exception:
    _TAI = None

# ── Compatibility shim ────────────────────────────────────────────────────────
# Guard against older FSThreadingASME that may not export bolt_nominal.
# This lets FastenersCmd load safely even if FSThreadingASME was not updated.
if not hasattr(_TA, "bolt_nominal"):
    def _bolt_nominal_shim(diam_str):
        s = str(diam_str or "").strip().replace('"', "in")
        if not s or s == "Auto":
            return ""
        return s.rstrip("in").rstrip()
    _TA.bolt_nominal = _bolt_nominal_shim

if not hasattr(_TA, "valid_thread2types_for_dia"):
    _TA.valid_thread2types_for_dia = lambda nominal: ["UNC", "UN", "UNR"]

if not hasattr(_TA, "tpi_enum_options"):
    _TA.tpi_enum_options = lambda nominal, tt: ["Custom"]

if not hasattr(_TA, "valid_classes_for_series_tpi"):
    _TA.valid_classes_for_series_tpi = lambda nom, ser, tpi: ["2A", "3A"]

if not hasattr(_TA, "all_classes_for_nominal"):
    _TA.all_classes_for_nominal = lambda nominal: ["2A", "3A"]

if not hasattr(_TA, "outer_dia_mm"):
    _TA.outer_dia_mm = lambda *a, **kw: None

if not hasattr(_TA, "get_shank_dia"):
    _TA.get_shank_dia = lambda fa, fallback: fallback

if not hasattr(_TA, "resolve_thread_params"):
    _TA.resolve_thread_params = lambda nom, fa: {
        "tpi": 0, "series": "UNC", "cls": "2A",
        "P_mm": 1.27, "is_unr": False, "thread_type": "UNC"}

if not hasattr(_TA, "_interpolated_deviation_pct"):
    _TA._interpolated_deviation_pct = lambda dia_mm: 0.0

translate = FreeCAD.Qt.translate
screwMaker = ScrewMaker.Instance

translate("FastenerCmdTreeView", "Screw")
translate("FastenerCmdTreeView", "Washer")
translate("FastenerCmdTreeView", "Nut")
translate("FastenerCmdTreeView", "ThreadedRod")
translate("FastenerCmdTreeView", "PressNut")
translate("FastenerCmdTreeView", "Standoff")
translate("FastenerCmdTreeView", "Spacer")
translate("FastenerCmdTreeView", "Stud")
translate("FastenerCmdTreeView", "ScrewTap")
translate("FastenerCmdTreeView", "ScrewTapBSPP")
translate("FastenerCmdTreeView", "ScrewDie")
translate("FastenerCmdTreeView", "ScrewDieBSPP")
translate("FastenerCmdTreeView", "Insert")
translate("FastenerCmdTreeView", "RetainingRing")
translate("FastenerCmdTreeView", "T-Slot")
translate("FastenerCmdTreeView", "SetScrew")
translate("FastenerCmdTreeView", "HexKey")
translate("FastenerCmdTreeView", "Nail")
translate("FastenerCmdTreeView", "Pin")
translate("FastenerCmdTreeView", "Thumbscrew")

# fmt: off
ScrewParameters = {"Type", "Diameter",
                   "MatchOuter", "Thread", "LeftHanded", "Length",
                   "TThread"}
ScrewParametersLC = {"Type", "Diameter", "MatchOuter",
                     "Thread", "LeftHanded", "Length", "LengthCustom",
                     "TPitch", "TLength", "TThread", "TType"}
# Fixed-geometry screws: no length selection needed
FixedScrewParameters = {"Type", "Diameter", "MatchOuter", "Thread", "TLength"}
# Eyebolt: fixed shank length (from CSV), full ASME threading UI (UNC/UNF TPI/class)
EyeboltParameters = {"Type", "Diameter", "MatchOuter", "Thread", "TPitch", "TLength", "TThread"}
RodParameters = {"Type", "Diameter", "MatchOuter", "Thread",
                 "LeftHanded", "lengthArbitrary", "DiameterCustom", "PitchCustom",
                 "TPitch", "TLength", "TThread", "TType"}
NutParameters = {"Type", "Diameter", "MatchOuter", "Thread", "LeftHanded",
                  "TNutThread", "TPitch"}
WoodInsertParameters = {"Type", "Diameter", "MatchOuter", "Thread", "LeftHanded"}
HeatInsertParameters = {"Type", "Diameter", "lengthArbitrary", "ExternalDiam", "MatchOuter", "Thread", "LeftHanded"}
WasherParameters = {"Type", "Diameter", "MatchOuter"}
# Types 6, 7 (internal) — gap between teeth is called "Recess Width"
ToothLockWasherParameters = {"Type", "Diameter", "MatchOuter",
                             "ToothCount", "ToothRecessWidth", "ToothLength"}
# Type 9 (conical external) — no twist angle
ToothLockWasherType9Parameters = {"Type", "Diameter", "MatchOuter",
                                  "ToothCount", "ToothWidth", "ToothLength"}
# Type 8 only — includes twist angle
ToothLockWasherType8Parameters = {"Type", "Diameter", "MatchOuter",
                                  "ToothCount", "ToothTwistAngle", "ToothWidth", "ToothLength"}
PCBStandoffParameters = {"Type", "Diameter", "MatchOuter", "Thread",
                         "LeftHanded", "Thread_Length", "LenByDiamAndWidth", "LengthCustom", "widthCode",
                         "TPitch", "TLength", "TThread"}
BellevilleWasherParameters = {"Type", "Diameter", "MatchOuter",
                              "DiameterCustom", "WasherOuterDiaCustom",
                              "WasherThicknessCustom", "WasherHeightCustom"}
PCBSpacerParameters = {"Type", "Diameter", "MatchOuter", "Thread",
                       "LeftHanded", "LenByDiamAndWidth", "LengthCustom", "widthCode"}
PEMPressNutParameters = {"Type", "Diameter",
                         "MatchOuter", "Thread", "LeftHanded", "ThicknessCode",
                         "TPitch", "TNutThread"}
PEMStandoffParameters = {"Type", "Diameter", "MatchOuter",
                         "Thread", "LeftHanded", "Length", "blindness",
                         "TPitch", "TLength", "TThread"}
RetainingRingParameters = {"Type", "Diameter", "MatchOuter"}
PinParameters = {"Type", "Diameter", "Length", "LengthCustom", "LeftHanded"}
TSlotNutParameters = {"Type", "Diameter", "MatchOuter", "Thread", "LeftHanded", "SlotWidth", "TNutThread"}
TSlotBoltParameters = {"Type", "Diameter", "Length", "LengthCustom",
                       "MatchOuter", "Thread", "LeftHanded", "SlotWidth",
                       "TPitch", "TLength", "TThread"}
HexKeyParameters = {"Type", "Diameter", "MatchOuter", "KeySize"}
NailParameters = {"Type", "Diameter", "MatchOuter"}
FastenerAttribs = ['Type', 'Diameter', 'Thread', 'LeftHanded', 'MatchOuter', 'Length',
                   'LengthCustom', 'Width', 'DiameterCustom', 'PitchCustom', 'Tcode',
                   'Blind', 'ScrewLength', "SlotWidth", 'ExternalDiam', 'KeySize', 'SecurityPin',
                   'ThreadPitch', 'Thread_TPI', 'Thread_Length', 'Thread_Type',
                   'Thread_Class', 'Thread_TPI', 'Thread_TPI_Custom',
                   # Metric data-driven thread properties (metric_thread_dia.csv)
                   'Thread_Pitch', 'Thread_Class_ISO',
                   'Thread_Root',
                   'Thread_Pitch_Nut', 'Thread_Pitch_Nut_Custom', 'Thread_Class_Nut',
                   # ASME nut internal thread properties (un_unr_internal_thread_minor_dia.csv)
                   'Thread_Type_Nut', 'Thread_TPI_Nut', 'Thread_Class_Nut_ASME',
                   # Security pin -- must be in key so changes invalidate the cache
                   'SecurityPin', 'SecurityPinDiameter',
                   # Tooth lock washer user parameters
                   'ToothCount', 'ToothTwistAngle', 'ToothWidth', 'ToothLength',
                   'ToothRecessWidth']

HexHeadGroup        = translate("FastenerCmd", "Hex head")
HexagonSocketGroup  = translate("FastenerCmd", "Hexagon socket")
HexalobularSocketGroup = translate("FastenerCmd", "Hexalobular socket")
SlottedGroup        = translate("FastenerCmd", "Slotted")
HCrossGroup         = translate("FastenerCmd", "H cross")
NutGroup            = translate("FastenerCmd", "Nut")
WasherGroup         = translate("FastenerCmd", "Washer")
OtherHeadGroup      = translate("FastenerCmd", "Misc head")
ThreadedRodGroup    = translate("FastenerCmd", "ThreadedRod")
InsertGroup         = translate("FastenerCmd", "Inserts")
RetainingRingGroup  = translate("FastenerCmd", "Retaining Rings")
TSlotGroup          = translate("FastenerCmd", "T-Slot Fasteners")
SetScrewGroup       = translate("FastenerCmd", "Set screws")
NailGroup           = translate("FastenerCmd", "Nails")
PinGroup            = translate("FastenerCmd", "Pins")
ThumbScrewGroup     = translate("FastenerCmd", "Thumb screws")
GroundScrewGroup    = translate("FastenerCmd", "Ground screws")

CMD_HELP = 0
CMD_GROUP = 1
CMD_PARAMETER_GRP = 2
CMD_STD_GROUP = 3

FSScrewCommandTable = {
    "ASMEB18.2.1.1":  (translate("FastenerCmd", "UNC Square bolts"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.2.1.2":  (translate("FastenerCmd", "UNC Hex bolts"), HexHeadGroup, ScrewParametersLC),
    "ASMEB18.2.1.3":  (translate("FastenerCmd", "UNC Heavy hex bolts"), HexHeadGroup, ScrewParametersLC),
    "ASMEB18.2.1.6":  (translate("FastenerCmd", "UNC Hex head screws"), HexHeadGroup, ScrewParametersLC),
    "ASMEB18.2.1.7":  (translate("FastenerCmd", "UNC Heavy hex screws"), HexHeadGroup, ScrewParametersLC),
    "ASMEB18.2.1.8":  (translate("FastenerCmd", "UNC Hex head screws with flange"), HexHeadGroup, ScrewParametersLC),
    "ASMEB18.2.1.9":  (translate("FastenerCmd", "UNC External 6-Lobe (Torx) flanged screws"), HexHeadGroup, ScrewParametersLC),
    "ASMEB18.2.5M":   (translate("FastenerCmd", "Metric 12-Point flange bolts"), HexHeadGroup, ScrewParametersLC),
    "DIN571":  (translate("FastenerCmd", "Hex head wood screw"), HexHeadGroup, ScrewParametersLC),
    "DIN933":  (translate("FastenerCmd", "Hex head screw"), HexHeadGroup, ScrewParametersLC),
    "DIN961":  (translate("FastenerCmd", "Hex head screw"), HexHeadGroup, ScrewParametersLC),
    "EN1662":  (translate("FastenerCmd", "Hexagon bolt with flange, small series"), HexHeadGroup, ScrewParametersLC),
    "EN1665":  (translate("FastenerCmd", "Hexagon bolt with flange, heavy series"), HexHeadGroup, ScrewParametersLC),
    "ISO4014": (translate("FastenerCmd", "Hex head bolt - Product grades A and B"), HexHeadGroup, ScrewParametersLC),
    "ISO4015": (translate("FastenerCmd", "Hexagon head bolts with reduced shank"), HexHeadGroup, ScrewParametersLC),
    "ISO4016": (translate("FastenerCmd", "Hex head bolts - Product grade C"), HexHeadGroup, ScrewParametersLC),
    "ISO4017": (translate("FastenerCmd", "Hex head screw - Product grades A and B"), HexHeadGroup, ScrewParametersLC),
    "ISO4018": (translate("FastenerCmd", "Hex head screws - Product grade C"), HexHeadGroup, ScrewParametersLC),
    "ISO4162": (translate("FastenerCmd", "Hexagon bolts with flange - Small series - Product grade A with driving feature of product grade B"), HexHeadGroup, ScrewParametersLC),
    "ISO8676": (translate("FastenerCmd", "Hex head screws with fine pitch thread"), HexHeadGroup, ScrewParametersLC),
    "ISO8765": (translate("FastenerCmd", "Hex head bolt with fine pitch thread"), HexHeadGroup, ScrewParametersLC),
    "ISO15071": (translate("FastenerCmd", "Hexagon bolts with flange - Small series - Product grade A"), HexHeadGroup, ScrewParametersLC),
    "ISO15072": (translate("FastenerCmd", "Hexagon bolts with flange with fine pitch thread - Small series - Product grade A"), HexHeadGroup, ScrewParametersLC),
    "ASMEB18.3.1A": (translate("FastenerCmd", "UNC Hex socket head cap screws"), HexagonSocketGroup, ScrewParametersLC),
    "ASMEB18.3.1G": (translate("FastenerCmd", "UNC Hex socket head cap screws with low head"), HexagonSocketGroup, ScrewParametersLC),
    "ASMEB18.3.2":  (translate("FastenerCmd", "UNC Hex socket countersunk head screws"), HexagonSocketGroup, ScrewParametersLC),
    "ASMEB18.3.3A": (translate("FastenerCmd", "UNC Hex socket button head screws"), HexagonSocketGroup, ScrewParametersLC),
    "ASMEB18.3.3B": (translate("FastenerCmd", "UNC Hex socket button head screws with flange"), HexagonSocketGroup, ScrewParametersLC),
    "ASMEB18.3.4":  (translate("FastenerCmd", "UNC Hexagon socket head shoulder screws"), HexagonSocketGroup, ScrewParametersLC),
    "DIN6912":  (translate("FastenerCmd", "Hexagon socket head cap screws with low head with centre"), HexagonSocketGroup, ScrewParametersLC),
    "DIN7984":  (translate("FastenerCmd", "Hexagon socket head cap screws with low head"), HexagonSocketGroup, ScrewParametersLC),
    "ISO2936":  (translate("FastenerCmd", "Hexagon socket screw keys"), HexagonSocketGroup, HexKeyParameters),
    "ISO4762":  (translate("FastenerCmd", "Hexagon socket head cap screw"), HexagonSocketGroup, ScrewParametersLC),
    "ISO7379":  (translate("FastenerCmd", "Hexagon socket head shoulder screw"), HexagonSocketGroup, ScrewParametersLC),
    "ISO7380-1":(translate("FastenerCmd", "Hexagon socket button head screw"), HexagonSocketGroup, ScrewParametersLC),
    "ISO7380-2":(translate("FastenerCmd", "Hexagon socket button head screws with collar"), HexagonSocketGroup, ScrewParametersLC),
    "ISO10642": (translate("FastenerCmd", "Hexagon socket countersunk head screw"), HexagonSocketGroup, ScrewParametersLC),
    "ISO14579": (translate("FastenerCmd", "Hexalobular socket head cap screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ISO14580": (translate("FastenerCmd", "Hexalobular socket cheese head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ISO14581": (translate("FastenerCmd", "Hexalobular socket countersunk flat head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ISO14582": (translate("FastenerCmd", "Hexalobular socket countersunk head screws, high head"), HexalobularSocketGroup, ScrewParametersLC),
    "ISO14583": (translate("FastenerCmd", "Hexalobular socket pan head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ISO14584": (translate("FastenerCmd", "Hexalobular socket raised countersunk head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ASMEB18.6.1.2":  (translate("FastenerCmd", "Slotted flat countersunk head wood screws"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.1.4":  (translate("FastenerCmd", "Slotted oval countersunk head wood screws"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.3.1A": (translate("FastenerCmd", "UNC slotted countersunk flat head screws"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.3.4A": (translate("FastenerCmd", "UNC Slotted oval countersunk head screws"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.3.9A": (translate("FastenerCmd", "UNC Slotted pan head screws"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.3.10A":(translate("FastenerCmd", "UNC Slotted fillister head screws"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.3.12A":(translate("FastenerCmd", "UNC Slotted truss head screws"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.3.12B":(translate("FastenerCmd", "UNC Cross recessed truss head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.16A":(translate("FastenerCmd", "UNC Slotted round head screws"), SlottedGroup, ScrewParametersLC),
    "DIN84":    (translate("FastenerCmd", "(Superseded by ISO 1207) Slotted cheese head screw"), SlottedGroup, ScrewParametersLC),
    "DIN96":    (translate("FastenerCmd", "Slotted half round head wood screw"), SlottedGroup, ScrewParametersLC),
    "GOST1144-1":(translate("FastenerCmd", "(Type 1) Half — round head wood screw"), SlottedGroup, ScrewParametersLC),
    "GOST1144-2":(translate("FastenerCmd", "(Type 2) Half — round head wood screw"), SlottedGroup, ScrewParametersLC),
    "ISO1207":  (translate("FastenerCmd", "Slotted cheese head screw"), SlottedGroup, ScrewParametersLC),
    "ISO1580":  (translate("FastenerCmd", "Slotted pan head screw"), SlottedGroup, ScrewParametersLC),
    "ISO2009":  (translate("FastenerCmd", "Slotted countersunk flat head screw"), SlottedGroup, ScrewParametersLC),
    "ISO2010":  (translate("FastenerCmd", "Slotted raised countersunk head screw"), SlottedGroup, ScrewParametersLC),
    "ASMEB18.6.1.3":  (translate("FastenerCmd", "Cross recessed flat countersunk head wood screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.1.5":  (translate("FastenerCmd", "Cross recessed oval countersunk head wood screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.1B": (translate("FastenerCmd", "UNC Cross recessed countersunk flat head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.1C": (translate("FastenerCmd", "UNC Hexalobular socket countersunk flat head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ASMEB18.6.3.4B": (translate("FastenerCmd", "UNC Cross recessed oval countersunk head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.4C": (translate("FastenerCmd", "UNC Hexalobular socket oval countersunk head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ASMEB18.6.3.9B": (translate("FastenerCmd", "UNC Cross recessed pan head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.10B":(translate("FastenerCmd", "UNC Cross recessed fillister head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.9C": (translate("FastenerCmd", "UNC Hexalobular socket pan head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ASMEB18.6.3.10C":(translate("FastenerCmd", "UNC Hexalobular socket fillister head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ASMEB18.6.3.12C":(translate("FastenerCmd", "UNC Hexalobular socket truss head screws"), HexalobularSocketGroup, ScrewParametersLC),
    "ASMEB18.6.3.16B":(translate("FastenerCmd", "UNC Cross recessed round head screws"), HCrossGroup, ScrewParametersLC),
    "DIN967":   (translate("FastenerCmd", "Cross recessed pan head screws with collar"), HCrossGroup, ScrewParametersLC),
    "DIN7996":  (translate("FastenerCmd", "Cross recessed pan head wood screw"), HCrossGroup, ScrewParametersLC),
    "GOST1144-3":(translate("FastenerCmd", "(Type 3) Half — round head wood screw"), HCrossGroup, ScrewParametersLC),
    "GOST1144-4":(translate("FastenerCmd", "(Type 4) Half — round head wood screw"), HCrossGroup, ScrewParametersLC),
    "ISO7045":  (translate("FastenerCmd", "Pan head screws type H cross recess"), HCrossGroup, ScrewParametersLC),
    "ISO7046":  (translate("FastenerCmd", "Countersunk flat head screws H cross r."), HCrossGroup, ScrewParametersLC),
    "ISO7047":  (translate("FastenerCmd", "Raised countersunk head screws H cross r."), HCrossGroup, ScrewParametersLC),
    "ISO7048":  (translate("FastenerCmd", "Cheese head screws with type H cross r."), HCrossGroup, ScrewParametersLC),
    "ISO7049-C":(translate("FastenerCmd", "Pan head self tapping screws with conical point, type H cross r."), HCrossGroup, ScrewParametersLC),
    "ISO7049-F":(translate("FastenerCmd", "Pan head self tapping screws with flat point, type H cross r."), HCrossGroup, ScrewParametersLC),
    "ISO7049-R":(translate("FastenerCmd", "Pan head self tapping screws with rounded point type H cross r."), HCrossGroup, ScrewParametersLC),
    "ISO13918":  (translate("FastenerCmd", "Welding stud"), OtherHeadGroup, ScrewParametersLC),
    "ISO13918A": (translate("FastenerCmd", "Internally threaded welding stud"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.5.2":(translate("FastenerCmd", "UNC Round head square neck bolts"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.9.3":(translate("FastenerCmd", "Type No. 3 Head Plow Bolt"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.9.4":(translate("FastenerCmd", "Type No. 4 Repair Head Plow Bolt"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.9.5":(translate("FastenerCmd", "Clipped Head Plow Bolt"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.9.6":(translate("FastenerCmd", "Type No. 6 Head Plow Bolt"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.9.7":(translate("FastenerCmd", "Type No. 7 Head Plow Bolt"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.9.9":(translate("FastenerCmd", "Elliptical Head Plow Bolt"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.15.1A":(translate("FastenerCmd", "UNC Type 1 Plain Pattern Eyebolt - Style A"), OtherHeadGroup, EyeboltParameters),
    "ASMEB18.15.1B":(translate("FastenerCmd", "UNC Type 1 Plain Pattern Eyebolt - Style B"), OtherHeadGroup, EyeboltParameters),
    "ASMEB18.15.2A":(translate("FastenerCmd", "UNC Type 2 Shoulder Pattern Eyebolt - Style A"), OtherHeadGroup, EyeboltParameters),
    "ASMEB18.15.2B":(translate("FastenerCmd", "UNC Type 2 Shoulder Pattern Eyebolt - Style B"), OtherHeadGroup, EyeboltParameters),
    "DIN478":   (translate("FastenerCmd", "Square head bolts with collar"), OtherHeadGroup, ScrewParametersLC),
    "DIN603":   (translate("FastenerCmd", "Mushroom head square neck bolts"), OtherHeadGroup, ScrewParametersLC),
    "ISO2342":  (translate("FastenerCmd", "headless screws with shank"), OtherHeadGroup, ScrewParametersLC),
    "ASMEB18.3.5A":(translate("FastenerCmd", "UNC Hexagon socket set screws with flat point"), SetScrewGroup, ScrewParametersLC),
    "ASMEB18.3.5B":(translate("FastenerCmd", "UNC Hexagon socket set screws with cone point"), SetScrewGroup, ScrewParametersLC),
    "ASMEB18.3.5C":(translate("FastenerCmd", "UNC Hexagon socket set screws with dog point"), SetScrewGroup, ScrewParametersLC),
    "ASMEB18.3.5D":(translate("FastenerCmd", "UNC Hexagon socket set screws with cup point"), SetScrewGroup, ScrewParametersLC),
    "ISO4026":  (translate("FastenerCmd", "Hexagon socket set screws with flat point"), SetScrewGroup, ScrewParametersLC),
    "ISO4027":  (translate("FastenerCmd", "Hexagon socket set screws with cone point"), SetScrewGroup, ScrewParametersLC),
    "ISO4028":  (translate("FastenerCmd", "Hexagon socket set screws with dog point"), SetScrewGroup, ScrewParametersLC),
    "ISO4029":  (translate("FastenerCmd", "Hexagon socket set screws with cup point"), SetScrewGroup, ScrewParametersLC),
    "ISO4766":  (translate("FastenerCmd", "Slotted socket set screws with flat point"), SetScrewGroup, ScrewParametersLC),
    "ISO7434":  (translate("FastenerCmd", "Slotted socket set screws with cone point"), SetScrewGroup, ScrewParametersLC),
    "ISO7435":  (translate("FastenerCmd", "Slotted socket set screws with long dog point"), SetScrewGroup, ScrewParametersLC),
    "ISO7436":  (translate("FastenerCmd", "Slotted socket set screws with cup point"), SetScrewGroup, ScrewParametersLC),
    "DIN464":          (translate("FastenerCmd", "Knurled thumb screws, high type"), ThumbScrewGroup, ScrewParametersLC),
    "DIN465":          (translate("FastenerCmd", "Slotted knurled thumb screws, high type"), ThumbScrewGroup, ScrewParametersLC),
    "DIN653":          (translate("FastenerCmd", "Knurled thumb screws, low type"), ThumbScrewGroup, ScrewParametersLC),
    "WOOTZ_ADJ_BREMS": (translate("FastenerCmd", "Adjustment screw, knurled head with retaining-clip groove (P/N 717090)"), ThumbScrewGroup, FixedScrewParameters),
    "GroundScrew":(translate("FastenerCmd", "round plate ground screw"), GroundScrewGroup, ScrewParametersLC),
    "ASMEB18.2.2.1A":(translate("FastenerCmd", "UNC Hex Machine screw nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.1B":(translate("FastenerCmd", "UNC Square machine screw nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.3": (translate("FastenerCmd", "UNC Square nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.5A":(translate("FastenerCmd", "UNC Hex nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.5B":(translate("FastenerCmd", "UNC Hex jam nuts"), NutGroup, NutParameters),
    # ── ASME B18.2.2 Table 11 — Heavy Hex Nut and Heavy Hex Jam Nut ──────────
    "ASMEB18.2.2.11A":(translate("FastenerCmd", "UNC Heavy hex nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.11B":(translate("FastenerCmd", "UNC Heavy hex jam nuts"), NutGroup, NutParameters),
    # ── ASME B18.2.2 Table 6/8 — Hex Slotted Nuts ────────────────────────────
    "ASMEB18.2.2.6": (translate("FastenerCmd", "UNC Hex slotted thin nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.8": (translate("FastenerCmd", "UNC Hex slotted wide nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.15": (translate("FastenerCmd", "UNC Hex castle nuts"), NutGroup, NutParameters),
    # ── ASME B18.2.2 Table 13A/13B — Hex Flange Nuts ─────────────────────────
    "ASMEB18.2.2.13A":(translate("FastenerCmd", "UNC Hex flange nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.13B":(translate("FastenerCmd", "UNC Large hex flange nuts"), NutGroup, NutParameters),
    # ── ASME B18.2.2 Table 14 — Hex Coupling Nuts ────────────────────────────
    "ASMEB18.2.2.14":(translate("FastenerCmd", "UNC Hex coupling nuts"), NutGroup, NutParameters),
    "ASMEB18.6.9A":  (translate("FastenerCmd", "Wing nuts, type A"), NutGroup, NutParameters),
    "DIN315":   (translate("FastenerCmd", "Wing nuts"), NutGroup, NutParameters),
    "DIN557":   (translate("FastenerCmd", "Square nuts"), NutGroup, NutParameters),
    "DIN562":   (translate("FastenerCmd", "Square nuts"), NutGroup, NutParameters),
    "DIN917":   (translate("FastenerCmd", "Cap nuts, thin style"), NutGroup, NutParameters),
    "DIN928":   (translate("FastenerCmd", "Square weld nuts"), NutGroup, NutParameters),
    "DIN929":   (translate("FastenerCmd", "Hexagonal weld nuts"), NutGroup, NutParameters),
    "DIN934":   (translate("FastenerCmd", "(Superseded by ISO 4035 and ISO 8673) Hexagon thin nuts, chamfered"), NutGroup, NutParameters),
    "DIN935":   (translate("FastenerCmd", "Slotted nuts"), NutGroup, NutParameters),
    "DIN935C":  (translate("FastenerCmd", "Castle nuts"), NutGroup, NutParameters),
    "DIN985":   (translate("FastenerCmd", "Nyloc nuts"), NutGroup, NutParameters),
    "DIN1587":  (translate("FastenerCmd", "Cap nuts"), NutGroup, NutParameters),
    "DIN6330":  (translate("FastenerCmd", "Hexagon nuts with a height of 1,5 d"), NutGroup, NutParameters),
    "DIN6331":  (translate("FastenerCmd", "Hexagon nuts with collar height 1,5 d"), NutGroup, NutParameters),
    "DIN6334":  (translate("FastenerCmd", "Elongated hexagon nuts"), NutGroup, NutParameters),
    "DIN7967":  (translate("FastenerCmd", "Self locking counter nuts"), NutGroup, WasherParameters),
    "EN1661":   (translate("FastenerCmd", "Hexagon nuts with flange"), NutGroup, NutParameters),
    "GOST11860-1":(translate("FastenerCmd", "(Type 1) Cap nuts"), NutGroup, NutParameters),
    "ISO4032":  (translate("FastenerCmd", "Hexagon nuts, Style 1"), NutGroup, NutParameters),
    "ISO4033":  (translate("FastenerCmd", "Hexagon nuts, Style 2"), NutGroup, NutParameters),
    "ISO4034":  (translate("FastenerCmd", "Hexagon nuts, Style 1"), NutGroup, NutParameters),
    "ISO4035":  (translate("FastenerCmd", "Hexagon thin nuts, chamfered"), NutGroup, NutParameters),
    # ── PATCH 2: ISO 7414 — Hexagon heavy nuts (metric) ──────────────────────
    "ISO7414":  (translate("FastenerCmd", "Hexagon heavy nuts"), NutGroup, NutParameters),
    # ─────────────────────────────────────────────────────────────────────────
    "ISO4161":  (translate("FastenerCmd", "Hexagon nuts with flange"), NutGroup, NutParameters),
    "ISO7040":  (translate("FastenerCmd", "Prevailing torque type hexagon nuts (with non-metallic insert)"), NutGroup, NutParameters),
    "ISO7041":  (translate("FastenerCmd", "Prevailing torque type hexagon nuts (with non-metallic insert), style 2"), NutGroup, NutParameters),
    "ISO7043":  (translate("FastenerCmd", "Prevailing torque type hexagon nuts with flange (with non-metallic insert)"), NutGroup, NutParameters),
    "ISO7044":  (translate("FastenerCmd", "Prevailing torque type all-metal hexagon nuts with flange"), NutGroup, NutParameters),
    "ISO7719":  (translate("FastenerCmd", "Prevailing torque type all-metal hexagon regular nuts"), NutGroup, NutParameters),
    "ISO7720":  (translate("FastenerCmd", "Prevailing torque type all-metal hexagon nuts, style 2"), NutGroup, NutParameters),
    "ISO8673":  (translate("FastenerCmd", "Hexagon regular nuts (style 1) with metric fine pitch thread — Product grades A and B"), NutGroup, NutParameters),
    "ISO8674":  (translate("FastenerCmd", "Hexagon high nuts (style 2) with metric fine pitch thread "), NutGroup, NutParameters),
    "ISO8675":  (translate("FastenerCmd", "Hexagon thin nuts chamfered (style 0) with metric fine pitch thread — Product grades A and B"), NutGroup, NutParameters),
    "ISO10511": (translate("FastenerCmd", "Prevailing torque type hexagon thin nuts (with non-metallic insert)"), NutGroup, NutParameters),
    "ISO10512": (translate("FastenerCmd", "Prevailing torque type hexagon nuts (with non-metallic insert) - fine pitch thread"), NutGroup, NutParameters),
    "ISO10513": (translate("FastenerCmd", "Prevailing torque type all-metal hexagon nuts with fine pitch thread"), NutGroup, NutParameters),
    "ISO10663": (translate("FastenerCmd", "Hexagon nuts with flange - fine pitch thread"), NutGroup, NutParameters),
    "ISO12125": (translate("FastenerCmd", "Prevailing torque type hexagon nuts with flange (with non-metallic insert) - fine pitch thread"), NutGroup, NutParameters),
    "ISO12126": (translate("FastenerCmd", "Prevailing torque type all-metal hexagon nuts with flange - fine pitch thread"), NutGroup, NutParameters),
    "ISO21670": (translate("FastenerCmd", "Hexagon weld nuts with flange"), NutGroup, NutParameters),
    "SAEJ483a1":(translate("FastenerCmd", "Low cap nuts"), NutGroup, NutParameters),
    "SAEJ483a2":(translate("FastenerCmd", "High cap nuts"), NutGroup, NutParameters),
    "DIN508":   (translate("FastenerCmd", "T-Slot nuts"), TSlotGroup, TSlotNutParameters),
    "GN505":    (translate("FastenerCmd", "GN 505 Serrated Quarter-Turn T-Slot nuts"), TSlotGroup, TSlotNutParameters),
    "GN505.4":  (translate("FastenerCmd", "GN 505.4 Serrated T-Slot Bolts"), TSlotGroup, TSlotBoltParameters),
    "GN506":    (translate("FastenerCmd", "GN 506 T-Slot nuts to swivel in"), TSlotGroup, TSlotNutParameters),
    "GN507":    (translate("FastenerCmd", "GN 507 T-Slot sliding nuts"), TSlotGroup, TSlotNutParameters),
    "ISO299":   (translate("FastenerCmd", "T-Slot nuts"), TSlotGroup, TSlotNutParameters),
    "ASMEB18.21.1.1":  (translate("FastenerCmd", "Helical spring lock washer, regular series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.2":  (translate("FastenerCmd", "Helical spring lock washer, heavy series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.3":  (translate("FastenerCmd", "Helical spring lock washer, extra duty series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.4":  (translate("FastenerCmd", "Helical spring lock washer, hi-collar series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.12A":(translate("FastenerCmd", "UN washers, narrow series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.12B":(translate("FastenerCmd", "UN washers, regular series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.12C":(translate("FastenerCmd", "UN washers, wide series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.6A": (translate("FastenerCmd", "Internal tooth lock washer, Type A"), WasherGroup, ToothLockWasherParameters),
    "ASMEB18.21.1.6B": (translate("FastenerCmd", "Internal tooth lock washer, Type B"), WasherGroup, ToothLockWasherParameters),
    "ASMEB18.21.1.7A": (translate("FastenerCmd", "Heavy internal tooth lock washer, Type A"), WasherGroup, ToothLockWasherParameters),
    "ASMEB18.21.1.7B": (translate("FastenerCmd", "Heavy internal tooth lock washer, Type B"), WasherGroup, ToothLockWasherParameters),
    "ASMEB18.21.1.8A": (translate("FastenerCmd", "External tooth lock washer, Type A"), WasherGroup, ToothLockWasherType8Parameters),
    "ASMEB18.21.1.8B": (translate("FastenerCmd", "External tooth lock washer, Type B"), WasherGroup, ToothLockWasherType8Parameters),
    "ASMEB18.21.1.9A": (translate("FastenerCmd", "Countersunk external tooth lock washer, Type A"), WasherGroup, ToothLockWasherType9Parameters),
    "ASMEB18.21.1.9B": (translate("FastenerCmd", "Countersunk external tooth lock washer, Type B"), WasherGroup, ToothLockWasherType9Parameters),
    "DIN6319C": (translate("FastenerCmd", "Spherical washer"), WasherGroup, WasherParameters),
    "DIN6319D": (translate("FastenerCmd", "Conical seat"), WasherGroup, WasherParameters),
    "DIN6319G": (translate("FastenerCmd", "Conical seat"), WasherGroup, WasherParameters),
    "DIN6340":  (translate("FastenerCmd", "Washers for clamping devices"), WasherGroup, WasherParameters),
    "DIN6796":  (translate("FastenerCmd", "Belleville conical spring washer"), WasherGroup, BellevilleWasherParameters),
    "ISO7089":  (translate("FastenerCmd", "Plain washers - Normal series"), WasherGroup, WasherParameters),
    "ISO7090":  (translate("FastenerCmd", "Plain Washers, chamfered - Normal series"), WasherGroup, WasherParameters),
    "ISO7092":  (translate("FastenerCmd", "Plain washers - Small series"), WasherGroup, WasherParameters),
    "ISO7093-1":(translate("FastenerCmd", "Plain washers - Large series"), WasherGroup, WasherParameters),
    "ISO7094":  (translate("FastenerCmd", "Plain washers - Extra large series"), WasherGroup, WasherParameters),
    "ISO8738":  (translate("FastenerCmd", "Plain washers for clevis pins"), WasherGroup, WasherParameters),
    "NFE27-619":(translate("FastenerCmd", "NFE27-619 Countersunk washer"), WasherGroup, WasherParameters),
    "ScrewTapInch":   (translate("FastenerCmd", "Inch threaded tap for creating internal threads"), ThreadedRodGroup, RodParameters),
    "ScrewDieInch":   (translate("FastenerCmd", "Tool object to cut external non-metric threads"), ThreadedRodGroup, RodParameters),
    "ThreadedRodInch":(translate("FastenerCmd", "UNC threaded rod"), ThreadedRodGroup, RodParameters),
    "ThreadedRod":    (translate("FastenerCmd", "Metric threaded rod"), ThreadedRodGroup, RodParameters),
    "ScrewTap":       (translate("FastenerCmd", "Metric threaded tap for creating internal threads"), ThreadedRodGroup, RodParameters),
    "ScrewDie":       (translate("FastenerCmd", "Tool object to cut external metric threads"), ThreadedRodGroup, RodParameters),
    "ScrewTapBSPP":   (translate("FastenerCmd", "BSP threaded tap for creating internal threads"), ThreadedRodGroup, RodParameters),
    "ScrewDieBSPP":   (translate("FastenerCmd", "Tool object to cut external BSP threads"), ThreadedRodGroup, RodParameters),
    "IUTHeatInsert":  (translate("FastenerCmd", "IUT[A/B/C] Heat Staked Metric Insert"), InsertGroup, HeatInsertParameters),
    "PEMPressNut":    (translate("FastenerCmd", "PEM Self Clinching nut"), InsertGroup, PEMPressNutParameters),
    "PEMStandoff":    (translate("FastenerCmd", "PEM Self Clinching standoff"), InsertGroup, PEMStandoffParameters),
    "PEMStud":        (translate("FastenerCmd", "PEM Self Clinching stud"), InsertGroup, ScrewParameters),
    "PCBSpacer":      (translate("FastenerCmd", "Wurth WA-SSTII PCB spacer"), InsertGroup, PCBSpacerParameters),
    "PCBStandoff":    (translate("FastenerCmd", "Wurth WA-SSTII  PCB standoff"), InsertGroup, PCBStandoffParameters),
    "4PWTI":          (translate("FastenerCmd", "4 Prong Wood Thread Insert (DIN 1624 Tee nuts)"), InsertGroup, WoodInsertParameters),
    "DIN471":  (translate("FastenerCmd", "Metric external retaining rings"), RetainingRingGroup, RetainingRingParameters),
    "DIN472":  (translate("FastenerCmd", "Metric internal retaining rings"), RetainingRingGroup, RetainingRingParameters),
    "DIN6799": (translate("FastenerCmd", "Metric E-clip retaining rings"), RetainingRingGroup, RetainingRingParameters),
    "DIN1143": (translate("FastenerCmd", "Round plain head nails for use in automatic nailing machines"), NailGroup, NailParameters),
    "DIN1144-A":(translate("FastenerCmd", "Nails for the installation of wood wool composite panels, 20mm round head"), NailGroup, NailParameters),
    "DIN1151-A":(translate("FastenerCmd", "Round plain head wire nails"), NailGroup, NailParameters),
    "DIN1151-B":(translate("FastenerCmd", "Round countersunk head wire nails"), NailGroup, NailParameters),
    "DIN1152": (translate("FastenerCmd", "Round lost head wire nails"), NailGroup, NailParameters),
    "DIN1160-A":(translate("FastenerCmd", "Clout or slate nails"), NailGroup, NailParameters),
    "DIN1160-B":(translate("FastenerCmd", "Clout or slate wide head nails"), NailGroup, NailParameters),
    "ISO1234":  (translate("FastenerCmd", "Split pins"), PinGroup, PinParameters),
    "ISO2338":  (translate("FastenerCmd", "Parallel pins"), PinGroup, PinParameters),
    "ISO2339":  (translate("FastenerCmd", "Taper pins"), PinGroup, PinParameters),
    "ISO2340A": (translate("FastenerCmd", "Clevis pins without head"), PinGroup, PinParameters),
    "ISO2340B": (translate("FastenerCmd", "Clevis pins without head (with split pin holes)"), PinGroup, PinParameters),
    "ISO2341A": (translate("FastenerCmd", "Clevis pins with head"), PinGroup, PinParameters),
    "ISO2341B": (translate("FastenerCmd", "Clevis pins with head (with split pin hole)"), PinGroup, PinParameters),
    "ISO8733":  (translate("FastenerCmd", "Parallel pins with internal thread, unhardened"), PinGroup, PinParameters),
    "ISO8734":  (translate("FastenerCmd", "Dowel pins"), PinGroup, PinParameters),
    "ISO8735":  (translate("FastenerCmd", "Parallel pins with internal thread, hardened"), PinGroup, PinParameters),
    "ISO8736":  (translate("FastenerCmd", "Taper pins with internal thread, unhardened"), PinGroup, PinParameters),
    "ISO8737":  (translate("FastenerCmd", "Taper pins with external thread, unhardened"), PinGroup, PinParameters),
    "ISO8739":  (translate("FastenerCmd", "Full-length grooved pins with pilot"), PinGroup, PinParameters),
    "ISO8740":  (translate("FastenerCmd", "Full-length grooved pins with chamfer"), PinGroup, PinParameters),
    "ISO8741":  (translate("FastenerCmd", "Half-length reverse taper grooved pins"), PinGroup, PinParameters),
    "ISO8742":  (translate("FastenerCmd", "Third-length center grooved pins"), PinGroup, PinParameters),
    "ISO8743":  (translate("FastenerCmd", "Half-length center grooved pins"), PinGroup, PinParameters),
    "ISO8744":  (translate("FastenerCmd", "Full-length taper grooved pins"), PinGroup, PinParameters),
    "ISO8745":  (translate("FastenerCmd", "Half-length taper grooved pins"), PinGroup, PinParameters),
    "ISO8746":  (translate("FastenerCmd", "Grooved pins with round head"), PinGroup, PinParameters),
    "ISO8747":  (translate("FastenerCmd", "Grooved pins with countersunk head"), PinGroup, PinParameters),
    "ISO8748":  (translate("FastenerCmd", "Coiled spring pins, heavy duty"), PinGroup, PinParameters),
    "ISO8750":  (translate("FastenerCmd", "Coiled spring pins, standard duty"), PinGroup, PinParameters),
    "ISO8751":  (translate("FastenerCmd", "Coiled spring pins, light duty"), PinGroup, PinParameters),
    "ISO8752":  (translate("FastenerCmd", "Slotted spring pins, heavy duty"), PinGroup, PinParameters),
    "ISO13337": (translate("FastenerCmd", "Slotted spring pins, light duty"), PinGroup, PinParameters),
}

FatenersStandards = {"ASME", "DIN", "ISO", "SAE", "EN", "GOST", "BSPP"}
FastenersStandardMap = {
    "ScrewTapInch": "ASME", "ScrewDieInch": "ASME", "ThreadedRodInch": "ASME",
    "ThreadedRod": "DIN", "ScrewTap": "ISO", "ScrewDie": "ISO",
    "ScrewTapBSPP": "BSPP", "ScrewDieBSPP": "BSPP",
}
# fmt: on


def FSGetStandardFromType(type):
    if type in FastenersStandardMap:
        return FastenersStandardMap[type]
    for std in FatenersStandards:
        if type.startswith(std):
            return std
    return "other"

def FSGetTypePretty(type):
    if type in FastenersStandardMap:
        return FastenersStandardMap[type] + " " + type
    for std in FatenersStandards:
        if type.startswith(std):
            return std + " " + type[len(std):]
    return "other"

def FSGetParams(type):
    if type not in FSScrewCommandTable:
        return {}
    return FSScrewCommandTable[type][CMD_PARAMETER_GRP]

def FSGetDescription(type):
    if type not in FSScrewCommandTable:
        return ""
    return FSGetTypePretty(type) + " " + FSScrewCommandTable[type][CMD_HELP]

def FSUpdateFormatString(fmtstr, type):
    if type not in FSScrewCommandTable:
        return fmtstr
    params = FSScrewCommandTable[type][CMD_PARAMETER_GRP]
    sizestr = ""
    for par in {"Diameter", "Length"}:
        if par in params:
            sizestr += " x " + par
    return fmtstr.replace("{dimension}", "{" + sizestr[3:] + "}")


# ─────────────────────────────────────────────────────────────────────────────
# Type classification helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_asme_std(type_str):
    """True for ALL ASME standard types.
    Covers 'ASME...' names (bolts/nuts) AND inch rod/tap/die types
    (ThreadedRodInch, ScrewTapInch, ScrewDieInch) which do not start with 'ASME'
    but belong to the ASME standard per FastenersStandardMap.
    Also treats SAEJ fasteners that use UN internal thread selection
    (e.g. SAEJ483a cup nuts) as ASME-threaded for property handling.
    """
    s = str(type_str)
    return s.startswith("ASME") or s.startswith("SAEJ") or FastenersStandardMap.get(s) == "ASME"


def _is_asme(fp):
    try:
        return _is_asme_std(fp.Type)
    except Exception:
        return False

def _is_asme_external(fp):
    """True only for ASME types with external thread (TThread), not nuts."""
    try:
        params = FSGetParams(fp.Type)
        return _is_asme_std(fp.Type) and "TThread" in params
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Property-panel visibility
# ─────────────────────────────────────────────────────────────────────────────

_VIS_BUSY = False


def _set_thread_props_visibility(fp, thread_on):
    global _VIS_BUSY
    if _VIS_BUSY:
        return
    _VIS_BUSY = True
    try:
        _set_thread_props_visibility_inner(fp, thread_on)
    finally:
        _VIS_BUSY = False


def _set_thread_props_visibility_inner(fp, thread_on):
    params = FSGetParams(fp.Type)
    is_asme_type = _is_asme_std(fp.Type)
    has_ext      = "TThread"    in params
    has_nut      = "TNutThread" in params
    is_metric_nut = has_nut and not is_asme_type

    if is_asme_type and has_ext:
        # ASME bolt — show ASME bolt props, hide all metric + nut props
        _vis_asme_external(fp, thread_on)
        for _p in ("Thread_Pitch", "Thread_Class_ISO",
                   "Thread_Pitch_Nut", "Thread_Class_Nut", "Thread_Root"):
            if hasattr(fp, _p):
                fp.setEditorMode(_p, 2)

    elif is_asme_type and has_nut:
        # ASME nut — show ASME nut props, hide all bolt and metric nut props
        for _p in ("Thread_Type", "Thread_TPI", "Thread_TPI_Custom",
                   "Thread_Class", "Thread_Length", "ThreadPitch",
                   "Thread_Pitch", "Thread_Class_ISO",
                   "Thread_Pitch_Nut", "Thread_Class_Nut", "Thread_Root"):
            if hasattr(fp, _p):
                fp.setEditorMode(_p, 2)
        # Show ASME internal nut props
        if _TAI is not None:
            _TAI.set_asme_nut_visibility(fp, thread_on)

    elif is_metric_nut:
        # Metric nut — show ONLY nut props, hide all bolt props
        for _p in ("Thread_Pitch", "Thread_Class_ISO", "ThreadPitch",
                   "Thread_Length", "Thread_Type", "Thread_TPI",
                   "Thread_TPI_Custom", "Thread_Class", "Thread_Root"):
            if hasattr(fp, _p):
                fp.setEditorMode(_p, 2)
        # Show nut properties (no Thread_Root for nut)
        if _TMI is not None:
            _TMI.set_nut_thread_visibility(fp, thread_on)

    else:
        # Metric bolt — show bolt props, hide nut props
        _TM.set_metric_thread_visibility(fp, thread_on)
        for _p in ("Thread_Pitch_Nut", "Thread_Class_Nut"):
            if hasattr(fp, _p):
                fp.setEditorMode(_p, 2)


def _update_metric_mean_dia(fp):
    if not hasattr(fp, "MetricMeanDia"):
        return
    try:
        _dia = str(getattr(fp, "Diameter",   "") or "")
        _p   = str(getattr(fp, "Thread_Pitch", "") or "")
        _cls = str(getattr(fp, "Thread_Class_ISO", "") or "")
        if _p and _cls:
            _val = _TM.mean_dia_from_table(_dia, _p, _cls)
            if _val and _val > 0:
                fp.MetricMeanDia = round(_val, 5)
    except Exception:
        pass


def _vis_asme_external(fp, thread_on):
    if hasattr(fp, "ThreadPitch"):
        fp.setEditorMode("ThreadPitch", 2)
    # PitchCustom is metric-only — hide it for all ASME types (TPI is used instead)
    if hasattr(fp, "PitchCustom"):
        fp.setEditorMode("PitchCustom", 2)
    if hasattr(fp, "Thread_Length"):
        fp.setEditorMode("Thread_Length", 0 if thread_on else 2)
    if hasattr(fp, "Thread_Type"):
        fp.setEditorMode("Thread_Type", 0 if thread_on else 2)
    if hasattr(fp, "Thread_TPI"):
        fp.setEditorMode("Thread_TPI", 0 if thread_on else 2)
    _tpi_sel   = str(getattr(fp, "Thread_TPI", "") or "")
    _is_custom = thread_on and (_tpi_sel == "Custom")
    if hasattr(fp, "Thread_TPI_Custom"):
        fp.setEditorMode("Thread_TPI_Custom", 0 if _is_custom else 2)
    _tpi_ready = thread_on and bool(_tpi_sel)
    if hasattr(fp, "Thread_Class"):
        fp.setEditorMode("Thread_Class", 0 if _tpi_ready else 2)



# ─────────────────────────────────────────────────────────────────────────────
# FSScrewObject
# ─────────────────────────────────────────────────────────────────────────────

class FSScrewObject(FSBaseObject):
    def __init__(self, obj, type, attachTo):
        super().__init__(obj, attachTo)
        self.VerifyMissingAttrs(obj, type)
        obj.Proxy = self

    def inswap(self, inpstr):
        return inpstr.replace('″', 'in') if '″' in inpstr else inpstr

    def InitBackupAttribs(self):
        for attr in FastenerAttribs:
            if not hasattr(self, 'attr'):
                setattr(self, attr, None)
        self.familyType           = ""
        self.calc_thread_length   = 0.0
        self.calc_diam            = None
        self.calc_pitch           = None
        self.calc_tpi             = None
        self.calc_len             = None
        self.dimTable             = None

    def BackupObject(self, obj):
        for attr in FastenerAttribs:
            if hasattr(obj, attr):
                val = getattr(obj, attr)
                if val.__class__.__name__ in ("str","bool","int","float"):
                    setattr(self, attr, val)
                else:
                    setattr(self, attr, str(val))

    def GetKey(self):
        key = ""
        for attr in FastenerAttribs:
            val = getattr(self, attr)
            if val is not None:
                key += attr + ":" + str(val) + "|"
        return key.rstrip("|")

    def onChanged(self, fp, prop):
        if prop == "Diameter" and not _is_asme_external(fp) \
                and not _is_asme_std(getattr(fp, "Type", "")) \
                and hasattr(fp, "Thread_Pitch"):
            _new_p = _TM.valid_pitches_for_dia(str(getattr(fp, "Diameter", "") or ""))
            if _new_p:
                try:
                    _cur = str(fp.Thread_Pitch)
                    fp.Thread_Pitch = _new_p
                    fp.Thread_Pitch = _cur if _cur in _new_p else _new_p[0]
                except Exception:
                    pass
                _p0 = str(getattr(fp, "Thread_Pitch", "") or "")
                _dia = str(getattr(fp, "Diameter", "") or "")
                _new_cls = _TM.valid_classes_for_dia_pitch(_dia, _p0)
                if _new_cls and hasattr(fp, "Thread_Class_ISO"):
                    try:
                        fp.Thread_Class_ISO = _new_cls
                        fp.Thread_Class_ISO = _new_cls[0]
                    except Exception:
                        pass
            _set_thread_props_visibility(fp, hasattr(fp, "Thread") and bool(fp.Thread))
            FastenerBase.FSCache.clear()
            return

        if prop == "Thread_Pitch" and hasattr(fp, "Thread_Class_ISO"):
            _dia_m  = str(getattr(fp, "Diameter", "") or "")
            _p_m    = str(getattr(fp, "Thread_Pitch", "") or "")
            _new_cls = _TM.valid_classes_for_dia_pitch(_dia_m, _p_m)
            if _new_cls:
                try:
                    _cur = str(fp.Thread_Class_ISO)
                    fp.Thread_Class_ISO = _new_cls
                    fp.Thread_Class_ISO = _cur if _cur in _new_cls else _new_cls[0]
                except Exception:
                    pass
            _set_thread_props_visibility(fp, hasattr(fp, "Thread") and bool(fp.Thread))
            FastenerBase.FSCache.clear()
            return

        if prop == "Thread_Class_ISO":
            _set_thread_props_visibility(fp, hasattr(fp, "Thread") and bool(fp.Thread))
            FastenerBase.FSCache.clear()
            return

        # ── Metric nut pitch/class cascade ──────────────────────────────────
        if prop == "Thread_Pitch_Nut" and hasattr(fp, "Thread_Pitch_Nut") \
                and _TMI is not None:
            _dia_n = str(getattr(fp, "Diameter", "") or "")
            _p_n   = str(getattr(fp, "Thread_Pitch_Nut", "") or "")
            _is_custom_n = (_p_n == "Custom")
            if hasattr(fp, "Thread_Pitch_Nut_Custom"):
                fp.setEditorMode("Thread_Pitch_Nut_Custom", 0 if _is_custom_n else 2)
                if not _is_custom_n and _p_n:
                    try:
                        fp.Thread_Pitch_Nut_Custom = float(_p_n)
                    except Exception:
                        pass
            if _p_n and hasattr(fp, "Thread_Class_Nut"):
                _p_cls = _p_n
                if _is_custom_n:
                    try:
                        _p_custom = float(getattr(fp, "Thread_Pitch_Nut_Custom", 0) or 0)
                        if _p_custom > 0:
                            _p_cls = str(_p_custom)
                    except Exception:
                        pass
                _nc = _TMI.valid_classes_for_dia_pitch(_dia_n, _p_cls) or ["6H"]
                try:
                    _cur_nc = str(fp.Thread_Class_Nut)   # read BEFORE list assign
                    fp.Thread_Class_Nut = _nc
                    _rest = _cur_nc if _cur_nc in _nc else ("6H" if "6H" in _nc else _nc[0])
                    if str(fp.Thread_Class_Nut) != _rest:
                        fp.Thread_Class_Nut = _rest
                except Exception:
                    pass
            _set_thread_props_visibility(fp, hasattr(fp, "Thread") and bool(fp.Thread))
            FastenerBase.FSCache.clear()
            return

        if prop == "Thread_Pitch_Nut_Custom" and hasattr(fp, "Thread_Pitch_Nut_Custom"):
            _set_thread_props_visibility(fp, hasattr(fp, "Thread") and bool(fp.Thread))
            FastenerBase.FSCache.clear()
            return

        if prop in ("Thread_Class_Nut", "Thread_Root", "Thread_Pitch_Nut_Custom") and hasattr(fp, prop):
            FastenerBase.FSCache.clear()
            return

        # SecurityPin / SecurityPinDiameter changes must regenerate the shape
        if prop in ("SecurityPin", "SecurityPinDiameter") and hasattr(fp, prop):
            # When SecurityPin is toggled, show/hide the diameter field
            if prop == "SecurityPin" and hasattr(fp, "SecurityPinDiameter"):
                fp.setEditorMode("SecurityPinDiameter", 0 if fp.SecurityPin else 2)
            FastenerBase.FSCache.clear()
            return

        # Tooth lock washer user parameters — any change regenerates the shape
        if prop in ("ToothCount", "ToothTwistAngle", "ToothWidth", "ToothLength", "ToothRecessWidth") and hasattr(fp, prop):
            FastenerBase.FSCache.clear()
            return

        # ── ASME nut type/TPI/class cascade ─────────────────────────────────
        if prop == "Thread_Type_Nut" and hasattr(fp, "Thread_Type_Nut")                 and _TAI is not None                 and _is_asme_std(str(getattr(fp, "Type", "") or "")):
            _dia_an = str(getattr(fp, "Diameter", "") or "")
            _type_an = str(getattr(fp, "Thread_Type_Nut", "") or "")
            if _type_an and hasattr(fp, "Thread_TPI_Nut"):
                _ntpis = _TAI.tpi_enum_options_for_nut(_dia_an, _type_an) or ["8", "Custom"]
                try:
                    _cur_tpi = str(fp.Thread_TPI_Nut)
                    fp.Thread_TPI_Nut = _ntpis
                    _rest_tpi = _cur_tpi if _cur_tpi in _ntpis else next((x for x in _ntpis if x != "Custom"), _ntpis[0])
                    if str(fp.Thread_TPI_Nut) != _rest_tpi:
                        fp.Thread_TPI_Nut = _rest_tpi
                except Exception:
                    pass
            FastenerBase.FSCache.clear()
            return

        if prop == "Thread_TPI_Nut" and hasattr(fp, "Thread_TPI_Nut")                 and _TAI is not None                 and _is_asme_std(str(getattr(fp, "Type", "") or "")):
            _dia_an  = str(getattr(fp, "Diameter", "") or "")
            _type_an = str(getattr(fp, "Thread_Type_Nut", "UNC") or "UNC")
            _tpi_an  = str(getattr(fp, "Thread_TPI_Nut", "") or "")
            # show/hide custom spinner
            _is_cust_nut = (_tpi_an == "Custom")
            if hasattr(fp, "Thread_TPI_Nut_Custom"):
                fp.setEditorMode("Thread_TPI_Nut_Custom", 0 if _is_cust_nut else 2)
                if not _is_cust_nut and _tpi_an:
                    try:
                        fp.Thread_TPI_Nut_Custom = float(_tpi_an)
                    except (ValueError, TypeError):
                        pass
            if _tpi_an and _tpi_an != "Custom" and hasattr(fp, "Thread_Class_Nut_ASME"):
                _ncls = _TAI.valid_classes_for_dia_tpi_type(_dia_an, _tpi_an, _type_an) or ["2B"]
                try:
                    _cur_cls = str(fp.Thread_Class_Nut_ASME)
                    fp.Thread_Class_Nut_ASME = _ncls
                    _rest_cls = _cur_cls if _cur_cls in _ncls else                                 ("2B" if "2B" in _ncls else _ncls[0])
                    if str(fp.Thread_Class_Nut_ASME) != _rest_cls:
                        fp.Thread_Class_Nut_ASME = _rest_cls
                except Exception:
                    pass
            FastenerBase.FSCache.clear()
            return

        if prop == "Thread_Class_Nut_ASME" and hasattr(fp, prop):
            FastenerBase.FSCache.clear()
            return

        if prop == "Diameter" and _is_asme_external(fp):
            _d_nom = _TA.bolt_nominal(getattr(fp, "Diameter", "") or "")
            if hasattr(fp, "Thread_Type"):
                _new_types = _TA.valid_thread2types_for_dia(_d_nom)
                try:
                    _cur = str(fp.Thread_Type)
                    fp.Thread_Type = _new_types
                    fp.Thread_Type = _cur if _cur in _new_types else _new_types[0]
                except Exception:
                    pass
            if hasattr(fp, "Thread_TPI"):
                _d_tt   = str(getattr(fp, "Thread_Type", "UNC") or "UNC")
                _d_opts = _TA.tpi_enum_options(_d_nom, _d_tt)
                try:
                    _cur = str(fp.Thread_TPI)
                    fp.Thread_TPI = _d_opts
                    fp.Thread_TPI = _cur if _cur in _d_opts else \
                        next((x for x in _d_opts if x != "Custom"), "Custom")
                except Exception:
                    pass
            FastenerBase.FSCache.clear()
            return

        # Diameter changed on any ASME non-external type (hexalobular screws, nuts, etc.)
        # The metric handler above skips ASME types, the external handler above skips
        # non-external types -- so this catches everything else (e.g. ASMEB18.6.3.1C/4C/9C/10C/12C).
        if prop == "Diameter" and _is_asme_std(getattr(fp, "Type", "")):
            FastenerBase.FSCache.clear()
            return

        if prop in ("Thread_Type", "Thread_TPI", "Thread_TPI_Custom", "Thread_Class") \
                and hasattr(fp, prop) and _is_asme_external(fp):
            thread_on = hasattr(fp, "Thread") and bool(fp.Thread)
            if prop == "Thread_Type":
                if hasattr(fp, "Thread_TPI"):
                    _nom  = _TA.bolt_nominal(getattr(fp, "Diameter", "") or "")
                    _tt   = str(getattr(fp, "Thread_Type", "UNC") or "UNC")
                    _opts = _TA.tpi_enum_options(_nom, _tt)
                    try:
                        _cur = str(fp.Thread_TPI)    # read BEFORE list assignment
                        fp.Thread_TPI = _opts
                        _restore = _cur if _cur in _opts else \
                            next((x for x in _opts if x != "Custom"), "Custom")
                        if str(fp.Thread_TPI) != _restore:
                            fp.Thread_TPI = _restore
                    except Exception:
                        pass
            elif prop == "Thread_TPI":
                _nom   = _TA.bolt_nominal(getattr(fp, "Diameter", "") or "")
                _tt    = str(getattr(fp, "Thread_Type", "UNC") or "UNC")
                _tpi_s = str(getattr(fp, "Thread_TPI", "") or "")

                if _tpi_s != "Custom" and _tpi_s and hasattr(fp, "Thread_TPI_Custom"):
                    try:
                        fp.Thread_TPI_Custom = float(_tpi_s)
                    except (ValueError, TypeError):
                        pass

                if hasattr(fp, "Thread_Class"):
                    if _tpi_s == "Custom":
                        _cust_val = float(getattr(fp, "Thread_TPI_Custom", 0) or 0)
                        if _cust_val > 0:
                            _near = _TA.nearest_tpi(_cust_val, _nom, _tt)
                            _cls_opts = _TA.valid_classes_for_series_tpi(_nom, _tt, _near)
                        else:
                            _cls_opts = _TA.all_classes_for_nominal(_nom)
                    else:
                        try:
                            _tpi_f = float(_tpi_s)
                            _cls_opts = _TA.valid_classes_for_series_tpi(
                                            _nom, _tt, _tpi_f)
                        except (ValueError, TypeError):
                            _cls_opts = ["2A", "3A"]
                    if _cls_opts:
                        try:
                            _cur = str(fp.Thread_Class)  # read BEFORE list assignment
                            fp.Thread_Class = _cls_opts
                            _restore = _cur if _cur in _cls_opts else _cls_opts[0]
                            if str(fp.Thread_Class) != _restore:
                                fp.Thread_Class = _restore
                        except Exception:
                            pass
            _set_thread_props_visibility(fp, thread_on)
            FastenerBase.FSCache.clear()
            return

        if prop in ("Thread", "Type"):
            params = FSGetParams(fp.Type)
            if "TThread" not in params and "TNutThread" not in params:
                return
            if not (hasattr(fp, "ThreadPitch") or hasattr(fp, "Thread_TPI")
                    or hasattr(fp, "Thread_Pitch")):
                return
            thread_on = hasattr(fp, "Thread") and bool(fp.Thread)
            _is_m = not _is_asme_std(getattr(fp, "Type", ""))
            if _is_m and "TPitch" in params and "TThread" in params:
                _dia_oc = str(getattr(fp, "Diameter", "") or "")
                if not hasattr(fp, "Thread_Pitch"):
                    _pitches_oc = _TM.valid_pitches_for_dia(_dia_oc)
                    fp.addProperty("App::PropertyEnumeration", "Thread_Pitch",
                        "Parameters",
                        translate("FastenerCmd", "Thread_Pitch (mm) — from ISO 965 table")
                    ).Thread_Pitch = _pitches_oc
                    try:
                        fp.Thread_Pitch = _pitches_oc[0]
                    except Exception:
                        pass
                if not hasattr(fp, "Thread_Class_ISO"):
                    _p0_oc = ""
                    try:
                        _p0_oc = str(fp.Thread_Pitch)
                    except Exception:
                        pass
                    _p0_oc = _p0_oc or "1.0"
                    _cls_oc = _TM.valid_classes_for_dia_pitch(_dia_oc, _p0_oc) or ["6g"]
                    fp.addProperty("App::PropertyEnumeration", "Thread_Class_ISO",
                        "Parameters",
                        translate("FastenerCmd", "Thread_Class — ISO 965 (6g=standard)")
                    ).Thread_Class_ISO = _cls_oc
                    try:
                        _def_oc = "6g" if "6g" in _cls_oc else _cls_oc[0]
                        fp.Thread_Class_ISO = _def_oc
                    except Exception:
                        pass
            _set_thread_props_visibility(fp, thread_on)

    def VerifyMissingAttrs(self, obj, type=None):
        self.updateProps(obj)
        self.InitBackupAttribs()

        if not hasattr(obj, "Type"):
            if type is None:
                if hasattr(self, "originalType"): type = self.originalType
                if hasattr(obj, "type"):
                    type = obj.type
                    FreeCAD.Console.PrintLog("using original type: " + type + "\n")
            obj.addProperty("App::PropertyEnumeration","Type","Parameters",
                translate("FastenerCmd","Fastener type")).Type = self.GetCompatibleTypes(type)
            obj.Type = type
        else:
            type = obj.Type

        if obj.Type == "ISO7380":  obj.Type = type = "ISO7380-1"
        if obj.Type == "DIN1624":
            type = "4PWTI"
            obj.Type = self.GetCompatibleTypes(type)
            obj.Type  = type
        self.familyType = screwMaker.GetTypeName(type)

        if not hasattr(obj, "Diameter"):
            diameters = screwMaker.GetAllDiams(type)
            diameters.insert(0, "Auto")
            if "DiameterCustom" in FSGetParams(type):
                diameters.append("Custom")
            obj.addProperty("App::PropertyEnumeration","Diameter","Parameters",
                translate("FastenerCmd","Standard diameter")).Diameter = diameters
            diameter = diameters[1]
            if hasattr(obj,"diameter"):
                obj.Diameter = diameter = obj.diameter
        else:
            diameter = obj.Diameter
        params = FSGetParams(type)

        if ("TThread" in params or "TNutThread" in params) and not hasattr(obj,"Thread"):
            obj.addProperty("App::PropertyBool","Thread","Parameters",
                translate("FastenerCmd","Generate real thread")).Thread = False
        if "LeftHanded" in params and not hasattr(obj,"LeftHanded"):
            obj.addProperty("App::PropertyBool","LeftHanded","Parameters",
                translate("FastenerCmd","Left handed thread")).LeftHanded = False
        if "MatchOuter" in params and not hasattr(obj,"MatchOuter"):
            obj.addProperty("App::PropertyBool","MatchOuter","Parameters",
                translate("FastenerCmd","Match outer thread diameter")).MatchOuter = \
                    FSParam.GetBool("MatchOuterDiameter")
        # Hexalobular types that support a tamper-resistant (security) centre pin.
        # ISO types: ISO 10664 drive geometry (makeHexalobularRecess)
        # ASME types: ASME B18.6.3 drive geometry (makeHexalobularRecessASME)
        # Both groups use the same _make_security_pin_cylinder() helper in their
        # respective FsMake files, so the same SecurityPin property controls both.
        _SECURITY_PIN_TYPES = {
            # ── ISO hexalobular ───────────────────────────────────────────────
            "ISO14579",   # Hexalobular socket head cap screws
            "ISO14580",   # Hexalobular socket cheese head screws
            "ISO14581",   # Hexalobular socket countersunk flat head screws
            "ISO14582",   # Hexalobular socket countersunk high head screws
            "ISO14583",   # Hexalobular socket pan head screws
            "ISO14584",   # Hexalobular socket raised countersunk head screws
            # ── ASME B18.6.3 hexalobular ─────────────────────────────────────
            "ASMEB18.6.3.1C",  # Countersunk flat head
            "ASMEB18.6.3.4C",  # Oval countersunk head
            "ASMEB18.6.3.9C",  # Pan head
            "ASMEB18.6.3.10C", # Fillister (oval / raised) head
            "ASMEB18.6.3.12C", # Truss head
        }
        if type in _SECURITY_PIN_TYPES and not hasattr(obj, "SecurityPin"):
            obj.addProperty("App::PropertyBool","SecurityPin","Parameters",
                translate("FastenerCmd","Add security (tamper-resistant) pin")).SecurityPin = False
        if type in _SECURITY_PIN_TYPES and not hasattr(obj, "SecurityPinDiameter"):
            obj.addProperty("App::PropertyFloat","SecurityPinDiameter","Parameters",
                translate("FastenerCmd",
                    "Security pin diameter [mm]. "
                    "Enter 0 to use the standard diameter "
                    "(75 % of inscribed bore = (B/2-Re)*1.5)."
                )).SecurityPinDiameter = 0.0
        # Show/hide SecurityPinDiameter depending on whether SecurityPin is enabled
        if hasattr(obj, "SecurityPin") and hasattr(obj, "SecurityPinDiameter"):
            obj.setEditorMode("SecurityPinDiameter", 0 if obj.SecurityPin else 2)

        # ── Tooth lock washer user parameters ────────────────────────────────────
        if "ToothCount" in params and not hasattr(obj, "ToothCount"):
            default_n = 9 if type.endswith("B") else 10
            obj.addProperty("App::PropertyInteger", "ToothCount", "ToothLockWasher",
                translate("FastenerCmd",
                    "Number of teeth (default: 9 for Type B, 10 for Type A)")
            ).ToothCount = default_n
        if "ToothTwistAngle" in params and not hasattr(obj, "ToothTwistAngle"):
            obj.addProperty("App::PropertyFloat", "ToothTwistAngle", "ToothLockWasher",
                translate("FastenerCmd",
                    "Tooth tip twist angle in degrees. "
                    "Twist decreases from this value at the bore tip to 0 at the ring edge.")
            ).ToothTwistAngle = 15.0
        if "ToothRecessWidth" in params and not hasattr(obj, "ToothRecessWidth"):
            try:
                import math as _math
                _dia_key = str(obj.Diameter)
                _dimrow  = FastenerBase.FsData[type + "def"][_dia_key]
                if len(_dimrow) >= 6:
                    _d1 = (_dimrow[0] + _dimrow[1]) / 2.0
                    _d2 = (_dimrow[2] + _dimrow[3]) / 2.0
                else:
                    _d1, _d2 = float(_dimrow[0]), float(_dimrow[1])
                _r_tip  = _d1 / 2.0
                _r_out  = _d2 / 2.0
                _rf     = 0.45 if type.endswith("B") else 0.50
                _r_root = _r_tip + _rf * (_r_out - _r_tip)
                _n_def  = 9 if type.endswith("B") else 10
                _pitch  = 2.0 * _math.pi / _n_def
                _gap_frac   = 0.35 if type.endswith("B") else 0.30
                _default_rw = max(_r_root * _pitch * _gap_frac, 0.05)
            except Exception:
                _default_rw = 1.0
            obj.addProperty("App::PropertyLength", "ToothRecessWidth", "ToothLockWasher",
                translate("FastenerCmd",
                    "Tooth recess width in mm — the gap between adjacent teeth. "
                    "Increasing this value narrows the teeth; decreasing it widens them.")
            ).ToothRecessWidth = _default_rw
        if "ToothWidth" in params and not hasattr(obj, "ToothWidth"):
            # For internal washers (6, 7): ToothWidth = rectangular gap width between teeth.
            # For external washers (8, 9): ToothWidth = tooth width.
            _is_internal = ("ASMEB18.21.1.6" in type or "ASMEB18.21.1.7" in type)
            try:
                import math as _math
                _dia_key = str(obj.Diameter)
                _dimrow  = FastenerBase.FsData[type + "def"][_dia_key]
                if len(_dimrow) == 6:
                    _d1 = (_dimrow[0] + _dimrow[1]) / 2.0
                    _d2 = (_dimrow[2] + _dimrow[3]) / 2.0
                else:
                    _d1, _d2 = float(_dimrow[0]), float(_dimrow[1])
                _r_tip   = _d1 / 2.0
                _r_out   = _d2 / 2.0
                _rf      = 0.45 if type.endswith("B") else 0.50
                _r_root  = _r_tip + _rf * (_r_out - _r_tip)
                _n_def   = 9 if type.endswith("B") else 10
                _pitch   = 2.0 * _math.pi / _n_def
                if _is_internal:
                    # default gap = 30 % (A) / 35 % (B) of pitch arc at r_root
                    _gap_frac   = 0.35 if type.endswith("B") else 0.30
                    _default_tw = max(_r_root * _pitch * _gap_frac, 0.05)
                else:
                    _wf         = 0.45 if type.endswith("B") else 0.50
                    _default_tw = max(_r_root * _pitch * _wf, 0.05)
            except Exception:
                _default_tw = 1.0
            _tw_tooltip = (
                "Tooth gap width in mm — the rectangular gap between adjacent teeth. "
                "Increasing this value narrows the teeth; decreasing it widens them."
                if _is_internal else
                "Tooth width in mm (or enter with unit, e.g. '0.05 in'). "
                "FreeCAD shows the value in your active unit system — "
                "mm and inches are correlated automatically."
            )
            obj.addProperty("App::PropertyLength", "ToothWidth", "ToothLockWasher",
                translate("FastenerCmd", _tw_tooltip)
            ).ToothWidth = _default_tw
        if "ToothLength" in params and not hasattr(obj, "ToothLength"):
            _is_internal_tl = ("ASMEB18.21.1.6" in type or "ASMEB18.21.1.7" in type)
            _is_type9_tl    = "ASMEB18.21.1.9" in type
            try:
                import math as _math
                _dia_key  = str(obj.Diameter)
                _dimrow   = FastenerBase.FsData[type + "def"][_dia_key]
                if len(_dimrow) >= 6:
                    _d1 = (_dimrow[0] + _dimrow[1]) / 2.0
                    _d2 = (_dimrow[2] + _dimrow[3]) / 2.0
                else:
                    _d1, _d2 = float(_dimrow[0]), float(_dimrow[1])
                _r_inner = _d1 / 2.0
                _r_outer = _d2 / 2.0
                _total   = _r_outer - _r_inner
                if _is_internal_tl:
                    # tooth (inward from bore): 45 % (B) / 50 % (A) of total
                    _tf = 0.45 if type.endswith("B") else 0.50
                elif _is_type9_tl:
                    _tf = 0.50
                else:
                    # Type 8: 55 % (B) / 60 % (A) of total
                    _tf = 0.55 if type.endswith("B") else 0.60
                _default_tl = round(_total * _tf, 4)
            except Exception:
                _default_tl = 1.0
            obj.addProperty("App::PropertyLength", "ToothLength", "ToothLockWasher",
                translate("FastenerCmd",
                    "Radial tooth length in mm. "
                    "Total radial span = tooth length + ring length (fixed by diameter). "
                    "Increase to make teeth longer; ring shortens automatically.")
            ).ToothLength = _default_tl
        # ── end tooth lock washer params ─────────────────────────────────────────

        if "widthCode" in params and not hasattr(obj,"Width"):
            obj.addProperty("App::PropertyEnumeration","Width","Parameters",
                translate("FastenerCmd","Body width code")).Width = \
                    screwMaker.GetAllWidthcodes(type, diameter)

        addCustomLen = "LengthCustom" in params and not hasattr(obj,"LengthCustom")
        if "Length" in params or "LenByDiamAndWidth" in params:
            slens = screwMaker.GetAllLengths(type, diameter, addCustomLen,
                        obj.Width if "LenByDiamAndWidth" in params else None)
            if not hasattr(obj,"Length"):
                obj.addProperty("App::PropertyEnumeration","Length","Parameters",
                    translate("FastenerCmd","Screw length")).Length = slens
            elif addCustomLen:
                origLen = obj.Length
                obj.Length = slens
                if origLen in slens: obj.Length = origLen
            if addCustomLen:
                obj.addProperty("App::PropertyLength","LengthCustom","Parameters",
                    translate("FastenerCmd","Custom length")).LengthCustom = \
                        self.inswap(slens[0])

        if "lengthArbitrary" in params and not hasattr(obj,"Length"):
            obj.addProperty("App::PropertyLength","Length","Parameters",
                translate("FastenerCmd","Screw length")).Length = \
                    screwMaker.GetTableProperty(type, diameter, "Length", 20.0)
        if "ExternalDiam" in params and not hasattr(obj,"ExternalDiam"):
            obj.addProperty("App::PropertyLength","ExternalDiam","Parameters",
                translate("FastenerCmd","External Diameter")).ExternalDiam = \
                    screwMaker.GetTableProperty(type, diameter, "ExtDia", 8.0)
        if "DiameterCustom" in params and not hasattr(obj,"DiameterCustom"):
            obj.addProperty("App::PropertyLength","DiameterCustom","Parameters",
                translate("FastenerCmd","Screw major diameter custom")).DiameterCustom = 6
        if "WasherOuterDiaCustom" in params and not hasattr(obj,"WasherOuterDiaCustom"):
            obj.addProperty("App::PropertyLength","WasherOuterDiaCustom","Parameters",
                translate("FastenerCmd","Washer outer diameter (custom)")).WasherOuterDiaCustom = 12
        if "WasherThicknessCustom" in params and not hasattr(obj,"WasherThicknessCustom"):
            obj.addProperty("App::PropertyLength","WasherThicknessCustom","Parameters",
                translate("FastenerCmd","Washer thickness (custom)")).WasherThicknessCustom = 1.5
        if "WasherHeightCustom" in params and not hasattr(obj,"WasherHeightCustom"):
            obj.addProperty("App::PropertyLength","WasherHeightCustom","Parameters",
                translate("FastenerCmd","Belleville washer free height (custom)")).WasherHeightCustom = 2.0
        if "PitchCustom" in params and not hasattr(obj,"PitchCustom"):
            obj.addProperty("App::PropertyLength","PitchCustom","Parameters",
                translate("FastenerCmd","Screw pitch custom")).PitchCustom = 1.0
        if "ThicknessCode" in params and not hasattr(obj,"Tcode"):
            obj.addProperty("App::PropertyEnumeration","Tcode","Parameters",
                translate("FastenerCmd","Thickness code")).Tcode = \
                    screwMaker.GetAllTcodes(type, diameter)
        if "SlotWidth" in params and not hasattr(obj,"SlotWidth"):
            obj.addProperty("App::PropertyEnumeration","SlotWidth","Parameters",
                translate("FastenerCmd","Slot width")).SlotWidth = \
                    screwMaker.GetAllSlotWidths(type, diameter)
        if "KeySize" in params and not hasattr(obj,"KeySize"):
            obj.addProperty("App::PropertyEnumeration","KeySize","Parameters",
                translate("FastenerCmd","Key size")).KeySize = \
                    screwMaker.GetAllKeySizes(type, diameter)

        if "TPitch" in params and not hasattr(obj,"ThreadPitch"):
            obj.addProperty("App::PropertyLength","ThreadPitch","Parameters",
                translate("FastenerCmd","Thread_Pitch legacy (hidden)")
            ).ThreadPitch = 0.0
            obj.setEditorMode("ThreadPitch", 2)

        if "TLength" in params and not hasattr(obj,"Thread_Length"):
            obj.addProperty("App::PropertyLength","Thread_Length","Parameters",
                translate("FastenerCmd","Thread_Length (mm). 0 = standard")
            ).Thread_Length = 0.0
            obj.setEditorMode("Thread_Length", 2)

        _this_type_early = str(type) if type else str(getattr(obj, "Type", ""))
        _is_metric_ext = not _is_asme_std(_this_type_early) and "TThread" in params
        _is_asme_ext   = _is_asme_std(_this_type_early) and "TThread" in params
        if _is_metric_ext and not hasattr(obj, "Thread_Root"):
            obj.addProperty("App::PropertyEnumeration", "Thread_Root", "Parameters",
                translate("FastenerCmd",
                    "Thread_Root: Flat (ISO standard) or Round (ISO 68-1)")
            ).Thread_Root = ["Flat", "Round"]
            try:
                obj.Thread_Root = "Flat"
            except Exception:
                pass
            obj.setEditorMode("Thread_Root", 0)

        if "TPitch" in params and not _is_asme_std(_this_type_early):
            _dia_v = str(getattr(obj, "Diameter", diameter) or "")
            if _dia_v in ("Auto", "", "Custom"):
                try:
                    _dia_v = screwMaker.AutoDiameter(type, None, None, False)
                except Exception:
                    _dia_v = diameter or ""
            if not hasattr(obj, "Thread_Pitch"):
                _pitches = _TM.valid_pitches_for_dia(_dia_v)
                if not _pitches:
                    try:
                        _dia_v2 = screwMaker.GetAllDiams(type)
                        _dia_v = _dia_v2[0] if _dia_v2 else _dia_v
                        _pitches = _TM.valid_pitches_for_dia(_dia_v)
                    except Exception:
                        pass
                if _pitches:
                    obj.addProperty("App::PropertyEnumeration", "Thread_Pitch", "Parameters",
                        translate("FastenerCmd", "Thread_Pitch (mm) — from ISO 965 table")
                    ).Thread_Pitch = _pitches
                    try:
                        obj.Thread_Pitch = _pitches[0]
                    except Exception:
                        pass
                    obj.setEditorMode("Thread_Pitch", 2)
            if not hasattr(obj, "Thread_Class_ISO"):
                _p0 = ""
                try:
                    _p0 = str(obj.Thread_Pitch)
                except Exception:
                    pass
                _p0 = _p0 or "1.0"
                _cls = _TM.valid_classes_for_dia_pitch(_dia_v, _p0) or ["6g"]
                obj.addProperty("App::PropertyEnumeration", "Thread_Class_ISO", "Parameters",
                    translate("FastenerCmd", "Thread_Class — ISO 965 (6g=standard, 4h=tight)")
                ).Thread_Class_ISO = _cls
                try:
                    _def_cls = "6g" if "6g" in _cls else _cls[0]
                    obj.Thread_Class_ISO = _def_cls
                except Exception:
                    pass
                obj.setEditorMode("Thread_Class_ISO", 2)

        _this_type   = str(type) if type else str(getattr(obj, "Type", ""))
        _is_asme_t   = _is_asme_std(_this_type)
        _has_ext_t   = "TThread" in params
        _has_nut_t   = "TNutThread" in params

        _is_metric_nut = _has_nut_t and not _is_asme_t and _TMI is not None
        if _is_metric_nut:
            _dia_nut = str(getattr(obj, "Diameter", diameter) or "")
            if _dia_nut in ("Auto", "", "Custom"):
                try:
                    _dia_nut = screwMaker.AutoDiameter(type, None, None, False)
                except Exception:
                    _dia_nut = diameter or ""
            if not hasattr(obj, "Thread_Pitch_Nut"):
                _np = _TMI.valid_pitches_for_dia(_dia_nut)
                if _np:
                    _np_enum = list(_np) + ["Custom"]
                    obj.addProperty("App::PropertyEnumeration", "Thread_Pitch_Nut",
                        "Parameters",
                        translate("FastenerCmd",
                            "Thread_Pitch_Nut (mm) — from ISO 965 internal thread table")
                    ).Thread_Pitch_Nut = _np_enum
                    try:
                        obj.Thread_Pitch_Nut = _np[0]
                    except Exception:
                        pass
                    obj.setEditorMode("Thread_Pitch_Nut", 2)
            if not hasattr(obj, "Thread_Pitch_Nut_Custom"):
                _init_np_custom = 1.0
                try:
                    _init_np_custom = float(str(getattr(obj, "Thread_Pitch_Nut", "1.0") or "1.0"))
                except Exception:
                    pass
                obj.addProperty("App::PropertyFloat", "Thread_Pitch_Nut_Custom",
                    "Parameters",
                    translate("FastenerCmd", "Thread_Pitch_Nut Custom value (mm)")
                ).Thread_Pitch_Nut_Custom = _init_np_custom
                obj.setEditorMode("Thread_Pitch_Nut_Custom", 2)
            if not hasattr(obj, "Thread_Class_Nut"):
                _np0 = ""
                try:
                    _np0 = str(obj.Thread_Pitch_Nut)
                except Exception:
                    pass
                _np0 = _np0 or "1.0"
                _nc = _TMI.valid_classes_for_dia_pitch(_dia_nut, _np0) or ["6H"]
                obj.addProperty("App::PropertyEnumeration", "Thread_Class_Nut",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_Class_Nut — ISO 965 internal (6H=standard)")
                ).Thread_Class_Nut = _nc
                try:
                    _def_nc = "6H" if "6H" in _nc else _nc[0]
                    obj.Thread_Class_Nut = _def_nc
                except Exception:
                    pass
                obj.setEditorMode("Thread_Class_Nut", 2)

        # ── ASME nut: Thread_Type_Nut + Thread_TPI_Nut + Thread_Class_Nut_ASME ──
        _is_asme_nut = _has_nut_t and _is_asme_t and _TAI is not None
        if _is_asme_nut:
            _dia_asme_nut = str(getattr(obj, "Diameter", diameter) or "")
            if _dia_asme_nut in ("Auto", "", "Custom"):
                try:
                    _dia_asme_nut = screwMaker.AutoDiameter(type, None, None, False)
                except Exception:
                    _dia_asme_nut = diameter or ""
            # Thread_Type_Nut — series dropdown (UNC, UNF, UN, UNEF, UNS)
            if not hasattr(obj, "Thread_Type_Nut"):
                _atypes = _TAI.valid_types_for_dia(_dia_asme_nut) or ["UNC"]
                obj.addProperty("App::PropertyEnumeration", "Thread_Type_Nut",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_Type_Nut — ASME B1.1 series (UNC/UNF/UN/UNEF)")
                ).Thread_Type_Nut = _atypes
                try:
                    _def_at = "UNC" if "UNC" in _atypes else _atypes[0]
                    obj.Thread_Type_Nut = _def_at
                except Exception:
                    pass
                obj.setEditorMode("Thread_Type_Nut", 2)
            # Thread_TPI_Nut — TPI dropdown
            if not hasattr(obj, "Thread_TPI_Nut"):
                _at_now = ""
                try:
                    _at_now = str(obj.Thread_Type_Nut)
                except Exception:
                    pass
                _at_now = _at_now or "UNC"
                _atpis = _TAI.tpi_enum_options_for_nut(_dia_asme_nut, _at_now) or ["8", "Custom"]
                obj.addProperty("App::PropertyEnumeration", "Thread_TPI_Nut",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_TPI_Nut — ASME B1.1 threads per inch")
                ).Thread_TPI_Nut = _atpis
                try:
                    obj.Thread_TPI_Nut = next((x for x in _atpis if x != "Custom"), _atpis[0])
                except Exception:
                    pass
                obj.setEditorMode("Thread_TPI_Nut", 2)
            # Thread_TPI_Nut_Custom — float spinner shown only when TPI == "Custom"
            if not hasattr(obj, "Thread_TPI_Nut_Custom"):
                obj.addProperty("App::PropertyFloat", "Thread_TPI_Nut_Custom", "Parameters",
                    translate("FastenerCmd", "Thread_TPI_Nut Custom value (supports decimals, e.g. 4.5)")
                ).Thread_TPI_Nut_Custom = 0.0
                obj.setEditorMode("Thread_TPI_Nut_Custom", 2)
            # Thread_Class_Nut_ASME — class dropdown (1B/2B/3B)
            if not hasattr(obj, "Thread_Class_Nut_ASME"):
                _at_now2 = ""
                try:
                    _at_now2 = str(obj.Thread_Type_Nut)
                except Exception:
                    pass
                _at_now2 = _at_now2 or "UNC"
                _atpi_now = ""
                try:
                    _atpi_now = str(obj.Thread_TPI_Nut)
                except Exception:
                    pass
                _atpi_now = _atpi_now or "8"
                _ancls = _TAI.valid_classes_for_dia_tpi_type(
                    _dia_asme_nut, _atpi_now, _at_now2) or ["2B"]
                obj.addProperty("App::PropertyEnumeration", "Thread_Class_Nut_ASME",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_Class_Nut_ASME — ASME B1.1 (2B=standard)")
                ).Thread_Class_Nut_ASME = _ancls
                try:
                    _def_ancls = "2B" if "2B" in _ancls else _ancls[0]
                    obj.Thread_Class_Nut_ASME = _def_ancls
                except Exception:
                    pass
                obj.setEditorMode("Thread_Class_Nut_ASME", 2)

        if "TType" in params and _is_asme_t and _has_ext_t \
                and not hasattr(obj, "Thread_Type"):
            _nom_t    = _TA.bolt_nominal(getattr(obj, "Diameter", "") or "")
            _valid_tt = _TA.valid_thread2types_for_dia(_nom_t)
            obj.addProperty("App::PropertyEnumeration","Thread_Type","Parameters",
                translate("FastenerCmd", "Thread_Type: UNC/UNF/UNEF/UN/UNR")
            ).Thread_Type = _valid_tt
            obj.setEditorMode("Thread_Type", 2)

        if "TPitch" in params and _is_asme_t and _has_ext_t:
            if hasattr(obj, "Thread_TPI"):
                _ok = False
                try: _ok = "Enumeration" in obj.getTypeIdOfProperty("Thread_TPI")
                except Exception: pass
                if not _ok:
                    try: obj.removeProperty("Thread_TPI")
                    except Exception: pass
            if not hasattr(obj, "Thread_TPI"):
                _snom  = _TA.bolt_nominal(getattr(obj, "Diameter", "") or "")
                _stt   = str(getattr(obj, "Thread_Type", "UNC") or "UNC")
                _sopts = _TA.tpi_enum_options(_snom, _stt)
                obj.addProperty("App::PropertyEnumeration", "Thread_TPI", "Parameters",
                    translate("FastenerCmd", "Thread_TPI — from ASME B1.1 table or Custom")
                ).Thread_TPI = _sopts
                _first_std_tpi = next((x for x in _sopts if x != "Custom"), None)
                try:
                    if _first_std_tpi:
                        obj.Thread_TPI = _first_std_tpi
                except Exception: pass
                obj.setEditorMode("Thread_TPI", 2)
            if not hasattr(obj, "Thread_TPI_Custom"):
                _cur_tpi_str = ""
                try:
                    _cur_tpi_str = str(obj.Thread_TPI)
                except Exception:
                    pass
                _init_custom = 0.0
                if _cur_tpi_str and _cur_tpi_str != "Custom":
                    try:
                        _init_custom = float(_cur_tpi_str)
                    except (ValueError, TypeError):
                        pass
                obj.addProperty("App::PropertyFloat", "Thread_TPI_Custom", "Parameters",
                    translate("FastenerCmd", "Thread_TPI Custom value (supports decimals, e.g. 4.5)")
                ).Thread_TPI_Custom = _init_custom
                obj.setEditorMode("Thread_TPI_Custom", 2)
            if not hasattr(obj, "Thread_Class"):
                obj.addProperty("App::PropertyEnumeration", "Thread_Class", "Parameters",
                    translate("FastenerCmd", "Thread_Class: 2A=standard, 3A=tight")
                ).Thread_Class = ["2A", "3A"]
                obj.setEditorMode("Thread_Class", 2)

        _hthread = _has_ext_t or _has_nut_t
        _ton     = (_hthread and hasattr(obj, "Thread") and bool(obj.Thread))

        if _is_asme_t and _has_ext_t:
            if _ton:
                _vis_asme_external(obj, True)
            else:
                for _p in ("Thread_Type", "Thread_TPI", "Thread_TPI_Custom",
                           "Thread_Class", "Thread_Length", "ThreadPitch"):
                    if hasattr(obj, _p):
                        obj.setEditorMode(_p, 2)
        elif _is_asme_t and _has_nut_t:
            for _p in ("Thread_Type", "Thread_TPI", "Thread_TPI_Custom",
                       "Thread_Class", "Thread_Length", "ThreadPitch"):
                if hasattr(obj, _p):
                    obj.setEditorMode(_p, 2)
        else:
            _TM.set_metric_thread_visibility(obj, _ton)

        if "blindness" in params and not hasattr(obj,"Blind"):
            obj.addProperty("App::PropertyBool","Blind","Parameters",
                translate("FastenerCmd","Blind Standoff type")).Blind = False
        if "Thread_Length" in params and not hasattr(obj,"ScrewLength"):
            obj.addProperty("App::PropertyLength","ScrewLength","Parameters",
                translate("FastenerCmd","Threaded part length")).ScrewLength = \
                    screwMaker.GetThreadLength(type, diameter)

        for _hp in ("Invert", "LeftHanded", "MatchOuter", "Offset", "OffsetAngle"):
            if hasattr(obj, _hp):
                obj.setEditorMode(_hp, 2)

        self.migrateToUpperCase(obj)
        self.BackupObject(obj)

    def GetCompatibleTypes(self, ftype):
        pargrp = FSGetParams(ftype)
        return sorted(t for t in FSScrewCommandTable if FSGetParams(t) is pargrp)

    def onDocumentRestored(self, obj):
        self.VerifyMissingAttrs(obj)

    def CleanDecimals(self, val):
        val = str(val)
        if re.search(r"[.]\d*$", val):
            return val.rstrip('0').rstrip('.')
        return val

    def ActiveLength(self, obj):
        if not hasattr(obj,'Length'): return '0'
        if not isinstance(obj.Length, str):
            return self.CleanDecimals(float(obj.Length))
        if obj.Length == 'Custom':
            return self.CleanDecimals(float(obj.LengthCustom))
        return obj.Length

    def paramChanged(self, param, value):
        return getattr(self, param) != value

    def execute(self, fp):
        try:
            baseobj = fp.BaseObject[0]
            shape = baseobj.getSubObject(fp.BaseObject[1][0])
        except:
            baseobj = None
            shape = None

        params = FSGetParams(fp.Type)

        typechange = False
        if fp.Type != self.Type:
            typechange = True
            curdiam = fp.Diameter
            diameters = screwMaker.GetAllDiams(fp.Type)
            diameters.insert(0, "Auto")
            if "DiameterCustom" in params: diameters.append("Custom")
            if curdiam not in diameters: curdiam = "Auto"
            fp.Diameter = diameters
            fp.Diameter = curdiam

        if self.PitchCustom is not None and hasattr(fp,"PitchCustom") \
                and str(fp.PitchCustom) != self.PitchCustom:
            fp.Diameter = "Custom"

        diameterchange  = self.Diameter != fp.Diameter
        matchouterchange= hasattr(fp,"MatchOuter") and self.MatchOuter != fp.MatchOuter
        widthchange     = hasattr(fp,"Width") and self.Width != fp.Width

        if fp.Diameter == "Auto" or matchouterchange:
            mo = fp.MatchOuter if hasattr(fp,"MatchOuter") else False
            self.calc_diam = screwMaker.AutoDiameter(fp.Type, shape, baseobj, mo)
            fp.Diameter = self.calc_diam
            diameterchange = True
        elif fp.Diameter == "Custom" and hasattr(fp,"DiameterCustom"):
            self.calc_diam = str(fp.DiameterCustom.Value)
        else:
            self.calc_diam = fp.Diameter

        if hasattr(fp,"Length"):
            if "lengthArbitrary" in params:
                l = screwMaker.GetTableProperty(fp.Type, fp.Diameter, "Length",
                        fp.Length.Value) if diameterchange else fp.Length.Value
                try:
                    minL = Units.Quantity(
                        str(FSParam.GetFloat("MinimumLength",2.0)) + " mm")
                except ValueError:
                    minL = Units.Quantity("2.0 mm")
                if Units.Quantity(l).Value < minL.Value: l = minL.Value
                fp.Length = l
                self.calc_len = str(l)
            else:
                width = fp.Width if "LenByDiamAndWidth" in params else None
                if self.paramChanged("Length", fp.Length):
                    if fp.Length != "Custom" and hasattr(fp,"LengthCustom"):
                        fp.LengthCustom = FastenerBase.LenStr2Num(fp.Length)
                elif self.LengthCustom is not None \
                        and str(fp.LengthCustom) != self.LengthCustom:
                    fp.Length = "Custom"
                origLen      = self.ActiveLength(fp)
                origIsCustom = fp.Length == "Custom"
                self.calc_diam, l, auto_width = screwMaker.FindClosest(
                    fp.Type, self.calc_diam, origLen, width)
                if self.calc_diam != fp.Diameter:
                    diameterchange = True
                    fp.Diameter = self.calc_diam
                if width != auto_width:
                    widthchange = True
                    fp.Width  = screwMaker.GetAllWidthcodes(fp.Type, fp.Diameter)
                    fp.Width  = width = auto_width
                if origIsCustom: l = origLen
                if l != origLen or diameterchange or typechange or widthchange:
                    if diameterchange or typechange or widthchange:
                        fp.Length = screwMaker.GetAllLengths(
                            fp.Type, fp.Diameter, hasattr(fp,"LengthCustom"), width)
                        if hasattr(fp,"ScrewLength"):
                            fp.ScrewLength = screwMaker.GetThreadLength(
                                fp.Type, fp.Diameter)
                    # Guard: the saved Length string may not exist in the
                    # rebuilt enum (e.g. after a fastener type was renamed).
                    # Fall back to "Custom" so the object stays editable
                    # instead of raising a ValueError and blocking the document.
                    try:
                        fp.Length = "Custom" if origIsCustom else l
                    except ValueError:
                        FreeCAD.Console.PrintWarning(
                            f"[FastenersCmd] Length value '{l}' is not in the "
                            f"enum for {fp.Type}/{fp.Diameter} — "
                            f"resetting to Custom\n")
                        if hasattr(fp, "LengthCustom"):
                            fp.LengthCustom = FastenerBase.LenStr2Num(l)
                        fp.Length = "Custom"
                    if not origIsCustom and fp.Length != "Custom" and hasattr(fp,"LengthCustom"):
                        fp.LengthCustom = FastenerBase.LenStr2Num(l)
                self.calc_len = l
        else:
            self.calc_len = None

        if hasattr(fp,"ExternalDiam") and diameterchange:
            fp.ExternalDiam = screwMaker.GetTableProperty(
                fp.Type, fp.Diameter, "ExtDia", 8.0)
        if diameterchange and "ThicknessCode" in params:
            tc = screwMaker.GetAllTcodes(fp.Type, fp.Diameter)
            oc = fp.Tcode; fp.Tcode = tc
            if oc in tc: fp.Tcode = oc
        if (typechange or diameterchange) and "SlotWidth" in params:
            sw = screwMaker.GetAllSlotWidths(fp.Type, fp.Diameter)
            osw = fp.SlotWidth; fp.SlotWidth = sw
            if osw in sw: fp.SlotWidth = osw
        if diameterchange and "KeySize" in params:
            ks = screwMaker.GetAllKeySizes(fp.Type, fp.Diameter)
            oks = fp.KeySize; fp.KeySize = ks
            if oks in ks: fp.KeySize = oks

        self.calc_pitch = fp.PitchCustom.Value \
            if fp.Diameter == "Custom" and hasattr(fp,"PitchCustom") else None

        thread_on = (("TThread" in params or "TNutThread" in params) and
                     hasattr(fp,"Thread") and bool(fp.Thread))
        asme_type = _is_asme_std(fp.Type)
        has_ext   = "TThread" in params

        _is_metric_nut_exec = thread_on and not asme_type and "TNutThread" in params
        _is_asme_nut_exec   = thread_on and asme_type and "TNutThread" in params
        _is_metric_bolt_exec = thread_on and not asme_type and "TThread" in params

        # ── ASME nut execute: populate Thread_Type_Nut, Thread_TPI_Nut, Thread_Class_Nut_ASME
        if _is_asme_nut_exec and _TAI is not None:
            _dia_an_e = str(self.calc_diam or fp.Diameter or "")

            # Thread_Type_Nut
            _atypes_e = _TAI.valid_types_for_dia(_dia_an_e) or ["UNC"]
            if not hasattr(fp, "Thread_Type_Nut"):
                fp.addProperty("App::PropertyEnumeration", "Thread_Type_Nut",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_Type_Nut — ASME B1.1 series (UNC/UNF/UN/UNEF)")
                ).Thread_Type_Nut = _atypes_e
                try: fp.Thread_Type_Nut = "UNC" if "UNC" in _atypes_e else _atypes_e[0]
                except Exception: pass
            else:
                try:
                    _cur_at = str(fp.Thread_Type_Nut)
                    fp.Thread_Type_Nut = _atypes_e
                    fp.Thread_Type_Nut = _cur_at if _cur_at in _atypes_e else                                          ("UNC" if "UNC" in _atypes_e else _atypes_e[0])
                except Exception: pass

            # Thread_TPI_Nut
            _at_e = ""
            try: _at_e = str(fp.Thread_Type_Nut)
            except Exception: pass
            _at_e = _at_e or "UNC"
            _atpis_e = _TAI.tpi_enum_options_for_nut(_dia_an_e, _at_e) or ["8", "Custom"]
            if not hasattr(fp, "Thread_TPI_Nut"):
                fp.addProperty("App::PropertyEnumeration", "Thread_TPI_Nut",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_TPI_Nut — ASME B1.1 threads per inch")
                ).Thread_TPI_Nut = _atpis_e
                try: fp.Thread_TPI_Nut = next((x for x in _atpis_e if x != "Custom"), _atpis_e[0])
                except Exception: pass
            else:
                try:
                    _cur_atpi = str(fp.Thread_TPI_Nut)
                    fp.Thread_TPI_Nut = _atpis_e
                    fp.Thread_TPI_Nut = _cur_atpi if _cur_atpi in _atpis_e else next((x for x in _atpis_e if x != "Custom"), _atpis_e[0])
                except Exception: pass
            # Thread_TPI_Nut_Custom — float spinner for custom TPI
            if not hasattr(fp, "Thread_TPI_Nut_Custom"):
                fp.addProperty("App::PropertyFloat", "Thread_TPI_Nut_Custom",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_TPI_Nut Custom value (supports decimals, e.g. 4.5)")
                ).Thread_TPI_Nut_Custom = 0.0
            _tpi_nut_sel = ""
            try: _tpi_nut_sel = str(fp.Thread_TPI_Nut)
            except Exception: pass
            _cust_nut = (_tpi_nut_sel == "Custom")
            fp.setEditorMode("Thread_TPI_Nut_Custom", 0 if _cust_nut else 2)
            if not _cust_nut and _tpi_nut_sel:
                try: fp.Thread_TPI_Nut_Custom = float(_tpi_nut_sel)
                except (ValueError, TypeError): pass

            # Thread_Class_Nut_ASME
            _atpi_e = ""
            try: _atpi_e = str(fp.Thread_TPI_Nut)
            except Exception: pass
            _atpi_e = _atpi_e or "8"
            _ancls_e = _TAI.valid_classes_for_dia_tpi_type(_dia_an_e, _atpi_e, _at_e) or ["2B"]
            if not hasattr(fp, "Thread_Class_Nut_ASME"):
                fp.addProperty("App::PropertyEnumeration", "Thread_Class_Nut_ASME",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_Class_Nut_ASME — ASME B1.1 (2B=standard)")
                ).Thread_Class_Nut_ASME = _ancls_e
                try:
                    _def_ancls_e = "2B" if "2B" in _ancls_e else _ancls_e[0]
                    fp.Thread_Class_Nut_ASME = _def_ancls_e
                except Exception: pass
            else:
                try:
                    _cur_ancls = str(fp.Thread_Class_Nut_ASME)
                    fp.Thread_Class_Nut_ASME = _ancls_e
                    fp.Thread_Class_Nut_ASME = _cur_ancls if _cur_ancls in _ancls_e else                                                ("2B" if "2B" in _ancls_e else _ancls_e[0])
                except Exception: pass

            # Store for FSmakeHexNut bore lookup
            self.Thread_Type_Nut     = str(getattr(fp, "Thread_Type_Nut",     "UNC") or "UNC")
            self.Thread_TPI_Nut      = str(getattr(fp, "Thread_TPI_Nut",      "")   or "")
            self.Thread_Class_Nut_ASME = str(getattr(fp, "Thread_Class_Nut_ASME", "2B") or "2B")

            # Resolve calc_tpi and calc_pitch from selected TPI
            _tpi_val = _TAI.resolve_nut_tpi(self)
            if _tpi_val and _tpi_val > 0:
                self.calc_tpi   = _tpi_val
                self.calc_pitch = 25.4 / _tpi_val
            else:
                self.calc_tpi   = None

            _TAI.set_asme_nut_visibility(fp, True)

        if _is_metric_nut_exec and _TMI is not None:
            _dia_pre = str(self.calc_diam or fp.Diameter or "")

            _np = _TMI.valid_pitches_for_dia(_dia_pre)
            if not _np:
                _np = _TMI.valid_pitches_for_dia(str(fp.Diameter or ""))
            if _np:
                if not hasattr(fp, "Thread_Pitch_Nut"):
                    fp.addProperty("App::PropertyEnumeration", "Thread_Pitch_Nut",
                        "Parameters",
                        translate("FastenerCmd",
                            "Thread_Pitch_Nut (mm) — from ISO 965 internal thread table")
                    ).Thread_Pitch_Nut = (list(_np) + ["Custom"])
                    try: fp.Thread_Pitch_Nut = _np[0]
                    except Exception: pass
                else:
                    try:
                        _cur_np = str(fp.Thread_Pitch_Nut)
                        _np_enum = list(_np) + ["Custom"]
                        fp.Thread_Pitch_Nut = _np_enum
                        fp.Thread_Pitch_Nut = _cur_np if _cur_np in _np_enum else _np[0]
                    except Exception: pass

            if not hasattr(fp, "Thread_Pitch_Nut_Custom"):
                _init_np_custom_e = 1.0
                try:
                    _init_np_custom_e = float(str(getattr(fp, "Thread_Pitch_Nut", "1.0") or "1.0"))
                except Exception:
                    pass
                fp.addProperty("App::PropertyFloat", "Thread_Pitch_Nut_Custom",
                    "Parameters",
                    translate("FastenerCmd", "Thread_Pitch_Nut Custom value (mm)")
                ).Thread_Pitch_Nut_Custom = _init_np_custom_e

            _pn_now = ""
            try: _pn_now = str(fp.Thread_Pitch_Nut)
            except Exception: pass
            _pn_now = _pn_now or (_np[0] if _np else "1.0")
            if _pn_now == "Custom":
                try:
                    _pn_custom = float(getattr(fp, "Thread_Pitch_Nut_Custom", 0) or 0)
                    if _pn_custom > 0:
                        _pn_now = str(_pn_custom)
                except Exception:
                    pass
            _cn = _TMI.valid_classes_for_dia_pitch(_dia_pre, _pn_now) or ["6H"]
            if not hasattr(fp, "Thread_Class_Nut"):
                fp.addProperty("App::PropertyEnumeration", "Thread_Class_Nut",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_Class_Nut — ISO 965 internal (6H=standard)")
                ).Thread_Class_Nut = _cn
                _def_cn = "6H" if "6H" in _cn else _cn[0]
                try: fp.Thread_Class_Nut = _def_cn
                except Exception: pass
            else:
                try:
                    _cur_cn = str(fp.Thread_Class_Nut)
                    fp.Thread_Class_Nut = _cn
                    fp.Thread_Class_Nut = _cur_cn if _cur_cn in _cn else \
                                           ("6H" if "6H" in _cn else _cn[0])
                except Exception: pass

            self.Thread_Pitch_Nut = str(getattr(fp, "Thread_Pitch_Nut", "") or "")
            self.Thread_Class_Nut = str(getattr(fp, "Thread_Class_Nut", "") or "6H")
            self.Thread_Root      = str(getattr(fp, "Thread_Root", "Flat") or "Flat")

        if _is_metric_bolt_exec:
            _dia_pre = str(self.calc_diam or fp.Diameter or "")
            if not hasattr(fp, "Thread_Root") and "TPitch" in params:
                fp.addProperty("App::PropertyEnumeration", "Thread_Root",
                    "Parameters",
                    translate("FastenerCmd",
                        "Thread_Root: Flat (ISO standard) or Round (ISO 68-1)")
                ).Thread_Root = ["Flat", "Round"]
                try: fp.Thread_Root = "Flat"
                except Exception: pass
                fp.setEditorMode("Thread_Root", 0)

            _pp = _TM.valid_pitches_for_dia(_dia_pre)
            if not _pp:
                _pp = _TM.valid_pitches_for_dia(str(fp.Diameter or ""))
            if _pp:
                if not hasattr(fp, "Thread_Pitch") and "TPitch" in params:
                    fp.addProperty("App::PropertyEnumeration", "Thread_Pitch",
                        "Parameters",
                        translate("FastenerCmd", "Thread_Pitch (mm) — from ISO 965 table")
                    ).Thread_Pitch = _pp
                    fp.setEditorMode("Thread_Pitch", 0)
                elif hasattr(fp, "Thread_Pitch"):
                    try:
                        _cur_p2 = str(fp.Thread_Pitch)
                        fp.Thread_Pitch = _pp
                        fp.Thread_Pitch = _cur_p2 if _cur_p2 in _pp else _pp[0]
                        fp.setEditorMode("Thread_Pitch", 0)
                    except Exception: pass

            _p_now = ""
            try: _p_now = str(fp.Thread_Pitch)
            except Exception: pass
            _p_now = _p_now or (_pp[0] if _pp else "1.0")
            _cp = _TM.valid_classes_for_dia_pitch(_dia_pre, _p_now)
            if not _cp: _cp = ["6g"]
            if not hasattr(fp, "Thread_Class_ISO") and "TPitch" in params:
                fp.addProperty("App::PropertyEnumeration", "Thread_Class_ISO",
                    "Parameters",
                    translate("FastenerCmd", "Thread_Class — ISO 965 (6g=standard)")
                ).Thread_Class_ISO = _cp
                _def_cls = "6g" if "6g" in _cp else _cp[0]
                try: fp.Thread_Class_ISO = _def_cls
                except Exception: pass
                fp.setEditorMode("Thread_Class_ISO", 0)
            elif hasattr(fp, "Thread_Class_ISO"):
                try:
                    _cur_c = str(fp.Thread_Class_ISO)
                    fp.Thread_Class_ISO = _cp
                    fp.Thread_Class_ISO = _cur_c if _cur_c in _cp else _cp[0]
                    fp.setEditorMode("Thread_Class_ISO", 0)
                except Exception: pass

        _set_thread_props_visibility(fp, thread_on)

        if thread_on and asme_type and has_ext:
            _nom     = _TA.bolt_nominal(fp.Diameter)
            _tt      = str(getattr(fp, "Thread_Type", "UNC") or "UNC")
            _tpi_sel = str(getattr(fp, "Thread_TPI",  "")   or "")
            _cust    = float(getattr(fp, "Thread_TPI_Custom", 0)   or 0)
            _is_cust = (_tpi_sel == "Custom")

            _res_tpi = (_cust if _cust > 0 else 0) if _is_cust else \
                       (float(_tpi_sel) if _tpi_sel and _tpi_sel != "Custom" else 0)

            if _res_tpi > 0:
                self.calc_tpi   = _res_tpi
                self.calc_pitch = 25.4 / _res_tpi
            else:
                self.calc_tpi   = None
                self.calc_pitch = None

            if hasattr(fp, "Thread_Type"):
                _t2_opts = _TA.valid_thread2types_for_dia(_nom)
                try:
                    _cur = str(fp.Thread_Type)
                    fp.Thread_Type = _t2_opts
                    _restore = _cur if _cur in _t2_opts else _t2_opts[0]
                    if str(fp.Thread_Type) != _restore:
                        fp.Thread_Type = _restore
                    if _cur not in _t2_opts: _tt = _t2_opts[0]
                except Exception: pass

            if hasattr(fp, "Thread_TPI"):
                _tpi_opts = _TA.tpi_enum_options(_nom, _tt)
                try:
                    _cur = str(fp.Thread_TPI)
                    fp.Thread_TPI = _tpi_opts
                    _cust_val = float(getattr(fp, "Thread_TPI_Custom", 0) or 0)
                    if _cur == "Custom" and _cust_val == 0:
                        _first = next((x for x in _tpi_opts if x != "Custom"), None)
                        _restore = _first or "Custom"
                    elif _cur in _tpi_opts:
                        _restore = _cur
                    else:
                        _restore = next((x for x in _tpi_opts if x != "Custom"), "Custom")
                    if str(fp.Thread_TPI) != _restore:
                        fp.Thread_TPI = _restore
                except Exception: pass
                try:
                    _tpi_now = str(fp.Thread_TPI)
                    if _tpi_now != "Custom" and hasattr(fp, "Thread_TPI_Custom"):
                        fp.Thread_TPI_Custom = float(_tpi_now)
                except Exception: pass

            if hasattr(fp, "Thread_Class"):
                if _is_cust and _res_tpi > 0:
                    _near_tpi = _TA.nearest_tpi(_res_tpi, _nom, _tt)
                    _vcls = _TA.valid_classes_for_series_tpi(_nom, _tt, _near_tpi)
                elif _is_cust:
                    _vcls = _TA.all_classes_for_nominal(_nom)
                else:
                    _vcls = (_TA.valid_classes_for_series_tpi(_nom, _tt, _res_tpi)
                             if _res_tpi > 0 else ["2A", "3A"])
                if _vcls:
                    try:
                        _cur = str(fp.Thread_Class)
                        fp.Thread_Class = _vcls
                        _restore = _cur if _cur in _vcls else _vcls[0]
                        if str(fp.Thread_Class) != _restore:
                            fp.Thread_Class = _restore
                    except Exception: pass
            self.Thread_Class = str(fp.Thread_Class) if hasattr(fp, "Thread_Class") else "2A"

            _set_thread_props_visibility(fp, True)

        elif thread_on and not asme_type:
            if "TNutThread" in params and _TMI is not None:
                _TMI.set_nut_thread_visibility(fp, True)
                if not hasattr(fp, "Thread_Pitch_Nut"):
                    _dia_en = str(fp.Diameter or "")
                    _np_e = _TMI.valid_pitches_for_dia(_dia_en)
                    if _np_e:
                        fp.addProperty("App::PropertyEnumeration", "Thread_Pitch_Nut",
                            "Parameters",
                            translate("FastenerCmd",
                                "Thread_Pitch_Nut (mm) — from ISO 965 internal thread table")
                        ).Thread_Pitch_Nut = (list(_np_e) + ["Custom"])
                        try: fp.Thread_Pitch_Nut = _np_e[0]
                        except Exception: pass
                        fp.setEditorMode("Thread_Pitch_Nut", 0)
                if not hasattr(fp, "Thread_Pitch_Nut_Custom"):
                    fp.addProperty("App::PropertyFloat", "Thread_Pitch_Nut_Custom",
                        "Parameters",
                        translate("FastenerCmd", "Thread_Pitch_Nut Custom value (mm)")
                    ).Thread_Pitch_Nut_Custom = 1.0
            if hasattr(fp, "Thread_Pitch"):
                _dia_e   = str(fp.Diameter or "")
                _new_p_e = _TM.valid_pitches_for_dia(_dia_e)
                if _new_p_e:
                    try:
                        _cur_p = str(fp.Thread_Pitch)
                        fp.Thread_Pitch = _new_p_e
                        fp.Thread_Pitch = _cur_p if _cur_p in _new_p_e else _new_p_e[0]
                    except Exception:
                        pass

            if hasattr(fp, "Thread_Class_ISO") and hasattr(fp, "Thread_Pitch"):
                _p_e  = str(fp.Thread_Pitch or "")
                _dia_e = str(fp.Diameter or "")
                _new_cls_e = _TM.valid_classes_for_dia_pitch(_dia_e, _p_e)
                if _new_cls_e:
                    try:
                        _cur_c = str(fp.Thread_Class_ISO)
                        fp.Thread_Class_ISO = _new_cls_e
                        fp.Thread_Class_ISO = _cur_c if _cur_c in _new_cls_e else _new_cls_e[0]
                    except Exception:
                        pass

            _mp = str(getattr(fp, "Thread_Pitch", "") or "")
            if _mp:
                try:
                    self.calc_pitch = float(_mp)
                except ValueError:
                    pass
            if not self.calc_pitch:
                if hasattr(fp, "ThreadPitch"):
                    v = fp.ThreadPitch.Value
                    if v > 0.0:
                        self.calc_pitch = v

            self.Thread_Pitch     = str(getattr(fp, "Thread_Pitch",     "") or "")
            self.Thread_Class_ISO = str(getattr(fp, "Thread_Class_ISO", "") or "6g")
            self.Thread_Root      = str(getattr(fp, "Thread_Root",  "Flat") or "Flat")
            self.Thread_Pitch_Nut = str(getattr(fp, "Thread_Pitch_Nut", "") or "")
            self.Thread_Class_Nut = str(getattr(fp, "Thread_Class_Nut", "") or "6H")

            _set_thread_props_visibility(fp, True)

        elif thread_on and hasattr(fp, "ThreadPitch"):
            v = fp.ThreadPitch.Value
            if v > 0.0:
                self.calc_pitch = v

        if thread_on and hasattr(fp, "Thread_Length"):
            is_nut = "TNutThread" in params and "TThread" not in params
            self.calc_thread_length = 0.0 if is_nut else fp.Thread_Length.Value
        else:
            self.calc_thread_length = 0.0

        # ── Console log: full threading summary with deviation breakdown ──────
        if thread_on:
            _log_dia  = self.calc_diam or "?"
            _log_len  = self.calc_len  or "?"
            _log_tlen = self.calc_thread_length \
                        if hasattr(self, "calc_thread_length") else 0.0

            try:
                _nom_mm = float(
                    str(self.calc_diam).replace("mm", "").strip()
                ) if self.calc_diam else 0.0
            except Exception:
                _nom_mm = 0.0

            if asme_type and has_ext:
                _log_tpi   = self.calc_tpi or "?"
                _log_pitch = f"{self.calc_pitch:.5f} mm" \
                             if self.calc_pitch else "standard"
                _log_cls   = self.Thread_Class or "2A"
                _log_type  = self.Thread_Type  or "UNC"
                _log_series = _log_type if _log_type in ("UNC","UNF","UNEF") else "UN"
                _is_cust_log = str(getattr(fp, "Thread_TPI", "")) == "Custom"

                _d_raw = None
                try:
                    _nom_key = _TA.bolt_nominal(self.calc_diam)
                    _tpi_num = float(_log_tpi) if str(_log_tpi).replace(".","").isdigit() else 0
                    if _is_cust_log and _tpi_num > 0:
                        _near_log = _TA.nearest_tpi(_tpi_num, _nom_key, _log_series)
                        _d_raw = _TA.outer_dia_mm(_nom_key, _log_series, _near_log, _log_cls)
                    else:
                        _d_raw = _TA.outer_dia_mm(_nom_key, _log_series, _tpi_num, _log_cls)
                except Exception:
                    pass

                _d_eff = None
                try:
                    _d_eff = _TA.get_shank_dia(self, _nom_mm)
                except Exception:
                    pass

                _pct = 0.0
                _dev = 0.0
                if _d_raw and _d_raw > 0 and _nom_mm > 0:
                    try:
                        from FSThreadingASME import \
                            _interpolated_deviation_pct as _apct
                        _pct = _apct(_nom_mm)
                        _dev = _d_raw * _pct / 100.0
                    except Exception:
                        pass

                _diff = (_nom_mm - _d_eff) if (_d_eff and _nom_mm) else 0.0

                FreeCAD.Console.PrintMessage(
                    f"\n{'═'*60}\n"
                    f"  ASME THREAD PARAMETERS\n"
                    f"{'─'*60}\n"
                    f"  Bolt type              : {fp.Type}\n"
                    f"  Nominal diameter       : {_log_dia}  ({_nom_mm:.4f} mm)\n"
                    f"  Thread type            : {_log_type}\n"
                    f"  Series                 : {_log_series}\n"
                    f"  TPI                    : {_log_tpi}\n"
                    f"  Pitch                  : {_log_pitch}\n"
                    f"  Class                  : {_log_cls}\n"
                    f"{'─'*60}\n"
                    f"  Thread_Outer_Dia (CSV) : "
                    f"{f'{_d_raw:.5f} mm' if _d_raw else 'not found'}"
                    f"  ← un_unr_limits_of_size.csv\n"
                    f"  Deviation pct          : {_pct:.4f} %"
                    f"  (interpolated for {_nom_mm:.4f} mm)\n"
                    f"  Deviation mm           : {_dev:.5f} mm\n"
                    f"  d_eff (body + cutter)  : "
                    f"{f'{_d_eff:.5f} mm' if _d_eff else 'fallback = nominal'}"
                    f"  ← used for shank + thread cutter\n"
                    f"  Difference from nominal: "
                    f"{_nom_mm:.4f} - "
                    f"{f'{_d_eff:.4f}' if _d_eff else '?'}"
                    f" = {_diff:.4f} mm smaller\n"
                    f"{'─'*60}\n"
                    f"  Thread length          : {_log_tlen:.3f} mm\n"
                    f"  Total bolt length      : {_log_len} mm\n"
                    f"{'═'*60}\n"
                )

            else:
                _log_pitch = f"{self.calc_pitch:.5f} mm" \
                             if self.calc_pitch else "standard"
                _mp  = str(getattr(self, "Thread_Pitch",     "") or "")
                _mc  = str(getattr(self, "Thread_Class_ISO", "") or "6g")
                _root= str(getattr(self, "Thread_Root", "Flat") or "Flat")

                _d_raw = None
                try:
                    _d_raw = _TM.mean_dia_from_table(
                        self.calc_diam,
                        str(float(_mp)) if _mp else "",
                        _mc)
                except Exception:
                    pass

                _d_eff = None
                try:
                    _d_eff = _TM.get_shank_dia(self, _nom_mm)
                except Exception:
                    pass

                _pct = 0.0
                _dev = 0.0
                if _d_raw and _d_raw > 0 and _nom_mm > 0:
                    try:
                        from FSThreadingMetric import \
                            _interpolated_deviation_pct as _mpct
                        _pct = _mpct(_nom_mm)
                        _dev = _d_raw * _pct / 100.0
                    except Exception:
                        pass

                _diff = (_nom_mm - _d_eff) if (_d_eff and _nom_mm) else 0.0

                FreeCAD.Console.PrintMessage(
                    f"\n{'═'*60}\n"
                    f"  METRIC THREAD PARAMETERS\n"
                    f"{'─'*60}\n"
                    f"  Bolt type              : {fp.Type}\n"
                    f"  Nominal diameter       : {_log_dia}  ({_nom_mm:.4f} mm)\n"
                    f"  Thread pitch           : {_mp} mm\n"
                    f"  Class (ISO)            : {_mc}\n"
                    f"  Root profile           : {_root}\n"
                    f"  Resolved pitch         : {_log_pitch}\n"
                    f"{'─'*60}\n"
                    f"  Thread_Mean_Dia (CSV)  : "
                    f"{f'{_d_raw:.5f} mm' if _d_raw else 'not found'}"
                    f"  ← metric_thread_dia.csv\n"
                    f"  Deviation pct          : {_pct:.4f} %"
                    f"  (interpolated for {_nom_mm:.4f} mm)\n"
                    f"  Deviation mm           : {_dev:.5f} mm\n"
                    f"  d_eff (body + cutter)  : "
                    f"{f'{_d_eff:.5f} mm' if _d_eff else 'fallback = nominal'}"
                    f"  ← used for shank + thread cutter\n"
                    f"  Difference from nominal: "
                    f"{_nom_mm:.4f} - "
                    f"{f'{_d_eff:.4f}' if _d_eff else '?'}"
                    f" = {_diff:.4f} mm smaller\n"
                    f"{'─'*60}\n"
                    f"  Thread length          : {_log_tlen:.3f} mm\n"
                    f"  Total bolt length      : {_log_len} mm\n"
                    f"{'═'*60}\n"
                )

        # ── Store thread params for FsMake shape functions ────────────────
        self.Thread_Type   = str(fp.Thread_Type)   if (thread_on and hasattr(fp, "Thread_Type"))  else "UNC"
        self.Thread_TPI    = str(fp.Thread_TPI)    if hasattr(fp, "Thread_TPI")                   else ""
        self.Thread_TPI_Custom = float(fp.Thread_TPI_Custom) if hasattr(fp, "Thread_TPI_Custom")  else 0.0
        self.Thread_Class  = str(fp.Thread_Class)  if (thread_on and hasattr(fp, "Thread_Class")) else "2A"
        self.ThreadSeries  = ""
        if not hasattr(self, "Thread_Pitch"): self.Thread_Pitch = ""
        if not hasattr(self, "Thread_Class_ISO"): self.Thread_Class_ISO = "6g"
        if thread_on and not asme_type:
            self.Thread_Pitch = str(getattr(fp, "Thread_Pitch", "") or "")
            self.Thread_Class_ISO = str(getattr(fp, "Thread_Class_ISO", "") or "6g")
        # Store ASME nut internal thread params for FSmakeHexNut bore lookup
        if not hasattr(self, "Thread_Type_Nut"):     self.Thread_Type_Nut     = "UNC"
        if not hasattr(self, "Thread_TPI_Nut"):      self.Thread_TPI_Nut      = ""
        if not hasattr(self, "Thread_Class_Nut_ASME"): self.Thread_Class_Nut_ASME = "2B"
        if thread_on and asme_type and "TNutThread" in params:
            self.Thread_Type_Nut     = str(getattr(fp, "Thread_Type_Nut",     "UNC") or "UNC")
            self.Thread_TPI_Nut      = str(getattr(fp, "Thread_TPI_Nut",      "")   or "")
            self.Thread_Class_Nut_ASME = str(getattr(fp, "Thread_Class_Nut_ASME", "2B") or "2B")

        screwMaker.updateFastenerParameters()
        self.BackupObject(fp)
        self.baseType = FSGetTypeAlias(self.Type)

        # ── Pre-process dimTable for ASME types before FsMake unpacking ───
        # New CSV has 7 data cols: b1, P, c, e, k, r, s  (b2 and dw removed)
        # FsMakeHexHeadBolt (doc10) expects 8 cols: b1, P, c, _dw_unused, e, k, r, s
        # → CMD inserts dummy dw=0.0 between c and e so FsMake unpack works unchanged.
        if self.baseType in ("ASMEB18.2.1.2", "ASMEB18.2.1.3", "ASMEB18.2.1.7"):
            try:
                if self.dimTable and len(self.dimTable) == 7:
                    b1, P_t, c_t, e_t, k_t, r_t, s_t = self.dimTable
                    # insert dummy dw=0.0 — FsMake discards it (_dw_unused)
                    self.dimTable = (b1, P_t, c_t, 0.0, e_t, k_t, r_t, s_t)
            except Exception:
                pass

        (key, s) = FastenerBase.FSGetKey(self.GetKey())
        if s is None:
            s = screwMaker.createFastener(self)
            FastenerBase.FSCache[key] = s
        else:
            FreeCAD.Console.PrintLog("Using cached object\n")

        dispDiam = self.CleanDecimals(self.calc_diam)
        label = dispDiam
        if hasattr(fp,"Length"):
            label += "x" + self.ActiveLength(fp)
            if hasattr(fp,"Width"): label += "x" + fp.Width
        if hasattr(fp,"LeftHanded") and self.LeftHanded: label += "LH"
        if hasattr(fp,"SlotWidth"): label += " x " + fp.SlotWidth
        label += "-" + translate("FastenerCmdTreeView", self.familyType)
        fp.Label = label
        fp.Shape = s

        if shape is not None:
            FastenerBase.FSMoveToObject(
                fp, shape, fp.Invert, fp.Offset.Value, fp.OffsetAngle.Value)


##########################################################################################################
# Gui code
##########################################################################################################

if FSutils.isGuiLoaded():
    from PySide import QtCore, QtGui
    from FreeCAD import Gui

    class FSViewProviderTree:
        def __init__(self, obj):
            obj.Proxy = self
            self.Object = obj.Object

        def attach(self, obj):
            self.Object = obj.Object

        def updateData(self, fp, prop): pass
        def getDisplayModes(self, obj): return []
        def setDisplayMode(self, mode): return mode

        def onChanged(self, vp, prop):
            if prop in {"Type","RestoredIcon"}:
                r = getattr(vp, "signalChangeIcon", None)
                if callable(r): r()

        def dumps(self): return None

        def loads(self, state):
            if state is not None:
                self.Object = FreeCAD.ActiveDocument.getObject(
                    state["ObjectName"])

        if FastenerBase.FsUseGetSetState:
            def __getstate__(self): return self.dumps()
            def __setstate__(self, s): self.loads(s)

        def getIcon(self):
            type = "ISO4017.svg"
            if hasattr(self.Object,"Type"):            type = self.Object.Type
            elif hasattr(self.Object.Proxy,"Type"):    type = self.Object.Proxy.Type
            return os.path.join(iconPath, FSGetIconAlias(type) + ".svg")

    class FSScrewCommand:
        def __init__(self, type, help):
            self.Type = type
            self.Help = help
            self.TypeName = screwMaker.GetTypeName(type)

        def GetResources(self):
            import GrammaticalTools
            return {
                "Pixmap": os.path.join(iconPath, FSGetIconAlias(self.Type)+".svg"),
                "MenuText": translate("FastenerCmd","Add ") +
                            GrammaticalTools.ToDativeCase(self.Help),
                "ToolTip": self.Help,
            }

        def Activated(self):
            FreeCAD.ActiveDocument.openTransaction("Add fastener")
            for selObj in FastenerBase.FSGetAttachableSelections():
                a = FreeCAD.ActiveDocument.addObject(
                    "Part::FeaturePython", self.TypeName)
                FSScrewObject(a, self.Type, selObj)
                a.Label = a.Proxy.familyType
                if FSParam.GetBool("DefaultFastenerColorActive", False):
                    a.ViewObject.DiffuseColor = FSParam.GetUnsigned(
                        "DefaultFastenerColor", 0xccccccff)
                    a.ViewObject.Transparency = FSParam.GetUnsigned(
                        "DefaultFastenerTransparency", 0)
                if FSParam.GetBool("DefaultLineWidthActive", False):
                    a.ViewObject.LineWidth = FSParam.GetFloat("DefaultLineWidth",1.0)
                if FSParam.GetBool("DefaultVertexSizeActive", False):
                    a.ViewObject.PointSize = FSParam.GetFloat("DefaultVertexSize",1.0)
                FSViewProviderTree(a.ViewObject)
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()

        def IsActive(self):
            return Gui.ActiveDocument is not None

    def FSAddScrewCommand(type):
        enabled = {
            "ISO":  FSParam.GetBool("ShowISOInToolbars", True),
            "DIN":  FSParam.GetBool("ShowDINInToolbars", True),
            "EN":   FSParam.GetBool("ShowENInToolbars", True),
            "ASME": FSParam.GetBool("ShowASMEInToolbars", True),
            "SAE":  FSParam.GetBool("ShowSAEInToolbars", True),
            "GOST": FSParam.GetBool("ShowGOSTInToolbars", True),
            "BSPP": FSParam.GetBool("ShowBSPPInToolbars", True),
            "other":True,
        }
        cmd = "FS" + type
        Gui.addCommand(cmd, FSScrewCommand(type, FSGetDescription(type)))
        group = FSScrewCommandTable[type][CMD_GROUP]
        if not enabled[FSGetStandardFromType(type)]:
            group = "Other " + group
        FastenerBase.FSCommands.append(cmd, "screws", group)

    for key in FSScrewCommandTable:
        FSAddScrewCommand(key)


##########################################################################################################
# Object classes
##########################################################################################################

class FSWasherObject(FSScrewObject):
    pass

class FSScrewRodObject(FSScrewObject):
    def onDocumentRestored(self, obj):
        if hasattr(obj.Proxy,"type"):     self.originalType = obj.Proxy.type
        elif hasattr(obj.Proxy,"Type"):   self.originalType = obj.Proxy.Type
        super().onDocumentRestored(obj)

class FSScrewDieObject(FSScrewObject):
    def onDocumentRestored(self, obj):
        if hasattr(obj.Proxy,"type"):     self.originalType = obj.Proxy.type
        elif hasattr(obj.Proxy,"Type"):   self.originalType = obj.Proxy.Type
        super().onDocumentRestored(obj)

class FSThreadedRodObject(FSScrewObject):
    def onDocumentRestored(self, obj):
        if hasattr(obj.Proxy,"type"):     self.originalType = obj.Proxy.type
        elif hasattr(obj.Proxy,"Type"):   self.originalType = obj.Proxy.Type
        super().onDocumentRestored(obj)

FastenerBase.FSAddFastenerType("Screw")
FastenerBase.FSAddFastenerType("Washer", False)
FastenerBase.FSAddFastenerType("Nut", False)
FastenerBase.FSAddFastenerType("ThreadedRod", True, False)
FastenerBase.FSAddFastenerType("PressNut", False)
FastenerBase.FSAddFastenerType("Standoff")
FastenerBase.FSAddFastenerType("Stud")
FastenerBase.FSAddFastenerType("HeatSet", False)
FastenerBase.FSAddFastenerType("RetainingRing", False)
FastenerBase.FSAddFastenerType("T-Slot", False)
FastenerBase.FSAddFastenerType("SetScrew")
FastenerBase.FSAddFastenerType("HexKey", False)
FastenerBase.FSAddFastenerType("Pin")
for item in ScrewMaker.screwTables:
    FastenerBase.FSAddItemsToType(ScrewMaker.screwTables[item][0], item)
