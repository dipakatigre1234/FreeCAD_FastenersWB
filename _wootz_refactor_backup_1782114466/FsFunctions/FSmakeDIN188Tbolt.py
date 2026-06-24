# -*- coding: utf-8 -*-
"""Shim module: the ScrewMaker loader resolves a make function to the module
FsFunctions.FS<function_name>.  makeDIN188Tbolt is implemented alongside the
DIN 186 T-bolt in FSmakeTbolt.py, so re-export it here."""
from FsFunctions.FSmakeTbolt import makeDIN188Tbolt
