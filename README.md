# 8BitDo Blender Viewport

Navigate Blender's 3D viewport with an 8BitDo or other XInput-compatible
controller while continuing to sculpt, transform objects, and edit mesh
components.

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

## Notes

- The add-on controls the viewport, not scene cameras or objects.
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
