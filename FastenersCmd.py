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
RodParameters = {"Type", "Diameter", "MatchOuter", "Thread",
                 "LeftHanded", "lengthArbitrary", "DiameterCustom", "PitchCustom",
                 "TPitch", "TLength", "TThread"}
NutParameters = {"Type", "Diameter", "MatchOuter", "Thread", "LeftHanded",
                  "TNutThread", "TPitch"}
WoodInsertParameters = {"Type", "Diameter", "MatchOuter", "Thread", "LeftHanded"}
HeatInsertParameters = {"Type", "Diameter", "lengthArbitrary", "ExternalDiam", "MatchOuter", "Thread", "LeftHanded"}
WasherParameters = {"Type", "Diameter", "MatchOuter"}
PCBStandoffParameters = {"Type", "Diameter", "MatchOuter", "Thread",
                         "LeftHanded", "Thread_Length", "LenByDiamAndWidth", "LengthCustom", "widthCode",
                         "TPitch", "TLength", "TThread"}
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
                   'Blind', 'ScrewLength', "SlotWidth", 'ExternalDiam', 'KeySize',
                   'ThreadPitch', 'Thread_TPI', 'Thread_Length', 'Thread_Type',
                   'Thread_Class', 'Thread_TPI', 'Thread_TPI_Custom',
                   # Metric data-driven thread properties (metric_thread_dia.csv)
                   'Thread_Pitch', 'Thread_Class_ISO',
                   'Thread_Root']

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
    "ASMEB18.6.3.4B": (translate("FastenerCmd", "UNC Cross recessed oval countersunk head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.9B": (translate("FastenerCmd", "UNC Cross recessed pan head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.10B":(translate("FastenerCmd", "UNC Cross recessed fillister head screws"), HCrossGroup, ScrewParametersLC),
    "ASMEB18.6.3.12C":(translate("FastenerCmd", "UNC Cross recessed truss head screws"), HCrossGroup, ScrewParametersLC),
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
    "ASMEB18.5.2":(translate("FastenerCmd", "UNC Round head square neck bolts"), OtherHeadGroup, ScrewParametersLC),
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
    "DIN464":   (translate("FastenerCmd", "Knurled thumb screws, high type"), ThumbScrewGroup, ScrewParametersLC),
    "DIN465":   (translate("FastenerCmd", "Slotted knurled thumb screws, high type"), ThumbScrewGroup, ScrewParametersLC),
    "DIN653":   (translate("FastenerCmd", "Knurled thumb screws, low type"), ThumbScrewGroup, ScrewParametersLC),
    "GroundScrew":(translate("FastenerCmd", "round plate ground screw"), GroundScrewGroup, ScrewParametersLC),
    "ASMEB18.2.2.1A":(translate("FastenerCmd", "UNC Hex Machine screw nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.1B":(translate("FastenerCmd", "UNC Square machine screw nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.2": (translate("FastenerCmd", "UNC Square nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.4A":(translate("FastenerCmd", "UNC Hexagon nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.4B":(translate("FastenerCmd", "UNC Hexagon thin nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.5": (translate("FastenerCmd", "UNC Hex slotted nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.12":(translate("FastenerCmd", "UNC Hex flange nuts"), NutGroup, NutParameters),
    "ASMEB18.2.2.13":(translate("FastenerCmd", "UNC Hex coupling nuts"), NutGroup, NutParameters),
    "ASMEB18.6.9A":  (translate("FastenerCmd", "Wing nuts, type A"), NutGroup, NutParameters),
    "DIN315":   (translate("FastenerCmd", "Wing nuts"), NutGroup, NutParameters),
    "DIN557":   (translate("FastenerCmd", "Square nuts"), NutGroup, NutParameters),
    "DIN562":   (translate("FastenerCmd", "Square nuts"), NutGroup, NutParameters),
    "DIN917":   (translate("FastenerCmd", "Cap nuts, thin style"), NutGroup, NutParameters),
    "DIN928":   (translate("FastenerCmd", "Square weld nuts"), NutGroup, NutParameters),
    "DIN929":   (translate("FastenerCmd", "Hexagonal weld nuts"), NutGroup, NutParameters),
    "DIN934":   (translate("FastenerCmd", "(Superseded by ISO 4035 and ISO 8673) Hexagon thin nuts, chamfered"), NutGroup, NutParameters),
    "DIN935":   (translate("FastenerCmd", "Slotted / Castle nuts"), NutGroup, NutParameters),
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
    "ASMEB18.21.1.12A":(translate("FastenerCmd", "UN washers, narrow series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.12B":(translate("FastenerCmd", "UN washers, regular series"), WasherGroup, WasherParameters),
    "ASMEB18.21.1.12C":(translate("FastenerCmd", "UN washers, wide series"), WasherGroup, WasherParameters),
    "DIN6319C": (translate("FastenerCmd", "Spherical washer"), WasherGroup, WasherParameters),
    "DIN6319D": (translate("FastenerCmd", "Conical seat"), WasherGroup, WasherParameters),
    "DIN6319G": (translate("FastenerCmd", "Conical seat"), WasherGroup, WasherParameters),
    "DIN6340":  (translate("FastenerCmd", "Washers for clamping devices"), WasherGroup, WasherParameters),
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

def _is_asme(fp):
    try:
        return str(fp.Type).startswith("ASME")
    except Exception:
        return False

def _is_asme_external(fp):
    """True only for ASME types with external thread (TThread), not nuts."""
    try:
        params = FSGetParams(fp.Type)
        return str(fp.Type).startswith("ASME") and "TThread" in params
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
    is_asme_type = str(fp.Type).startswith("ASME")
    has_ext      = "TThread"    in params
    has_nut      = "TNutThread" in params

    if is_asme_type and has_ext:
        _vis_asme_external(fp, thread_on)
    elif is_asme_type and has_nut:
        for _p in ("Thread_Type", "Thread_TPI", "Thread_TPI_Custom",
                   "Thread_Class", "Thread_Length", "ThreadPitch"):
            if hasattr(fp, _p):
                fp.setEditorMode(_p, 2)
    else:
        _TM.set_metric_thread_visibility(fp, thread_on)


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
                and not str(getattr(fp, "Type", "")).startswith("ASME") \
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
                        _restore = _cur if _cur in _opts else                             next((x for x in _opts if x != "Custom"), "Custom")
                        if str(fp.Thread_TPI) != _restore:
                            fp.Thread_TPI = _restore
                    except Exception:
                        pass
            elif prop == "Thread_TPI":
                _nom   = _TA.bolt_nominal(getattr(fp, "Diameter", "") or "")
                _tt    = str(getattr(fp, "Thread_Type", "UNC") or "UNC")
                _tpi_s = str(getattr(fp, "Thread_TPI", "") or "")

                # ── Mirror standard TPI into Thread_TPI_Custom ────────────
                # Same pattern as Length / LengthCustom:
                # whenever user picks a standard value, mirror it into Custom
                # so Custom field always shows the last-selected standard value.
                if _tpi_s != "Custom" and _tpi_s and hasattr(fp, "Thread_TPI_Custom"):
                    try:
                        fp.Thread_TPI_Custom = int(float(_tpi_s))
                    except (ValueError, TypeError):
                        pass

                if hasattr(fp, "Thread_Class"):
                    if _tpi_s == "Custom":
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
            _is_m = not str(getattr(fp, "Type", "")).startswith("ASME")
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
        _is_metric_ext = not _this_type_early.startswith("ASME") and "TThread" in params
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

        if "TPitch" in params and not _this_type_early.startswith("ASME"):
            # Resolve actual diameter — "Auto" has no pitches so use AutoDiameter
            _dia_v = str(getattr(obj, "Diameter", diameter) or "")
            if _dia_v in ("Auto", "", "Custom"):
                try:
                    _dia_v = screwMaker.AutoDiameter(type, None, None, False)
                except Exception:
                    _dia_v = diameter or ""
            if not hasattr(obj, "Thread_Pitch"):
                _pitches = _TM.valid_pitches_for_dia(_dia_v)
                if not _pitches:
                    # fallback: try with diameter directly resolved
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
        _is_asme_t   = _this_type.startswith("ASME")
        _has_ext_t   = "TThread" in params
        _has_nut_t   = "TNutThread" in params

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
                # Default to first standard TPI (not Custom) — same as
                # Length defaulting to first standard length, not Custom
                _first_std_tpi = next((x for x in _sopts if x != "Custom"), None)
                try:
                    if _first_std_tpi:
                        obj.Thread_TPI = _first_std_tpi
                except Exception: pass
                obj.setEditorMode("Thread_TPI", 2)
            if not hasattr(obj, "Thread_TPI_Custom"):
                # Mirror current TPI into Custom on creation so user never sees 0
                _cur_tpi_str = ""
                try:
                    _cur_tpi_str = str(obj.Thread_TPI)
                except Exception:
                    pass
                _init_custom = 0
                if _cur_tpi_str and _cur_tpi_str != "Custom":
                    try:
                        _init_custom = int(float(_cur_tpi_str))
                    except (ValueError, TypeError):
                        pass
                obj.addProperty("App::PropertyInteger", "Thread_TPI_Custom", "Parameters",
                    translate("FastenerCmd", "Thread_TPI Custom value")
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
                    fp.Length = "Custom" if origIsCustom else l
                    if not origIsCustom and hasattr(fp,"LengthCustom"):
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
        asme_type = str(fp.Type).startswith("ASME")
        has_ext   = "TThread" in params

        if thread_on and not asme_type:
            # Use calc_diam (already resolved from Auto) for CSV lookup
            _dia_pre = str(self.calc_diam or fp.Diameter or "")

            # ── Ensure Thread_Pitch property exists and has valid options ──
            # Always repopulate from CSV using resolved diameter
            _pp = _TM.valid_pitches_for_dia(_dia_pre)
            if not _pp:
                # last resort: try raw fp.Diameter
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
                    except Exception:
                        pass

            # ── Ensure Thread_Class_ISO property exists and has valid options ──
            _p_now = ""
            try:
                _p_now = str(fp.Thread_Pitch)
            except Exception:
                pass
            _p_now = _p_now or (_pp[0] if _pp else "1.0")
            _cp = _TM.valid_classes_for_dia_pitch(_dia_pre, _p_now)
            if not _cp:
                _cp = ["6g"]
            if not hasattr(fp, "Thread_Class_ISO") and "TPitch" in params:
                fp.addProperty("App::PropertyEnumeration", "Thread_Class_ISO",
                    "Parameters",
                    translate("FastenerCmd", "Thread_Class — ISO 965 (6g=standard)")
                ).Thread_Class_ISO = _cp
                _def_cls = "6g" if "6g" in _cp else _cp[0]
                try:
                    fp.Thread_Class_ISO = _def_cls
                except Exception:
                    pass
                fp.setEditorMode("Thread_Class_ISO", 0)
            elif hasattr(fp, "Thread_Class_ISO"):
                try:
                    _cur_c = str(fp.Thread_Class_ISO)
                    fp.Thread_Class_ISO = _cp
                    fp.Thread_Class_ISO = _cur_c if _cur_c in _cp else _cp[0]
                    fp.setEditorMode("Thread_Class_ISO", 0)
                except Exception:
                    pass

        _set_thread_props_visibility(fp, thread_on)

        if thread_on and asme_type and has_ext:
            _nom     = _TA.bolt_nominal(fp.Diameter)
            _tt      = str(getattr(fp, "Thread_Type", "UNC") or "UNC")
            _tpi_sel = str(getattr(fp, "Thread_TPI",  "")   or "")
            _cust    = int(getattr(fp, "Thread_TPI_Custom", 0)   or 0)
            _is_cust = (_tpi_sel == "Custom")

            _res_tpi = (_cust if _cust > 0 else 0) if _is_cust else \
                       (int(_tpi_sel) if _tpi_sel and _tpi_sel != "Custom" else 0)

            if _res_tpi > 0:
                self.calc_tpi   = _res_tpi
                self.calc_pitch = 25.4 / _res_tpi
            else:
                self.calc_tpi   = None
                self.calc_pitch = None

            if hasattr(fp, "Thread_Type"):
                _t2_opts = _TA.valid_thread2types_for_dia(_nom)
                try:
                    _cur = str(fp.Thread_Type)      # read BEFORE list assignment
                    fp.Thread_Type = _t2_opts
                    _restore = _cur if _cur in _t2_opts else _t2_opts[0]
                    if str(fp.Thread_Type) != _restore:
                        fp.Thread_Type = _restore
                    if _cur not in _t2_opts: _tt = _t2_opts[0]
                except Exception: pass

            if hasattr(fp, "Thread_TPI"):
                _tpi_opts = _TA.tpi_enum_options(_nom, _tt)
                try:
                    _cur = str(fp.Thread_TPI)       # read BEFORE list assignment
                    fp.Thread_TPI = _tpi_opts
                    # FreeCAD resets enum to index 0 on list assign — restore
                    _cust_val = int(getattr(fp, "Thread_TPI_Custom", 0) or 0)
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
                # ── Mirror standard TPI into Thread_TPI_Custom ────────────
                # Same pattern as Length/LengthCustom: standard selection
                # always mirrors into Custom field so user always sees current value.
                try:
                    _tpi_now = str(fp.Thread_TPI)
                    if _tpi_now != "Custom" and hasattr(fp, "Thread_TPI_Custom"):
                        fp.Thread_TPI_Custom = int(float(_tpi_now))
                except Exception: pass

            # _tt is the actual Thread_Type string (UNC/UNF/UNEF/UN/UNR)
            # valid_classes_for_series_tpi handles UN/UNR correctly
            if hasattr(fp, "Thread_Class"):
                _vcls = _TA.all_classes_for_nominal(_nom) if _is_cust else \
                        (_TA.valid_classes_for_series_tpi(_nom, _tt, _res_tpi)
                         if _res_tpi > 0 else ["2A", "3A"])
                if _vcls:
                    try:
                        # Read BEFORE assigning list — FreeCAD resets enum value
                        # to index 0 when list is assigned, losing the user's selection
                        _cur = str(fp.Thread_Class)
                        fp.Thread_Class = _vcls
                        # Restore user's selection (or first valid if not in new list)
                        _restore = _cur if _cur in _vcls else _vcls[0]
                        if str(fp.Thread_Class) != _restore:
                            fp.Thread_Class = _restore
                    except Exception: pass
            # ── Sync self.Thread_Class NOW (after fp is stable) ──────────────
            # Must happen after the enum is set so self gets the correct value
            self.Thread_Class = str(fp.Thread_Class) if hasattr(fp, "Thread_Class") else "2A" 

            _set_thread_props_visibility(fp, True)

        elif thread_on and not asme_type:
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

            # nominal mm — reference for interpolation
            try:
                _nom_mm = float(
                    str(self.calc_diam).replace("mm", "").strip()
                ) if self.calc_diam else 0.0
            except Exception:
                _nom_mm = 0.0

            if asme_type and has_ext:
                # ── ASME external thread ──────────────────────────────────
                _log_tpi   = self.calc_tpi or "?"
                _log_pitch = f"{self.calc_pitch:.5f} mm" \
                             if self.calc_pitch else "standard"
                _log_cls   = self.Thread_Class or "2A"
                _log_type  = self.Thread_Type  or "UNC"
                _log_series = _log_type if _log_type in ("UNC","UNF","UNEF") else "UN"

                # raw CSV dia
                _d_raw = None
                try:
                    _nom_key = _TA.bolt_nominal(self.calc_diam)
                    _d_raw   = _TA.outer_dia_mm(
                        _nom_key, _log_series,
                        float(_log_tpi) if str(_log_tpi).replace(".","").isdigit() else 0,
                        _log_cls)
                except Exception:
                    pass

                # deviated d_eff
                _d_eff = None
                try:
                    _d_eff = _TA.get_shank_dia(self, _nom_mm)
                except Exception:
                    pass

                # deviation pct + mm
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
                # ── Metric thread ─────────────────────────────────────────
                _log_pitch = f"{self.calc_pitch:.5f} mm" \
                             if self.calc_pitch else "standard"
                _mp  = str(getattr(self, "Thread_Pitch",     "") or "")
                _mc  = str(getattr(self, "Thread_Class_ISO", "") or "6g")
                _root= str(getattr(self, "Thread_Root", "Flat") or "Flat")

                # raw CSV dia
                _d_raw = None
                try:
                    _d_raw = _TM.mean_dia_from_table(
                        self.calc_diam,
                        str(float(_mp)) if _mp else "",
                        _mc)
                except Exception:
                    pass

                # deviated d_eff
                _d_eff = None
                try:
                    _d_eff = _TM.get_shank_dia(self, _nom_mm)
                except Exception:
                    pass

                # deviation pct + mm
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
        self.Thread_TPI_Custom = int(fp.Thread_TPI_Custom) if hasattr(fp, "Thread_TPI_Custom")    else 0
        self.Thread_Class  = str(fp.Thread_Class)  if (thread_on and hasattr(fp, "Thread_Class")) else "2A"
        self.ThreadSeries  = ""
        if not hasattr(self, "Thread_Pitch"): self.Thread_Pitch = ""
        if not hasattr(self, "Thread_Class_ISO"): self.Thread_Class_ISO = "6g"
        if thread_on and not asme_type:
            self.Thread_Pitch = str(getattr(fp, "Thread_Pitch", "") or "")
            self.Thread_Class_ISO = str(getattr(fp, "Thread_Class_ISO", "") or "6g")

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