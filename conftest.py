"""Test bootstrap.

The package ``__init__`` imports Home Assistant, which isn't available in a
lightweight unit-test environment. ``gesture`` and ``const`` are deliberately
HA-free, so we load them under a synthetic ``button_actions`` package that skips
the real ``__init__`` while still supporting their relative imports.

``schema`` is HA-coupled only at the edges: it builds a voluptuous schema from
``homeassistant.helpers.config_validation`` validators at import time, but its
title helpers are pure string logic. We stub those two deps just enough for the
module to import so ``mapping_title`` can be unit-tested without HA installed.
"""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(__file__)
_BASE = os.path.join(ROOT, "custom_components", "button_actions")
_PKG = "button_actions"


def _stub_schema_deps() -> None:
    """Register minimal fakes for voluptuous and HA's config_validation."""
    if "voluptuous" not in sys.modules:
        vol = types.ModuleType("voluptuous")

        class _Marker:
            """Hashable stand-in for vol.Optional/Required schema keys."""

            def __init__(self, key, **_kw):
                self.key = key

            def __hash__(self):
                return hash(self.key)

            def __eq__(self, other):
                return isinstance(other, _Marker) and other.key == self.key

        vol.Optional = _Marker
        vol.Required = _Marker
        vol.In = lambda *a, **k: object()
        vol.Schema = lambda *a, **k: object()

        class Invalid(Exception):
            pass

        vol.Invalid = Invalid
        sys.modules["voluptuous"] = vol

    if "homeassistant" not in sys.modules:
        ha = types.ModuleType("homeassistant")
        helpers = types.ModuleType("homeassistant.helpers")
        cv = types.ModuleType("homeassistant.helpers.config_validation")
        for _attr in ("string", "entity_id", "positive_int", "boolean", "SCRIPT_SCHEMA"):
            setattr(cv, _attr, object())
        helpers.config_validation = cv
        ha.helpers = helpers
        sys.modules["homeassistant"] = ha
        sys.modules["homeassistant.helpers"] = helpers
        sys.modules["homeassistant.helpers.config_validation"] = cv


if _PKG not in sys.modules:
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [_BASE]
    sys.modules[_PKG] = pkg

    _stub_schema_deps()

    for _name in ("const", "gesture", "schema"):
        _spec = importlib.util.spec_from_file_location(
            f"{_PKG}.{_name}", os.path.join(_BASE, f"{_name}.py")
        )
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[f"{_PKG}.{_name}"] = _mod
        _spec.loader.exec_module(_mod)
