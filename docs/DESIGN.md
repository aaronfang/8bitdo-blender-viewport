# Navigation Design

## Principles

1. Starting navigation must not create a long-running modal operator.
2. Switching modes must not change the visible view transform.
3. Controller actions are edge-triggered unless explicitly continuous.
4. Scene queries are cached and run at a lower frequency than input polling.
5. Optional assists must have explicit settings and conservative defaults.

## Modes

`navigation_mode` stores the persistent mode. `effective_mode` includes a
temporary inversion while LB, L3, or R3 is held.

- Tap LB: toggle the persistent mode.
- Hold LB, L3, or R3: temporarily use the opposite mode.
- Release: return to the persistent mode.

Entering Orbit records a pivot without modifying `view_location`,
`view_rotation`, or `view_distance`. Pivot priority is:

1. Most recent sculpt stroke location.
2. Center of selected Edit Mode mesh components.
3. Combined center of selected Object Mode object bounds.
4. Existing viewport focus.

## Controller Map

| Input | Continuous action | Edge action |
| --- | --- | --- |
| Left stick | Move / pan | - |
| Right stick | Look / orbit | - |
| LT / RT | Vertical move / zoom | - |
| LB | Temporary opposite mode | Tap toggles persistent mode |
| RB | Fly height lock / Orbit boost | - |
| L3 / R3 | Temporary opposite mode | - |
| D-pad Up / Down | - | Increase / decrease speed gear |
| A | - | Focus target |
| B | - | Face target |
| X | - | Toggle ground walk |
| Y | - | Level horizon |
| D-pad Left / Right | - | Previous / next view history |
| Start | - | Save or recall bookmark through a modifier/chord |
| Back | - | Stop navigation |

Mappings beyond `v1.1` may be exposed as preferences before release if user
testing shows conflicts.

## Speed Model

The effective Fly speed is:

```text
base speed * manual gear * active scene scale * adaptive proximity
```

- Manual gears are discrete powers of ten around `1x`.
- Scene scaling uses a cached scene-bounds diagonal and is recomputed only on
  start or explicit refresh.
- Adaptive proximity uses a forward ray cast at no more than 10 Hz. Its start
  distance, minimum multiplier, and curve are configurable. Higher curve values
  retain more speed until closer to the detected surface.
- While Adaptive Surface Speed is active, the requested scene multiplier fades
  toward `1x` as the surface multiplier approaches its minimum. This prevents a
  large-scene multiplier from overwhelming close-surface precision.

Movement and look commands are filtered with an exponential response whose
coefficient is derived from elapsed time. This makes acceleration independent
of timer frequency.

## View State

A view state contains:

- world-space viewpoint position;
- view quaternion;
- `view_distance`;
- Orbit pivot;
- persistent navigation mode;
- speed gear.

History uses a bounded deque. Bookmarks use Blender scene properties so they
are serialized into the `.blend` file.

## Rendering And Cleanup

The status overlay uses a `SpaceView3D` post-pixel draw handler and Blender's
font API. The status and control-help sections can be switched independently.
Status includes mode-specific speed settings, effective Fly speed factors,
surface distance, active assists, and controller connection. Draw handlers,
timers, and XInput vibration must all be removed during stop and unregister.

## Performance Budgets

- Input and view update: approximately 100 Hz.
- Forward proximity ray: at most 10 Hz.
- Ground/collision rays: at most 20 Hz while moving; one initial alignment
  query on activation and no repeated queries while idle.
- Scene bounds: on start or explicit refresh, never every timer tick.
- Overlay: redraw with the viewport; no independent timer.
