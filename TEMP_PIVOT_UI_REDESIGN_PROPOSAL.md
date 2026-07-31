# Temp Pivot Tool — UI Redesign Proposal (Approval Draft)

## Goal
Make the Temp Pivot Tool faster to scan and easier to operate in production by using:
- a wider default window,
- clear two-column layout,
- tabbed workflows,
- modern visual hierarchy,
- and reduced scrolling.

---

## Proposed Window Spec

- **Window title:** `Temp Pivot Tool`
- **Default size:** `620 x 560` (resizable, minimum `560 x 500`)
- **Layout shell:**
  - Top: compact header/status strip.
  - Body: **Tabs** (`Workflow`, `Controls`, `Options`, `Help`).
  - Footer: context-aware primary action + compact hints.

---

## Information Architecture

### 1) Workflow Tab (primary)
A two-column operational layout focused on the most common task.

#### Left column (about 65%)
**Stage cards** with numbered progress chips:
1. Select Control
2. Create Pivot Locator
3. Position Pivot
4. Complete Setup
5. Toggle Pivot Mode

Each stage card includes:
- one-line explanation,
- primary action button,
- success/error inline feedback,
- disabled/enabled states based on prerequisites.

#### Right column (about 35%)
**Live context panel**:
- Current control name,
- Pivot null name,
- Active mode (`ON`/`OFF`),
- Current frame,
- Last action result.

This panel stays visible so users don’t need to scroll back to check status.

---

### 2) Controls Tab
Quick access to frequently used actions after setup:
- `Toggle ON / OFF` (large switch-style button),
- `Key Control`,
- `Reset / Cleanup` (if available),
- optional shortcuts hints (e.g., `D + Insert`).

Use evenly spaced button groups in two columns.

---

### 3) Options Tab
Utility/settings that should not clutter the main workflow:
- Auto-key behavior,
- Constraint naming options,
- Confirmations / warnings toggles,
- UI density (`Compact` / `Comfortable`).

---

### 4) Help Tab
A concise guide replacing long stacked text blocks:
- 5-step quick start,
- common mistakes and fixes,
- short glossary (`pivot null`, `offset`, etc.).

---

## Visual Design Direction

### Palette (dark modern, Maya-friendly)
- Window bg: `#2B2D31`
- Card bg: `#34373C`
- Border/divider: `#4A4F57`
- Text primary: `#E7EAF0`
- Text secondary: `#B5BDC9`
- Accent blue: `#4C9AFF` (setup/primary actions)
- Accent green: `#36C275` (active/toggle ON)
- Accent amber: `#E6A23C` (create/setup attention)
- Error red: `#D9534F`

### Typography and spacing
- Header: semibold, 12–13 px equivalent
- Body: regular, 10–11 px equivalent
- Section spacing: 10–12 px
- Card padding: 10 px
- Button height: 34–38 px for primary actions

### Component style
- Flat-modern cards with subtle borders,
- consistent button color semantics,
- chips/badges for stage number + state (`Ready`, `Waiting`, `Done`),
- fewer heavy separators; more whitespace for readability.

---

## UX Behavior Improvements

- Keep key actions always visible (no deep vertical scrolling).
- Disable impossible actions and show why (inline hint under button).
- Persistent status panel to avoid context loss.
- Contextual footer action:
  - before setup: `Create Pivot Locator` / `Complete Setup`,
  - after setup: `Toggle Pivot ON/OFF`.
- Optional toast-style mini notifications for completed actions.

---

## Text / Label Cleanup

Replace verbose copy with action-first microcopy:
- `Stage 1 — Create Pivot Locator` → `1. Create Pivot`
- `Stage 2 — Complete Setup` → `2. Finalize`
- `Toggle ON / OFF` remains but show state badge next to it.

Guide content moves into the **Help** tab.

---

## Low-Fidelity Wireframe (concept)

```text
+------------------------------------------------------------------+
| Temp Pivot Tool                                  [READY] [v1.1]  |
+------------------------------------------------------------------+
| Workflow | Controls | Options | Help                             |
+-------------------------------+----------------------------------+
| 1. Select Control             | Current Context                  |
| [ Select From Scene ]         | Control: arm_ctrl_L             |
|                               | Pivot Null: tempPivot_arm_L     |
| 2. Create Pivot               | Mode: OFF                       |
| [ Create Pivot Locator ]      | Frame: 124                      |
|                               | Last: Locator created           |
| 3. Position Pivot             |                                  |
| Use D + Insert                |                                  |
|                               |                                  |
| 4. Finalize                   |                                  |
| [ Complete Setup ]            |                                  |
+-------------------------------+----------------------------------+
| Primary Action: [ Toggle Pivot ON ]   Hint: Key after major move |
+------------------------------------------------------------------+
```

---

## Why this will be easier to navigate

- Tabs separate workflow from secondary settings.
- Two columns reduce back-and-forth scanning.
- Persistent right panel prevents losing state context.
- Large, staged actions reduce user mistakes.
- Wider window removes cramped single-column stacking.

---

## Implementation Plan (after approval)

1. Add tab container and split workflow into left/right panels.
2. Convert current stage sections into card components with state chips.
3. Move guide content into Help tab and shorten labels in Workflow.
4. Add consistent color tokens and spacing constants.
5. Add a context-aware footer primary action.
6. Validate in Maya with common animator flow (select → create → adjust → complete → toggle).

---

## Approval Request

If this direction looks good, I will implement this as **Phase 1 (layout + visual refresh)** while preserving all existing tool logic and behavior.
