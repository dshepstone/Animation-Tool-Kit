"""
SavePlus Installer for Maya 2025
This file is executed when the install_saveplus.mel is dropped into Maya's viewport.
It handles copying files to Maya's script directory and creating a shelf button.
"""
import os
import sys
import shutil
import traceback

try:
    import maya.mel
    import maya.cmds
    isMaya = True
except ImportError:
    isMaya = False

def _onMayaDropped():
    """
    Function executed when the MEL script is dropped into Maya.
    This handles the installation of SavePlus files and creation of a shelf button.
    """
    try:
        # Show a confirmation dialog
        result = maya.cmds.confirmDialog(
            title="SavePlus Installation",
            message="This will install SavePlus to your Maya scripts directory and create a shelf button.\n\nWould you like to continue?",
            button=["Install", "Cancel"],
            defaultButton="Install",
            cancelButton="Cancel"
        )
        
        if result != "Install":
            print("SavePlus installation cancelled by user.")
            return
            
        # Get directories
        sourceDir = os.path.dirname(os.path.abspath(__file__))
        
        # Get Maya scripts directory
        scriptsDir = maya.cmds.internalVar(userScriptDir=True)

        # Get Maya icons directory via Maya's own variable so the path is always
        # correct regardless of drive letter, Documents location, or Maya version.
        # Fall back to deriving from scriptsDir if userPrefsDir returns empty
        # (observed in some Maya 2026 environments).
        prefsDir = maya.cmds.internalVar(userPrefsDir=True) or ""
        if not os.path.isabs(prefsDir):
            # scriptsDir is <maya_user>/<version>/scripts/ – sibling is prefs/
            prefsDir = os.path.join(os.path.dirname(scriptsDir.rstrip("/\\")), "prefs")
        iconsDir = os.path.join(prefsDir, "icons")
        
        # Create icons directory if it doesn't exist
        if not os.path.exists(iconsDir):
            os.makedirs(iconsDir)
        
        print("Source directory: " + sourceDir)
        print("Scripts directory: " + scriptsDir)
        print("Icons directory: " + iconsDir)
        
        # Files to copy
        filesToCopy = [
            "__init__.py",
            "savePlus_core.py",
            "savePlus_maya.py",
            "savePlus_ui_components.py",
            "savePlus_main.py",
            "savePlus_launcher.py"
        ]
        
        # Copy each file to the scripts directory
        for fileName in filesToCopy:
            sourcePath = os.path.join(sourceDir, fileName)
            destPath = os.path.join(scriptsDir, fileName)
            
            if not os.path.exists(sourcePath):
                raise FileNotFoundError(
                    f"Missing installer source file: {fileName}. "
                    f"Expected at: {sourcePath}"
                )

            shutil.copy2(sourcePath, destPath)
            print(f"Copied {fileName} to {destPath}")
        
        # Look for the icon file in various locations
        iconFound = False
        iconDestPath = os.path.join(iconsDir, "saveplus.png")
        
        iconLocations = [
            os.path.join(sourceDir, "icons", "saveplus.png"),
            os.path.join(sourceDir, "saveplus.png"),
            os.path.join(sourceDir, "icon", "saveplus.png")
        ]
        
        for iconPath in iconLocations:
            if os.path.exists(iconPath):
                shutil.copy2(iconPath, iconDestPath)
                print(f"Copied icon from {iconPath} to {iconsDir}")
                iconFound = True
                break
                
        # Set the icon path for the shelf button
        if iconFound:
            iconPath = "saveplus.png"
        else:
            print("Warning: SavePlus icon not found. Using Maya's default icon.")
            iconPath = "incrementalSave.png"
        
        # Create the shelf button command
        command = '''
# -----------------------------------
# SavePlus
# -----------------------------------

import importlib
import sys
import maya.cmds as cmds

# Ensure the scripts directory is in the Python path
scriptsDir = cmds.internalVar(userScriptDir=True)
if scriptsDir not in sys.path:
    sys.path.insert(0, scriptsDir)

# Reload all SavePlus modules so any file updates take effect
# without needing to restart Maya.
for _mod in ['savePlus_maya', 'savePlus_core', 'savePlus_ui_components',
             'savePlus_main', 'savePlus_launcher']:
    if _mod in sys.modules:
        try:
            importlib.reload(sys.modules[_mod])
        except Exception as _e:
            print(f"SavePlus: warning reloading {_mod}: {_e}")

try:
    import savePlus_launcher
    savePlus_launcher.launch_save_plus()
except Exception as e:
    cmds.warning(f"Error launching SavePlus: {str(e)}")
    raise
'''

        # Unique identifier embedded in the annotation so both the installer
        # and savePlus_launcher can find the button without creating duplicates.
        UNIQUE_IDENTIFIER = "SavePlus_v1_ToolButton"

        # Get the current shelf
        shelf = maya.mel.eval('$gShelfTopLevel=$gShelfTopLevel')
        parent = maya.cmds.tabLayout(shelf, query=True, selectTab=True)

        # Check for an existing SavePlus shelf button and update it rather
        # than adding a duplicate to the shelf.
        existing_button = None
        if maya.cmds.shelfLayout(parent, exists=True):
            shelf_buttons = maya.cmds.shelfLayout(parent, query=True, childArray=True) or []
            for btn in shelf_buttons:
                if maya.cmds.shelfButton(btn, exists=True):
                    try:
                        annotation = maya.cmds.shelfButton(btn, query=True, annotation=True) or ""
                        if UNIQUE_IDENTIFIER in annotation:
                            existing_button = btn
                            break
                    except Exception:
                        pass

        if existing_button:
            maya.cmds.shelfButton(
                existing_button,
                edit=True,
                command=command,
                image=iconPath,
                image1=iconPath,
                sourceType='Python',
            )
            print("SavePlus shelf button updated successfully.")
        else:
            maya.cmds.shelfButton(
                command=command,
                annotation=f'SavePlus - Intelligent File Versioning Tool [{UNIQUE_IDENTIFIER}]',
                sourceType='Python',
                image=iconPath,
                image1=iconPath,
                label='SavePlus',
                parent=parent,
            )
            print("SavePlus shelf button created successfully.")
        
        # Verify the installation
        installSuccess = True
        missingFiles = []
        
        for fileName in filesToCopy:
            filePath = os.path.join(scriptsDir, fileName)
            if not os.path.exists(filePath):
                installSuccess = False
                missingFiles.append(fileName)
        
        if not installSuccess:
            errorMsg = f"Some files were not installed correctly: {', '.join(missingFiles)}"
            print(errorMsg)
            maya.cmds.confirmDialog(
                title="SavePlus Installation Warning",
                message=errorMsg,
                button=["OK"],
                defaultButton="OK"
            )
        else:
            # Installation successful
            successMsg = "SavePlus has been successfully installed!\n\nA shelf button has been created or updated on your current shelf."
            
            # Ask if user wants to launch SavePlus now
            result = maya.cmds.confirmDialog(
                title="SavePlus Installation",
                message=successMsg + "\n\nWould you like to launch SavePlus now?",
                button=["Yes", "No"],
                defaultButton="Yes",
                cancelButton="No"
            )
            
            if result == "Yes":
                # Launch SavePlus
                try:
                    # Add scripts directory to path if not already there
                    if scriptsDir not in sys.path:
                        sys.path.append(scriptsDir)
                        
                    # Import and launch
                    import savePlus_launcher
                    savePlus_launcher.launch_save_plus()
                    
                    print("SavePlus launched successfully.")
                except Exception as e:
                    errorMsg = f"Error launching SavePlus: {str(e)}"
                    print(errorMsg)
                    maya.cmds.confirmDialog(
                        title="SavePlus Launch Error",
                        message=errorMsg,
                        button=["OK"],
                        defaultButton="OK"
                    )
            
            print("SavePlus installation completed successfully!")
            
    except Exception as e:
        errorMsg = f"Error during SavePlus installation: {str(e)}"
        print(errorMsg)
        traceback.print_exc()
        
        if isMaya:
            maya.cmds.confirmDialog(
                title="SavePlus Installation Error",
                message=errorMsg + "\n\nPlease check the Script Editor for details.",
                button=["OK"],
                defaultButton="OK"
            )

# Execute when dropped into Maya
if isMaya:
    _onMayaDropped()
