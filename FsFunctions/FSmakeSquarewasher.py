# ─────────────────────────────────────────────────────────
# Wootz standard fastener function (admin-approved)
# type_id:        DIN436
# standard_name:  DIN 436
# approved_by:    adityaasingh904@gmail.com
# approved_at:    2026-06-16T18:42:46.716058
# source:         submission subb8b8f0ab9e234a
# ─────────────────────────────────────────────────────────

# -*- coding: utf-8 -*-
"""
***************************************************************************
* Copyright (c) 2013, 2014, 2015                                        *
* Original code by:                                                     *
* Ulrich Brammer <ulrich1a[at]users.sourceforge.net>                    *
* *
* This file is a supplement to the FreeCAD CAx development system.      *
* Modified to explicitly support DIN 436 Square Washers only.           *
***************************************************************************
"""
import math
from screw_maker import *

def makeSquarewasher(self, fa): # dynamically loaded method of class Screw
    """Creates a washer
    Supported types:
    - DIN436 Square washers for wood constructions
    """

    SType = fa.baseType

    # Read Custom geometry or DIN 436 table parameters
    if fa.dimTable is None:
        d1 = float(fa.DiameterCustom)
        a  = float(fa.WasherOuterDiaCustom)
        h  = float(fa.WasherThicknessCustom)
    elif SType == 'DIN436':
        # Unpacking based on "d1", "a", "s" from the CSV
        d1, a, h = fa.dimTable
    else:
        # Fallback if an unsupported type slips through
        return None

    # ── DIN 436 square washer geometry creation ──
    half_side = a / 2.0

    # Create the outer square body
    outer = Part.makeBox(
        a,
        a,
        h,
        Base.Vector(-half_side, -half_side, 0.0)
    )
    
    # Create the central cylindrical cutter for the through-hole
    # The cutter is extended 1 mm above and below (s + 2.0) to prevent coplanar face errors during the boolean cut
    cutter = Part.makeCylinder(
        d1 / 2.0,
        h + 2.0,
        Base.Vector(0.0, 0.0, -1.0),
        Base.Vector(0.0, 0.0, 1.0)
    )
    
    # Perform boolean cut to hollow out the washer
    return outer.cut(cutter)
