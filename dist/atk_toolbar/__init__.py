"""Animation Tool Kit Toolbar — package init.

Public API
----------
    import atk_toolbar
    atk_toolbar.show()    # open / restore the toolbar
    atk_toolbar.close()   # hide the toolbar
    atk_toolbar.toggle()  # show when hidden, hide when shown (shelf button)
"""

__version__ = "1.0.0"
__author__  = "Animation Tool Kit"

from .atk_toolbar import show, close, toggle, is_visible, _rebuild_ui  # noqa: F401
