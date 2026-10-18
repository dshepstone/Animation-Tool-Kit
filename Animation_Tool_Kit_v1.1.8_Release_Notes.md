# Animation Tool Kit 1.1.8 — Playblast reliability

Includes Playblast Creator **2.0.5**. Other bundled tools retain their versions.

## Fixes

- Failed NVIDIA NVENC and Apple VideoToolbox H.264 encodes automatically retry
  with CPU libx264 when the configured FFmpeg includes it. An NVENC API/driver
  mismatch no longer requires a driver upgrade to export using software.
- Checks process startup, exit status, and nonempty output before reporting success.
- Encodes to a private staging file before publishing. Existing videos survive
  failed encoding; overwrite must be explicitly enabled. Locked destinations
  produce an actionable error rather than a false success.
- Each capture owns a unique temporary folder. Failed captures/encodes retain
  their frames for recovery and report the location. Successful exports clean up.
- Rejects incomplete intermediate frame sequences instead of exporting a truncated video.
- Explicitly targets the selected Maya viewport and restores its camera,
  visibility, overscan, and current frame after capture failures.
- Linux uses PNG intermediates when an older saved preference requests native
  movie capture. Portable filename validation and executable permission checks
  prevent common Windows/macOS/Linux path failures.
- Pads odd dimensions to even dimensions for H.264/MPEG-4/ProRes compatibility.
- Timeline audio beginning after the capture start receives silence padding;
  earlier audio is trimmed. Audio is encoded explicitly to AAC.
- Encoder discovery is cached per executable and reaps timed-out probe processes.
- Fixes the missing-logo error path and releases shot-mask image textures.

## Interface

The **Output** tab's **Destination** card has a separate, clearly labelled
**Force overwrite existing output** checkbox, followed by replacement guidance.
It is unchecked by default. Existing-file errors name the location of this control.
H.264 labels explain automatic hardware/software fallback. Inputs and export
buttons are disabled during capture/encoding to prevent overlapping jobs.
Failed previews no longer announce success. Names containing dots are preserved.

## Install/update

Extract `AnimationToolKit_v1_1_8.zip`, then drag `install_atk_toolbar.mel` into Maya.
**Restart Maya after updating** to ensure both the Python UI and loaded shot-mask
plug-in use the new code. The historical `PBC_v2_0_4` installation directory and
standalone installer filenames are intentionally retained for existing shelf and
loader compatibility; the bundled code version is 2.0.5.

Set **Settings → FFmpeg** to `ffmpeg.exe` on Windows or the executable `ffmpeg`
on macOS/Linux. For reliable H.264 fallback use a build containing **libx264**.
No FFmpeg binary or NVIDIA driver is bundled. PNG image exports do not need FFmpeg.
The custom `{playblast_creator_projects}` preset now resolves under the user's
home directory on every platform instead of a hard-coded C: drive.

## Verification and limits

Automated tests exercise real FFmpeg encodes and ffprobe inspection for H.264,
MPEG-4 and ProRes; frame counts, dimensions, frame rate and audio; failure recovery;
overwrite races; paths; cancelled/incomplete mocked Maya captures; and real Qt
process status and the Output layout. CI runs on Windows, macOS, and Linux.

Maya capture is mocked in cloud tests. Actual Maya viewport capture, shot-mask
GPU drawing, native movie codecs, physical NVIDIA/Apple acceleration, and all
Maya/driver combinations require workstation smoke testing. Hardware-failure
fallback is tested by injecting failure and performing a real software encode.
See `tests/PLAYBLAST_VALIDATION.md` for reproducible checks and this distinction.
