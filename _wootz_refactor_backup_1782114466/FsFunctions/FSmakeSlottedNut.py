# -*- coding: utf-8 -*-
"""
Wrapper module for slotted nuts.

ScrewMaker resolves a function name like "makeSlottedNut" to module
"FsFunctions.FSmakeSlottedNut". The actual implementation lives in
FSmakeCastleNut.py, so this module forwards the call.
"""

from FsFunctions.FSmakeCastleNut import makeSlottedNut  # re-export

