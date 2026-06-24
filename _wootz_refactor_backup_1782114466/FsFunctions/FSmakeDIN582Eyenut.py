# -*- coding: utf-8 -*-
"""Shim module: the ScrewMaker loader resolves a make function to the module
FsFunctions.FS<function_name>.  makeDIN582Eyenut is implemented alongside the
other eye fasteners in FSmakeEyebolt.py, so re-export it here."""
from FsFunctions.FSmakeEyebolt import makeDIN582Eyenut
