"""Animation Tool Kit Toolbar — package init.

Public API
----------
    import atk_toolbar
    atk_toolbar.show()    # open / restore the toolbar
    atk_toolbar.close()   # hide the toolbar
"""

__version__ = "1.0.0"
__author__  = "Animation Tool Kit"

from .atk_toolbar import show, close, is_visible, _rebuild_ui  # noqa: F401
