# -*- coding: utf-8 -*-
"""
Shim so the ScrewMaker module-resolution logic
("FsFunctions.FS" + function_name) can find makeISO3266Eyebolt.

The actual implementation lives in FSmakeEyebolt.py.
"""
from FsFunctions.FSmakeEyebolt import makeISO3266Eyebolt  # noqa: F401
