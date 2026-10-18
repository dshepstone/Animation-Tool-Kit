# Animation Tool Kit 1.1.9 — Updated ATK toolbar logo

The ATK website button beside the settings gear now uses the supplied
**ATK_Logo.png** artwork. Clicking the button opens **https://shepstone.ca/**
in both horizontal and vertical toolbar layouts.

The new icon ships in the toolbar package and is copied into Maya's icon folder
by the installer. The release ZIP contains the updated installer, icon loader,
and an exact copy of the new artwork.

This release also includes all **Playblast Creator 2.0.5** fixes from ATK 1.1.8:

- Software H.264 fallback when NVIDIA NVENC or Apple VideoToolbox encoding fails,
  provided the configured FFmpeg includes libx264.
- Existing videos protected on failed exports, with an explicit **Output →
  Destination → Force overwrite existing output** checkbox.
- Improved temporary capture handling, incomplete-frame validation, audio offsets,
  portable paths, odd image dimensions, viewport restoration, and error reporting.

## Install/update

Download and extract `AnimationToolKit_v1_1_9.zip`, then drag
`install_atk_toolbar.mel` into Maya. Restart Maya after updating so the toolbar,
icon loader, and Playblast Creator plug-in all use the installed code.

## Verification

The release pipeline runs the 38-test playblast suite and packaging checks on
Windows, macOS, and Linux before publication. The packager verifies ZIP integrity
and compares all packaged file contents against the source tree. The icon asset,
installer references, source/dist copies, and unchanged website click handler
were checked directly.

Actual Maya viewport capture and physical GPU behavior still require workstation
smoke testing; see `tests/PLAYBLAST_VALIDATION.md` in the repository for details.
