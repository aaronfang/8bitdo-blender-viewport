# Changelog

## 1.3.1 - 2026-10-17

- Rebase Blender's native mouse-navigation focus when gamepad navigation stops.
- Preserve the exact visible viewpoint while deriving a stable orbit depth from
  the sculpt stroke, selected components, selected objects, or scene scale.
- Clarify that Fly/Orbit shown while inactive is the next controller mode.

## 1.3.0 - 2026-10-17

- Add X-button Ground mode with eye height, step, slope, and collision controls.
- Add Y-button horizon leveling and optional gradual stabilization.
- Add optional dynamic viewport clipping with automatic restoration on stop.
- Add optional XInput vibration for navigation events and collisions.
- Limit ground/collision queries to 30 Hz and clipping updates to 5 Hz.

## 1.2.0 - 2026-10-17

- Add A-button target focus and B-button target facing.
- Add interruptible smooth view and Orbit-pivot transitions.
- Add D-pad Left/Right bidirectional view history.
- Add named view bookmarks stored in the `.blend` scene.
- Preserve camera position when facing the active target.

## 1.1.0 - 2026-10-17

- Add D-pad Fly speed gears from `0.001x` through `1000x`.
- Add separate left/right stick deadzones and response curves.
- Add frame-rate-independent Fly movement and look smoothing.
- Add optional scene-scale and forward-surface adaptive Fly speed.
- Add a compact viewport status overlay.
- Add repeatable Blender smoke tests for navigation math and pivot behavior.

## 1.0.0 - 2026-10-17

- Initial public release.
- Add concurrent Fly and Orbit viewport navigation through XInput.
- Add persistent and temporary mode switching.
- Add context-aware Orbit pivots without changing the view on mode switch.
- Add Fly height lock and separate movement/look speed controls.
- Add configurable deadzones, inversion, controller index, and navigation
  speeds.
