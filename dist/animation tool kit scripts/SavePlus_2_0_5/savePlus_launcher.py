"""
SavePlus Launcher - Main entry point for the SavePlus tool

This script launches the SavePlus tool for Maya 2025, handling imports
and initialization of the modular SavePlus components.

To use:
1. Place all SavePlus scripts in Maya's scripts directory
2. Run this script from Maya's Script Editor
3. Create a shelf button with this command:
   import savePlus_launcher; savePlus_launcher.launch_save_plus()
"""

import os
import sys
import traceback
import shutil
from savePlus_maya import cmds, mel

# Version for this launcher
VERSION = "2.0.4"

def setup_import_paths():
    """Setup import paths for SavePlus modules"""
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Add to Python path if not already included
    if script_dir not in sys.path:
        sys.path.append(script_dir)

def import_modules():
    """Import SavePlus modules"""
    try:
        # Ensure the script directory is in the Python path
        setup_import_paths()
        
        # Try to import modules
        import savePlus_core
        import savePlus_ui_components
        import savePlus_main
        return savePlus_core, savePlus_ui_components, savePlus_main
    except ImportError as e:
        print(f"Error importing modules: {e}")
        traceback.print_exc()
        
        # Try an alternative approach
        try:
            # Custom import approach
            print("Trying alternative import method...")
            setup_import_paths()
            
            # Use __import__ with more specific error handling
            core_module = __import__("savePlus_core")
            ui_module = __import__("savePlus_ui_components")
            
            # Patch the ui_components module to use the core module directly
            ui_module.savePlus_core = core_module
            
            # Now import the main module
            main_module = __import__("savePlus_main")
            
            # Patch the main module to use the core and ui modules directly
            main_module.savePlus_core = core_module
            main_module.savePlus_ui_components = ui_module
            
            return core_module, ui_module, main_module
        except Exception as e2:
            print(f"Alternative import also failed: {e2}")
            traceback.print_exc()
            raise

def launch_save_plus():
    """Launch the SavePlus UI"""
    try:
        print("="*50)
        print(f"Starting SavePlus v{VERSION}...")
        
        # Import the modules
        core, ui, main = import_modules()
        
        # Check for existing UI window or workspace control
        for obj in cmds.lsUI(windows=True):
            if obj.startswith('SavePlusUI'):
                print(f"Closing existing SavePlus window: {obj}")
                cmds.deleteUI(obj)

        # Also close any existing docked workspace control
        workspace_control = 'SavePlusUIWorkspaceControl'
        if cmds.workspaceControl(workspace_control, exists=True):
            print(f"Closing existing SavePlus workspace control: {workspace_control}")
            cmds.deleteUI(workspace_control)

        # Create and show the UI as a floating dockable window
        save_plus_ui = main.SavePlusUI()
        save_plus_ui.show(dockable=True, floating=True)
        
        # Return the UI instance to avoid garbage collection
        print(f"SavePlus v{core.VERSION} loaded successfully!")
        print("="*50)
        return save_plus_ui
        
    except Exception as e:
        error_message = f"Error loading SavePlus: {str(e)}"
        print(error_message)
        traceback.print_exc()
        cmds.confirmDialog(
            title="SavePlus Error", 
            message=f"Error loading SavePlus: {str(e)}\n\nCheck script editor for details.", 
            button=["OK"], 
            defaultButton="OK"
        )
        return None

def quick_install():
    """
    Quick install function for SavePlus.
    Copies files to Maya scripts directory and creates a shelf button.
    
    Returns:
        bool: True if installation was successful, False otherwise
    """
    try:
        # Get Maya scripts directory
        maya_script_dir = cmds.internalVar(userScriptDir=True)
        
        # Get Maya icons directory (for shelf button icons)
        maya_icons_dir = os.path.join(os.path.dirname(os.path.dirname(maya_script_dir)), "prefs", "icons")
        if not os.path.exists(maya_icons_dir):
            try:
                os.makedirs(maya_icons_dir)
                print(f"Created Maya icons directory: {maya_icons_dir}")
            except Exception as e:
                print(f"Warning: Could not create Maya icons directory: {e}")
        
        # Get the directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Files to copy to scripts directory
        files_to_copy = [
            "__init__.py",
            "savePlus_core.py",
            "savePlus_ui_components.py",
            "savePlus_main.py",
            "savePlus_launcher.py"
        ]
        
        # Copy script files
        for file_name in files_to_copy:
            source_file = os.path.join(current_dir, file_name)
            dest_file = os.path.join(maya_script_dir, file_name)
            
            if os.path.exists(source_file):
                # Create directory if it doesn't exist
                if not os.path.exists(os.path.dirname(dest_file)):
                    os.makedirs(os.path.dirname(dest_file))
                
                # Copy the file
                shutil.copy2(source_file, dest_file)
                print(f"Copied {file_name} to {maya_script_dir}")
            else:
                print(f"Warning: Could not find {source_file}")
        
        # Handle icon file separately - check if it exists in various locations
        icon_sources = [
            os.path.join(current_dir, "icons", "saveplus.png"),
            os.path.join(current_dir, "saveplus.png"),
            os.path.join(current_dir, "icon", "saveplus.png")
        ]
        
        icon_found = False
        icon_dest_path = os.path.join(maya_icons_dir, "saveplus.png")
        
        for icon_source in icon_sources:
            if os.path.exists(icon_source):
                # Copy icon to Maya's icons directory
                shutil.copy2(icon_source, icon_dest_path)
                print(f"Copied icon from {icon_source} to {maya_icons_dir}")
                icon_found = True
                break
        
        if not icon_found:
            print("Warning: SavePlus icon not found. The shelf button will use Maya's default icon.")
        
        # Create shelf button
        result = install_shelf_button(maya_icons_dir)
        
        if result:
            print("Shelf button created successfully")
        else:
            print("Failed to create shelf button")
            
        return True
    except Exception as e:
        print(f"Error during installation: {str(e)}")
        traceback.print_exc()
        return False

# Create a shelf button installation function
def install_shelf_button(maya_icons_dir=None):
    """Install SavePlus buttons on the current Maya shelf"""
    try:
        # Get the active shelf
        top_shelf = mel.eval('$gShelfTopLevel=$gShelfTopLevel')
        current_shelf = cmds.tabLayout(top_shelf, query=True, selectTab=True)
        
        # Unique identifier for the button
        UNIQUE_IDENTIFIER = "SavePlus_v1_ToolButton"
        
        # Check for existing button
        existing_button = None
        if cmds.shelfLayout(current_shelf, exists=True):
            shelf_buttons = cmds.shelfLayout(current_shelf, query=True, childArray=True) or []
            for btn in shelf_buttons:
                if cmds.shelfButton(btn, exists=True):
                    try:
                        annotation = cmds.shelfButton(btn, query=True, annotation=True)
                        if UNIQUE_IDENTIFIER in annotation:
                            existing_button = btn
                    except:
                        pass
        
        # Command for the shelf button — reloads all modules so file updates
        # take effect without restarting Maya.
        button_command = """
import importlib
import sys
import maya.cmds as cmds

scriptsDir = cmds.internalVar(userScriptDir=True)
if scriptsDir not in sys.path:
    sys.path.insert(0, scriptsDir)

for _mod in ['savePlus_maya', 'savePlus_core', 'savePlus_ui_components',
             'savePlus_main', 'savePlus_launcher']:
    if _mod in sys.modules:
        try:
            importlib.reload(sys.modules[_mod])
        except Exception as _e:
            print(f"SavePlus: warning reloading {_mod}: {_e}")

import savePlus_launcher
savePlus_launcher.launch_save_plus()
"""
        
        # Get path to custom icon in Maya's icons directory
        if maya_icons_dir is None:
            # Get Maya icons directory if not provided
            script_dir = cmds.internalVar(userScriptDir=True)
            maya_icons_dir = os.path.join(os.path.dirname(os.path.dirname(script_dir)), "prefs", "icons")
        
        icon_path = os.path.join(maya_icons_dir, "saveplus.png")
        
        # Use custom icon if available, otherwise use Maya's default
        if not os.path.exists(icon_path):
            icon_path = 'incrementalSave.png'  # Fallback to Maya's icon
        else:
            # Use just the filename for Maya shelf buttons, not the full path
            icon_path = "saveplus.png"
        
        shelf_annotation = f'SavePlus - Intelligent File Versioning Tool [{UNIQUE_IDENTIFIER}]'

        # Create or update button
        if existing_button:
            cmds.shelfButton(existing_button, edit=True,
                             command=button_command,
                             image=icon_path,
                             image1=icon_path,
                             annotation=shelf_annotation,
                             sourceType='python')
            print(f"Updated existing SavePlus shelf button with icon: {icon_path}")
        else:
            cmds.shelfButton(
                label='SavePlus',
                annotation=shelf_annotation,
                image=icon_path,
                image1=icon_path,
                command=button_command,
                sourceType='python',
                parent=current_shelf)
            print(f"SavePlus shelf button created with icon: {icon_path}")
        
        return True
    except Exception as e:
        print(f"Error installing shelf button: {e}")
        traceback.print_exc()
        return False

# Only create the UI if this script is run directly
if __name__ == "__main__":
    # Store the UI instance in a global variable to prevent garbage collection
    global saveplus_ui_instance
    saveplus_ui_instance = launch_save_plus()
