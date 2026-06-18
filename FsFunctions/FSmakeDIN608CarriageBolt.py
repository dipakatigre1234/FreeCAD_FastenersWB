# -*- coding: utf-8 -*-
"""Shim module: the ScrewMaker loader resolves a make function to the module
FsFunctions.FS<function_name>.  makeDIN608CarriageBolt is implemented alongside
the other carriage bolts in FSmakeCarriageBolt.py, so re-export it here."""
from FsFunctions.FSmakeCarriageBolt import makeDIN608CarriageBolt
