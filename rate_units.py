# units.py
import re
from typing import Tuple, Optional

# Keep keys lowercase and minimal (family+number)
UNIT_MAP = {
    "s21": "TH/s",
    "l7":  "GH/s",
    "l9":  "GH/s",
    "s19": "TH/s",
    "s9":  "TH/s",
    "t17": "TH/s",
    "t19": "TH/s",
    "s17": "TH/s",
    "s17e":"TH/s",
    "s17pro":"TH/s",
    "s9k": "TH/s",
    "s9se":"TH/s",
}

_MODEL_KEY_RE = re.compile(r"([a-z])\s*-?\s*(\d+)", re.I)

def model_key(model: Optional[str]) -> Optional[str]:
    """
    Normalize a model string ('Antminer L9', 'L9', 'S19j Pro', 's19j-pro') -> 'l9'/'s19'
    """
    if not model:
        return None
    m = _MODEL_KEY_RE.search(model)
    if not m:
        return model.lower().strip()
    fam, num = m.groups()
    return f"{fam.lower()}{num}"

def preferred_unit_for_model(model: Optional[str]) -> str:
    key = model_key(model)
    return UNIT_MAP.get(key or "", "GH/s")  # default to GH/s if unknown

def convert_from_ghs(value_ghs: Optional[float], model: Optional[str]) -> Tuple[Optional[float], str]:
    """
    Input is GH/s (what many stats fields use). Output is (value_in_preferred_unit, unit_str).
    """
    if model_key(model) == "l7" and value_ghs >1000:
        value_ghs = value_ghs / 1000.0  # L7 is usually in TH/s

    if value_ghs is None:
        return None, preferred_unit_for_model(model)
    unit = preferred_unit_for_model(model)
    if unit == "TH/s":
        return value_ghs / 1000.0, unit
    if unit == "GH/s":
        return value_ghs, unit
    if unit == "MH/s":
        return value_ghs * 1000.0, unit
    # fallback: unknown unit, keep GH/s
    return value_ghs, "GH/s"
