# -*- coding: utf-8 -*-
"""
Shim so the ScrewMaker module-resolution logic
("FsFunctions.FS" + function_name) can find makeDIN580Eyebolt.

The actual implementation lives in FSmakeEyebolt.py.
"""
from FsFunctions.FSmakeEyebolt import makeDIN580Eyebolt  # noqa: F401
