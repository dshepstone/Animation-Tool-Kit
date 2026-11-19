# Animation Tool Kit 1.1.17 — Toolbar layouts

## New: Settings → Layout

The toolbar now has almost 30 buttons. Docked along the bottom of Maya it can run past the edge of the screen. The new **Layout** tab in the toolbar's Settings makes it fit: show fewer buttons, fold groups away, use more than one row, and pick the icon size and alignment. Changes show on the toolbar straight away.

Nothing changes until you pick something: the default layout is **Full**, the same toolbar as 1.1.16.

- **Presets.** Each one works docked on any side or floating.
  - **Full**: every tool, in the usual order, with the group separators.
  - **Most used**: the tools you click most (10 by default, 3 to 25), and a **More** button with the rest.
  - **Custom**: only the tools you tick, in your own order.
  - **Grouped**: one button each for Timing, Viewport, Rigging and Pipeline. Click a group to open its tools in a small strip. Tick a group under *Grouped: open on the bar* to keep its tools on the bar instead.
- **Expert mode** works with any preset: smaller icons, tighter spacing, no separators, and group buttons without text. Tooltips stay.
- **Tools list.** Tick the tools to show, and drag them (or use **Up** / **Down**) to set the order Custom and Grouped use. Tools you hid in earlier versions stay hidden.
- **My groups.** Make your own named groups of tools, such as *Blocking* or *Polish*. They fold open like the built-in groups, in the Custom and Grouped layouts.
- **Rows and columns.** Use 1 to 3 rows on a top or bottom bar, or 1 to 3 columns on a side bar. Tools wrap in order.
- **Alignment.** Left, centre or right on a top or bottom bar; top, centre or bottom on a side bar.
- **Icon size**: Small, Medium or Large (moved here from the Appearance tab).
- **Export / Import** a layout as a file, to share it with a class or move it to another computer. **Reset layout** goes back to Full.
- **Usage.** ATK counts how often you use each tool: button clicks, quick left-click actions, right-click actions and the Timeline Ticks colour strips. Most used ranks by this count. **Reset usage** clears it. The bar doesn't reorder while you work; it updates the next time it is built (opening Maya, changing Settings or Reload Scripts).

Folded tools work as they do on the bar: the same icon, tooltip, left-click and right-click menu. Clicking outside the strip closes it.

You can also switch preset and Expert mode from the gear button's right-click menu, under **Layout**. Right-click a group button to unfold it on the bar.

The tool checkboxes moved from the old Tools tab to the Layout tab. That tab is now called **Widgets** and keeps the Inbetweener slider and frame stepper switches.

## Tests

- New automated tests cover the layout rules: each preset, rows and columns, alignment, ties in usage, damaged or old settings, and moving the old hide settings into the new layout. CI runs them.
- New offscreen tests build the real toolbar in every preset, on both orientations, with 1 to 3 rows, and drive the Layout tab, the fold-out strips and usage counting. CI runs them.
- `tests/check_toolbar_layouts_maya.py` checks the layouts inside Maya with `mayapy`:

  `"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" tests/check_toolbar_layouts_maya.py`

## Retained features

Includes everything from 1.1.16: Animation Tweaker (sculpted corrections and polish on animated meshes, keyed as static, pulse or pose-to-pose tweaks), and from 1.1.15 the toolkit-wide bug fixes, Key Cleanup, Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards. Then open **Settings → Layout**.
