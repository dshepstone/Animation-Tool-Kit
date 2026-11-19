# Animation Tool Kit 1.1.18 — Noise Generator 1.2.0

## New: Noise Generator presets and inbetween workflow

The **Noise Generator** has a new tabbed layout and a quick way to add camera shakes, skids and impacts between two keys.

- **Presets tab.** Select the start and end key, set **Amount** and click a preset. It bakes the gap, eases it and adds noise in one undo step. The two keys never move.
  - **Camera Shake**: random jitter on 1's that fades in and out.
  - **Handheld**: slower, softer drift on 3's.
  - **Impact Hit**: a hard rattle that dies away into the end key.
  - **Skid to Stop**: slows into the stop with chatter that dies out.
  - **Settle Wobble**: back-and-forth on 2's that settles.
  - **Rumble Build**: grows from nothing to full strength.
- **Bake between two keys.** Select two keys and bake on 1's, 2's, 3's or 4's. The two keys keep their value, time and tangents, and only the curves you selected keys on are baked. **Select inbetweens after bake** selects just the new inbetweens.
- **Pin Noise.** Zigzag or random noise on the inbetweens. **Pin start key** and **Pin end key** fade the noise into those keys so there is no pop. **Decay** gives a strong start that dies away.
- **Ease In / Ease Out.** Re-time the inbetweens: a slow or fast start, and a slow or fast finish.
- **Start and end keys stay put.** While Pin Noise, Ease In or Ease Out are dragged, the keys on either side of the selection hold their value and their tangents are set to *fixed*, so the curve through them does not swing.
- **Tabs.** Inbetweens, Presets, Noise and Shape. The channel filter stays at the top, and the tool remembers the last tab.

## Retained features

Includes everything from 1.1.17: toolbar layouts (Settings → Layout), and from 1.1.16 Animation Tweaker, and from 1.1.15 the toolkit-wide bug fixes, Key Cleanup, Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards. Then click **Noise Generator** on the toolbar and open the **Presets** or **Inbetweens** tab.
