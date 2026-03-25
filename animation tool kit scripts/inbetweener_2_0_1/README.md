# inbeTweener

A high-performance tweening utility for Maya animators to break down poses and manage arcs.

![Version](https://img.shields.io/badge/Version-2.1.0-orange)
![Maya Version](https://img.shields.io/badge/Maya-2018--2025-blue)
![Python](https://img.shields.io/badge/Python-2.7%20%7C%203.x-green)
![Qt](https://img.shields.io/badge/Qt-PySide2%20%7C%20PySide6-purple)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Overview

**Vertex Tweener** is a professional-grade animation tool for Autodesk Maya that enables animators to efficiently break down poses between keyframes with precision and control. Whether you're creating subtle in-betweens or dramatic overshoot/anticipation effects, Vertex Tweener provides an intuitive interface for crafting perfect motion arcs.

### Key Features

- **🎯 Drag & Drop Install** - No manual path setup required. Simply drag the MEL file into Maya and you're ready to go.

- **📊 Local Tweener (LT)** - Precision breakdown between keyframes at current time using formula `Result = Value_A + (Value_B - Value_A) × (Bias/100)`.

- **🌍 World Tweener (WT)** - Blend in world space using matrix interpolation (no viewport flicker), perfect for maintaining global position.

- **↔️ Blend to Neighbor (BN)** - Adjust selected controls toward previous/next keyframe neighbors for quick refinements.

- **🔄 Blend to Default (BD)** - Slide between original keyframe values and rest pose. Uses scanned default pose values when available, with intelligent fallback for scale/visibility attributes. Preserves original on press, resets on release.

- **📈 Blend to Ease (BE)** - Create professional easing with cubic curves for smooth ease-in/ease-out motion on selected controls.

- **🚀 Overshoot/Anticipation** - Local Tweener extends from -50% to 150% for exaggerated motion and dynamic poses.

- **🔄 Auto-Key Mode** - Automatically commit changes to the timeline when enabled, or preview changes interactively when disabled.

- **👁️ Motion Trails** - Real-time visual feedback showing motion arcs to help you visualize and perfect your animation paths.

- **⚡ Single Undo Action** - Each slider drag is grouped into one undo chunk for efficient workflow management.

- **💾 Preference Persistence** - Remembers your last settings (Auto-key state, slider position, motion trails, overshoot mode) between sessions.

- **🎨 Quick-Snap Buttons** - Instant access to common breakdown values: 1/8, 1/4, 1/2, 3/4, 7/8, plus 0, 1/3, 2/3, and 1.

- **🔧 Smart Attribute Handling** - Automatically processes all keyable attributes on selected objects while respecting locks and connections.

- **📸 Scan Default Pose** - Store your rig's rest/bind pose on a network node for accurate Blend-to-Default results. Uses multi-level fallback: scanned values → Maya's attributeQuery → intelligent heuristics.

- **⚡ Cached Performance** - Keyframe values are cached on slider press for fast, responsive drags with no Maya API queries during interaction.

## Installation

### Getting Started

1. **Download** the `install_Tweener.mel` file from the `dist/` folder in this repository.

2. **Drag and Drop** the MEL file directly into your Maya viewport.

3. **Confirm Installation** when prompted to create a shelf button (recommended).

That's it! The tool is now installed and ready to use.

> 💡 **Tip:** For detailed installation instructions and comprehensive usage guide, see the [dist/README.md](dist/README.md) file.

### What Happens During Installation?

The installer automatically:

- Extracts the Python code from the MEL file
- Installs `vertex_tweener.py` to your Maya scripts directory
- Creates a shelf button on your current shelf (if accepted)
- Configures the tool for immediate use

### Manual Installation (Alternative)

If you prefer manual installation:

1. Copy `vertex_tweener.py` to your Maya scripts directory:
   
   - **Windows**: `Documents/maya/<version>/scripts/`
   - **macOS**: `~/Library/Preferences/Autodesk/maya/<version>/scripts/`
   - **Linux**: `~/maya/<version>/scripts/`

2. Create a shelf button with this Python command:
   
   ```python
   import vertex_tweener
   vertex_tweener.show()
   ```

## Usage

### Quick Start

1. **Select** one or more animated objects in your scene
2. **Position** the timeline between two keyframes
3. **Launch** Vertex Tweener from the shelf button
4. **Drag** the slider to break down the pose
5. **Enable Auto-Key** to commit changes, or leave it off to preview interactively

### Tool Overview

The Inbetweener Tool features five powerful sliders, each designed for specific animation tasks:

#### 🔵 Local Tweener (LT) - Main Slider

Break down poses between keyframes at the current timeline position.

- **0%** = Previous keyframe position
- **50%** = Halfway between keyframes
- **100%** = Next keyframe position
- **-50% to 0%** = Anticipation (overshoot mode)
- **100% to 150%** = Overshoot (overshoot mode)

**Use for:** Standard breakdowns, in-betweens, pose-to-pose animation

#### 🟡 World Tweener (WT) - World Space

Blend in world space using matrix interpolation (no viewport flicker).

- **Range:** 0% to 100%
- **Best for:** Maintaining world position during parent hierarchy changes
- **Benefits:** No viewport flicker, global coordinate tweening

**Use for:** Complex rigs with multiple parent constraints

#### 🟠 Blend to Neighbor (BN) - Nudge Toward Neighbors

Adjust selected controls toward neighboring keyframe values.

- **< 50:** Blend toward PREVIOUS key
- **> 50:** Blend toward NEXT key
- **50:** Neutral (no change)
- **Resets to 50** on release
- Works on selected controls in viewport

**Use for:** Smoothing rough keys, favoring timing in one direction

#### 🟣 Blend to Default (BD) - Reset to Rest Pose

Slide between original keyframe values and default/rest pose.

- **0:** Original keyframe values (no change)
- **100:** Default pose values
- **Preserves original** values when first pressed
- **Resets to 0** on release
- Uses **Scan Default Pose** values when available for accurate rest poses
- Falls back to Maya's attributeQuery, then intelligent heuristics (1.0 for scale/visibility/volume, 0.0 for translate/rotate)

**Use for:** Resetting poses, comparing keyed vs. rest pose, partial resets

#### 🟢 Blend to Ease (BE) - Professional Easing

Create smooth easing with cubic curves on selected controls.

- **< 50:** Ease-out (toward previous key)
- **> 50:** Ease-in (toward next key)
- **50:** Neutral (no ease)
- **Uses cubic curves** for natural motion
- **Resets to 50** on release

**Use for:** Professional ease-in/ease-out, smooth acceleration/deceleration

### Additional Features

#### Scan Default Pose

Store your rig's rest/bind pose for accurate Blend-to-Default results:

1. Put your rig in its default/bind pose
2. Select the root control(s) of your rig
3. Click **Scan Default Pose** in the tool
4. The tool scans all controls in the hierarchy and stores their values on a network node (`inbetweener_defaultPose`)

Once scanned, BD uses these real rest values instead of guessing. A confirmation dialog ensures you don't accidentally overwrite a previous scan.

#### Quick-Snap Buttons

Instant access to common breakdown positions:

- **Top Row:** 1/8, 1/4, 1/2, 3/4, 7/8
- **Bottom Row:** 0, 1/3, 2/3, 1

These buttons work with the Local Tweener and auto-key the result.

#### Motion Trails

Enable to visualize motion arcs in real-time:

- Identify problematic arcs
- Ensure smooth, natural motion
- See immediate feedback on tweening adjustments

#### Options

- **Auto Key:** Automatically set keyframes when tweening
- **Motion Trails:** Show visual feedback for animation arcs
- **Overshoot Mode:** Extend Local Tweener range to -50% and 150%

### Tips and Best Practices

- **Use Local Tweener for viewport tweening** - Fast, interactive, perfect for standard breakdowns
- **Use World Tweener for hierarchy changes** - Maintains world position during parent switching
- **Select controls for BN/BD/BE** - These sliders work on your selected controls in the viewport
- **Scan Default Pose for accurate BD results** - Put your rig in rest pose, select root controls, and scan once per rig
- **BD slider is great for resetting poses** - Slide to preview, release to reset, or commit at any point
- **Enable Motion Trails to visualize arcs** - See your spacing and motion path in real-time
- **Use Quick Buttons for common positions** - Faster than dragging the slider
- **Preview First**: Keep Auto-Key disabled while exploring values, then enable when satisfied
- **Multiple Objects**: Select multiple controls to break down complex rigs simultaneously
- **Undo Support**: Each slider drag is one undo action - press Ctrl+Z to revert
- **BE slider creates professional easing** - No need to manually adjust curves in Graph Editor

## Technical Details

### Requirements

- **Autodesk Maya** 2018 or later
- **Python** 2.7 or 3.x (depending on Maya version)
- **PySide2** (Maya 2017+) or **PySide6** (Maya 2022+) — auto-detected via compatibility layer

### How It Works

1. **Attribute Detection**: Scans all keyable attributes on selected objects
2. **Keyframe Analysis**: Identifies the previous and next keyframes surrounding the current time
3. **Interpolation**: Calculates new values using the tweening formula
4. **Application**: Sets the new values on all applicable attributes
5. **Keyframing**: Optionally creates keyframes if Auto-Key is enabled

### Architecture

- **TweenEngine**: Core interpolation logic with keyframe caching for fast slider drags
- **WorldTweenEngine**: World-space matrix interpolation with quaternion slerp for rotation
- **DefaultPoseStore**: Scans and stores rest/bind pose values on a Maya network node for accurate BD blending
- **MotionTrailsManager**: Handles visual feedback and motion trail lifecycle
- **VertexTickedSlider**: Custom QSlider with color-coded 10% tick marks and dynamic position labels
- **VertexTweenerUI**: PySide2/PySide6-based interface with accordion layout and preference management
- **Preference System**: Uses Maya's optionVar for persistent settings

### Supported Attributes

The tool automatically processes:

- Transform attributes (translate, rotate, scale)
- Custom rig controls
- Any keyable attribute on selected objects

The tool intelligently skips:

- Locked attributes
- Attributes with non-animation connections
- Attributes without sufficient keyframes

## Troubleshooting

### The tool doesn't affect my objects

**Solution**: Ensure your objects have at least two keyframes on the attributes you want to tween, and that you're positioned between them on the timeline.

### Motion Trails aren't appearing

**Solution**: Motion Trails require transform nodes. Ensure you have animated transform nodes selected, and that your playback range is set correctly.

### Shelf button isn't created

**Solution**: You can manually create a shelf button with this command:

```python
import vertex_tweener
vertex_tweener.show()
```

### Installation fails

**Solution**: Ensure you have write permissions to your Maya scripts directory. Try running Maya as administrator (Windows) or check folder permissions (macOS/Linux).

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with professional pipeline development best practices for Maya animators worldwide.

---

**Made for animators, by animators.** ✨
