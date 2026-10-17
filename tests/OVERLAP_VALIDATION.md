# Overlap integration validation

Verified with Maya 2027's Python runtime on Windows, October 17, 2026.

`check_overlap_integration.py` creates a disposable installed layout, sources
the installer procedure declarations without running the full artist installer,
then executes the new Overlap MEL package-copy block against a temporary scripts
folder. It checks:

- `atk_overlap` installs with HTML help, icon, and licence.
- The toolbar registry resolves the installed package and includes Overlap once.
- Existing visibility controls hide and show it.
- The registered launcher creates the Overlap Qt window with File/Help menus.
- Source sampling, preview, optimized baking, and bake deletion work through that UI.
- The toolbar creates its Overlap button and clicking it dispatches the launcher.
- The icon has a generated fallback.
- Reload Scripts purges the whole isolated package; relaunch replaces only the
  ATK Overlap window, using its own window identity.

The workspaceControl show/visibility and Windows minimize watcher boundaries are
replaced by plain Qt behavior in this standalone check. Full interactive docking,
minimize placement, and the final drag-and-drop confirmation remain manual checks.
No artist scripts directory or production scene is installed or overwritten.

The complete Overlap 0.4.0 solver, UI, and guide came from the already tested
standalone build. The ATK bundle changes only its package/shelf import, window
identity, and stale-window replacement after module reload. Its separate licence
is retained; ATK's root licence does not replace it.

Run from the repository root:

```powershell
& 'C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe' tests/check_overlap_integration.py
```

The root and `dist` copies are synchronized using the existing release packager.
The resulting v1.1.7 ZIP is checked for the registry entry, bundled package,
offline guide, PNG, and licence, and for exclusion of Python bytecode caches.
