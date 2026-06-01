# -*- coding: utf-8 -*-
"""
Loader shim for the PEM Blind Threaded standoff (BSO/BSOS/BSOA/BSO4).

The screw factory resolves a make function by importing the module
``FsFunctions.FS<function>``.  The actual implementation of
``makePEMBlindStandoff`` lives together with the other PEM standoff code in
``FSmakePEMStandoff.py``; this module simply re-exports it so the dynamic
dispatch in ``Screw.createScrew`` can find it.
"""
from FsFunctions.FSmakePEMStandoff import makePEMBlindStandoff

__all__ = ["makePEMBlindStandoff"]
