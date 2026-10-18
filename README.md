# 8BitDo Blender Viewport

Navigate Blender's 3D viewport with an 8BitDo or other XInput-compatible
controller while continuing to sculpt, transform objects, and edit mesh
components.

[中文帮助](docs/README_ZH.md)

The add-on targets Blender 4.5 LTS on Windows and reads controllers directly
through Windows XInput. It has no third-party Python dependencies.

## Features

- Free-flight navigation for large scenes without orbit zoom limits.
- Orbit navigation around a context-aware pivot.
- Background polling that does not occupy Blender's modal event chain.
- Temporary or persistent switching between Fly and Orbit.
- Independent Fly movement and look speeds.
- World-height lock for level flight.
- Controller deadzones, axis inversion, and precision/fast controls.
- Manual speed gears, independent stick response curves, and smooth Fly input.
- Optional scene-scale and surface-distance adaptive speed.
- Compact in-viewport navigation status.
- Target focus/facing actions with interruptible smooth transitions.
- Bidirectional view history and `.blend`-persistent named bookmarks.
- Optional dynamic viewport clipping and horizon stabilization.
- Ground-walk navigation with slope, step, and collision controls.
- Optional XInput vibration feedback.

## Installation

1. Download `8bitdo_blender_viewport.py` from the latest release.
2. In Blender, open **Edit > Preferences > Add-ons**.
3. Use **Install from Disk...** and select the downloaded Python file.
4. Enable **8BitDo / XInput Viewport Navigation**.
5. In a 3D Viewport, press `N`, open **View > Gamepad Navigation**, and click
   **Start**.

The controller must be connected in XInput/X mode. Use `joy.cpl` on Windows to
confirm that it is visible as a game controller.

## Controls

| Input | Fly | Orbit |
| --- | --- | --- |
| Left stick | Strafe / move forward and backward | Pan |
| Right stick | Look | Orbit around the active pivot |
| LT / RT | Move down / up | Zoom out / in |
| Tap LB | Permanently switch Fly / Orbit | Permanently switch Fly / Orbit |
| Hold LB | Temporarily use Orbit | Temporarily use Fly |
| Hold RB | Lock world Z height | 3x navigation speed |
| Hold L3 or R3 | Temporarily use the opposite mode | Temporarily use the opposite mode |
| D-pad Up / Down | Increase / decrease speed gear | Increase / decrease speed gear |
| A / B | Focus / face the active target | Focus / face the active target |
| X / Y | Toggle Ground mode / level horizon | Toggle Ground mode / level horizon |
| D-pad Left / Right | Previous / next view | Previous / next view |
| Back | Stop gamepad navigation | Stop gamepad navigation |

`Ctrl+Shift+J` toggles gamepad navigation when the mouse is over a 3D
Viewport.

Standard XInput does not expose 8BitDo P1/P2 rear buttons as independent
buttons. In 8BitDo Ultimate Software, map P1 and P2 to L3 and R3 to use either
rear button for temporary mode switching.

## Orbit Pivot Priority

Switching to Orbit does not change the current viewport position, orientation,
or zoom. The add-on records a pivot using this priority:

1. Most recent sculpt brush location.
2. Center of selected mesh components in Edit Mode.
3. Combined bounding-box center of selected objects in Object Mode.
4. Current viewport focus.

Subsequent Orbit rotation and zoom use that independent pivot.

## Settings

### Fly And Orbit

| Setting | Meaning |
| --- | --- |
| Fly Move Speed | Base translation speed in Blender units per second. |
| Fly Look Speed | Right-stick look speed in radians per second. |
| Fly Acceleration | How quickly movement approaches the requested speed. |
| Fly Damping | How quickly residual movement stops after releasing the stick. |
| Look Response | How quickly right-stick rotation approaches the requested rate. |
| Orbit Speed | Right-stick Orbit angular speed. |
| Pan Speed | Orbit pan speed relative to `view_distance`. |
| Zoom Speed | Exponential Orbit zoom rate. |
| View Transition | Duration of focus, face, history, bookmark, and horizon animations. |

### Large-scene Speed

`Scene Scale Speed` multiplies Fly speed using the scene-bounds diagonal. It is
useful when the same controller settings must work in scenes of very different
sizes.

`Adaptive Surface Speed` casts a ray along the viewing direction and slows Fly
movement only inside the configured range:

| Setting | Meaning |
| --- | --- |
| Adaptive Start Distance | Surface distance, in Blender units, where slowing begins. Lower it to delay slowing until closer to geometry. |
| Adaptive Minimum Speed | Fraction of base Fly speed retained at the surface. `0.05` means 5%. |
| Adaptive Curve | Higher values preserve speed longer and concentrate slowing near the surface. |

When both systems are enabled, the scene-scale multiplier fades back to `1x`
inside the adaptive range. This prevents a very large scene multiplier from
overpowering close-surface precision.

### Ground And View Assistance

| Setting | Meaning |
| --- | --- |
| Dynamic View Clipping | Adapts near/far clipping to scene size and speed, restoring original values on stop. |
| Horizon Stabilization | Gradually removes sideways camera roll while preserving yaw and pitch/look direction. |
| Horizon Strength | Rate at which sideways roll is corrected. |
| Ground Eye Height | Viewpoint height above the detected ground surface. |
| Maximum Step | Largest upward ground-height change Ground mode can climb in one update. |
| Ground Probe Distance | Maximum downward search distance for walkable ground. |
| Maximum Slope | Steepest surface normal accepted as walkable ground. |
| Collision Avoidance | Prevents Ground mode from moving through forward geometry. |
| Collision Radius | Clearance retained between the viewpoint and a detected obstacle. |

On entering Ground mode, the viewpoint first aligns to Ground Eye Height even
when that correction is larger than Maximum Step. Maximum Step applies to
subsequent terrain changes. Ground rays run only while aligning or moving, so
an idle controller does not continuously query scene geometry.

### Input And Display

Starting, reconnecting, or editing left-stick curve/deadzone/calibration requires
150 ms with all analog controls neutral before navigation resumes. The status
HUD displays INPUT PAUSED while waiting. Calibrate the released left stick if
needed. Curves below 1 amplify input outside the deadzone, never neutral input.

If the released left stick still reports movement, release it and click
`Calibrate Left Stick Center` in the N panel. Reset Left Center X/Y to zero in
preferences to undo calibration. Stable offsets can be calibrated; frozen
controller readings require reconnecting the controller. Higher Fly Damping
brakes faster; neutral input always stops movement within 0.5 seconds.

Left/right stick deadzones and response curves are independent. A higher curve
gives finer control around the center while retaining full output at the edge.

`Viewport Status` displays live mode, connection, effective speed, gear,
scene/adaptive multipliers, detected surface distance, and active assists.
`Control Help` separately displays the controller mapping in the viewport's
lower-left corner. Both overlays appear only while navigation is running.

## Notes

- The add-on controls the viewport, not scene cameras or objects.
- Stopping navigation preserves the visible viewpoint and rebuilds a stable
  native Blender orbit focus for subsequent mouse/keyboard navigation.
- Ground mode uses world Z as up and follows ray-castable scene geometry.
- Dynamic clipping restores the viewport's original clipping values when
  navigation stops.
- XInput supports up to four controllers; choose index `0` through `3` in the
  panel.
- If no controller is detected, switch the controller to XInput/X mode and
  check whether Steam Input or another application has exclusive control.

## License

[MIT](LICENSE)

## Development

Run the smoke tests with Blender 4.5:

```powershell
blender.exe --background --factory-startup --python tests/blender_smoke_test.py
```
