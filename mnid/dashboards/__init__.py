"""
Sub-package for new dashboards built on top of the MNID component layer.

Each module here should be self-contained — import from mnid.core, mnid.charts,
mnid.components, and mnid.aggregation, then return an html.Div from its render
function. Register a page in pages/ and add a nav link in helpers/navigation_callbacks.py.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=8)
def load_dashboard_module(folder_name: str):
    """Load a dashboard package by folder name, including hyphenated directories."""
    package_root = Path(__file__).resolve().parent / folder_name
    init_path = package_root / '__init__.py'
    if not init_path.exists():
        raise ModuleNotFoundError(f'Dashboard package not found: {folder_name}')

    safe_name = folder_name.replace('-', '_')
    module_name = f'mnid.dashboards.dynamic_{safe_name}'
    spec = importlib.util.spec_from_file_location(
        module_name,
        init_path,
        submodule_search_locations=[str(package_root)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f'Unable to load dashboard module: {folder_name}')

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
