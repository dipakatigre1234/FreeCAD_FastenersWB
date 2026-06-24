# -*- coding: utf-8 -*-
"""
Shim so the ScrewMaker module-resolution logic
("FsFunctions.FS" + function_name) can find makeEyeboltShoulder.

The actual implementation lives in FSmakeEyebolt.py.
"""
from FsFunctions.FSmakeEyebolt import makeEyeboltShoulder  # noqa: F401
