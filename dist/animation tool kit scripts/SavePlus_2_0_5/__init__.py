"""
SavePlus - File versioning tool for Maya 2025
Package initialization file
"""

__version__ = "2.0.4"
__author__ = "Original MEL script by Neal Singleton, Python port by SavePlus Team"

# Import key modules
import savePlus_core
import savePlus_ui_components
import savePlus_main
import savePlus_launcher
# Set version in all modules
VERSION = __version__

# Convenience function to launch the tool
def launch():
    """Launch the SavePlus tool"""
    return savePlus_launcher.launch_save_plus()
