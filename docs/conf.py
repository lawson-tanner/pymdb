"""Sphinx configuration for pymdb."""
from __future__ import annotations

import os
import sys

# -- Path setup --------------------------------------------------------------
# Not strictly required when pymdb is installed into the docs build
# environment (see docs/requirements.txt / pyproject.toml [docs] extra), but
# kept as a fallback so `sphinx-build` also works against a checkout where
# only the source tree, and not the package, has been installed.
sys.path.insert(0, os.path.abspath("../src"))

import mdb  # noqa: E402

# -- Project information ------------------------------------------------------
project = "pymdb"
copyright = "2026, Lawson Tanner"
author = "Lawson Tanner"
release = mdb.__version__
version = release

# -- General configuration ----------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# autodoc/autosummary ---------------------------------------------------------
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autoclass_content = "class"
autosummary_generate = True
add_module_names = False

# napoleon is enabled for the rare Google/NumPy-style docstring that creeps
# in; pymdb's own docstrings are plain reST, which napoleon passes through
# unchanged.
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_use_param = True
napoleon_use_rtype = True

# intersphinx -------------------------------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Options for HTML output --------------------------------------------------
html_theme = "furo"
html_static_path = ["_static"]
html_title = f"pymdb {release}"

html_theme_options = {
    "source_repository": "https://github.com/lawson-tanner/pymdb/",
    "source_branch": "main",
    "source_directory": "docs/",
}

# Rendered doctest-style examples (README quick start, module docstrings) are
# illustrative, not executed; nothing here runs them, so there is no exec
# state to configure.
