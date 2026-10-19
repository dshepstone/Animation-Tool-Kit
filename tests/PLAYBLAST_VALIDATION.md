# Playblast Creator verification

Run from the repository root using Python 3.9+:

```
python -m pip install PySide6
python -m unittest discover -s tests -p "test_playblast*.py" -v
python -m compileall -q "animation tool kit scripts/Playblast_Creator" atk_toolbar
python package_atk_release.py --version 1.1.12
```

FFmpeg and ffprobe must be on PATH for the media integration tests. CI asserts
these prerequisites and Qt are installed so those tests cannot silently skip.
The suite imports real production classes through AST extraction to avoid Maya
imports. It does not substitute a separate implementation of the export logic.
Qt-specific tests use real PySide6/QProcess; Maya capture calls are mocked.

## Automated coverage

- NVIDIA API mismatch and Apple hardware failure: deterministic injected failure,
  then real or mocked software fallback; encoder-specific flags removed correctly.
- FFmpeg startup failure, nonzero exit, crash status, invalid diagnostic bytes,
  and successful process completion. Real Qt process success and failure.
- Failed/empty output rejected; existing output preserved; opt-in successful
  overwrite; exclusive publication rejects a file created during export;
  locked/permission-denied destinations; staging cleanup.
- Windows/macOS/Linux codec selection, executable paths with spaces and quotes,
  Unix execute permissions, per-binary encoder cache, timeout process cleanup.
- Explicit viewport targeting, restoration after capture failure, cancellation,
  incomplete captures, isolated recovery directories, Linux PNG intermediate,
  image return value, invalid filenames/ranges, and named/fractional frame rates.
- Real H.264 MP4/MOV, MPEG-4 MP4/MOV, and ProRes MOV: ffprobe checks codec,
  frame count, frame rate, and padded odd dimensions. Timeline audio before,
  at, and after capture start (including decoded silence verification).
- Real movie transcode with optional absent audio and missing-input failure.
- Real Qt Output tab: overwrite checkbox visible below filename and initially off.
- Shot-mask missing texture/renderer diagnostics and release on drawing errors.
- ZIP CRC and every packaged file compared to canonical source; portable paths.

## Workstation smoke tests still required

No Maya installation or physical NVIDIA/Apple GPU is available in the cloud
runner. Do not equate these tests with an end-to-end Maya certification.

On Windows, Linux and macOS with supported Maya versions:

1. Install from the release ZIP and restart Maya. Open Playblast Creator from ATK.
2. Create an animated cube, camera and timeline sound. Export PNG and H.264 MP4;
   check framing, shot mask, inclusive frame range, audio sync and viewer launch.
3. Export again to the same path with overwrite off; confirm guidance names
   Output > Destination > Force overwrite existing output. Enable it and repeat.
4. Repeat with a namespaced camera and a different focused viewport. Confirm
   camera, current frame, visibility and overscan restore after success/failure.
5. Test an older NVIDIA driver or unavailable GPU. Confirm warning and software
   retry; play the completed output. Test without libx264 and confirm a clear error.
6. Test macOS VideoToolbox, native movie intermediates on Windows/macOS, a locked
   output, unwritable destination and low disk space. Existing videos must survive.
7. Cancel capture and test malformed/missing logo images. Check recovery logging,
   no false success, and shot-mask drawing in the actual viewport.
8. Test unusually high resolution, offscreen capture and a representative heavy
   production scene. Maya can clamp capture resolution to viewport limits.

Native Trax mixing remains Maya-dependent: use a native movie intermediate on
Windows/macOS when required. Image-sequence audio uses the active timeline sound
node; multiple Trax clips are not mixed by FFmpeg in this tool.
