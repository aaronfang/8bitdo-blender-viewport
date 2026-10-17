# Roadmap

The public `v1.0.0` release is the stable baseline. Large-scene improvements
will be delivered as independently testable releases.

## v1.1 - Control Foundation (Delivered)

- Manual speed gears controlled by D-pad Up/Down.
- Optional scene-scale-aware base Fly speed.
- Optional adaptive Fly speed based on the surface distance ahead.
- Independent left/right stick deadzones and response curves.
- Frame-rate-independent acceleration and damping for movement and look.
- Compact viewport status overlay.

Acceptance criteria:

- Existing Fly/Orbit mappings remain usable with all assists disabled.
- Speed gear changes occur once per button press.
- Movement converges smoothly and stops without persistent drift.
- Expensive scene queries run at no more than 10 Hz.
- Blender 4.5.5 can register/unregister the add-on without errors.

## v1.2 - Targeting And Recovery (Delivered)

- One-action focus using the existing pivot priority.
- Face target without moving the current viewpoint.
- Configurable smooth pivot/focus transitions.
- View history with previous/next navigation.
- Named view bookmarks stored in the `.blend` file.

Acceptance criteria:

- Target acquisition never changes the view unless the invoked action requests
  it.
- View transitions are interruptible and frame-rate independent.
- Bookmark data survives saving and reopening a `.blend` file.

## v1.3 - Environment Assistance (Delivered)

- Optional dynamic near/far viewport clipping.
- Horizon leveling and optional gradual horizon stabilization.
- Ground-walk mode with configurable eye height and step/slope behavior.
- Optional collision avoidance.
- Optional XInput vibration for mode, speed, and collision feedback.

Acceptance criteria:

- Every environment assist can be disabled independently.
- Ground queries and collision checks are cached and bounded in cost.
- Dynamic clipping does not overwrite user settings after navigation stops.
- Vibration always stops when the add-on stops or unloads.

## Compatibility

- Primary target: Blender 4.5 LTS on Windows.
- Input backend: Windows XInput.
- No third-party Python package dependencies.
- Navigation must continue to coexist with sculpting, transforms, and mesh
  editing.
