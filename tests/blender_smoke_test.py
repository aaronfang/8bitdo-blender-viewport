import importlib
import math
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bmesh
import bpy
from mathutils import Quaternion, Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
addon = importlib.import_module("8bitdo_blender_viewport")


def assert_close(actual, expected, tolerance=1.0e-6):
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"Expected {expected}, got {actual}")


def reset_scene():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def test_input_math():
    signature = (1, (10000, 0))
    _, last_change, stale = addon.input_watchdog(None, signature, 0.0, 1.0, 3.0, True)
    assert not stale
    _, _, stale = addon.input_watchdog(signature, signature, last_change, 4.1, 3.0, True)
    assert stale
    _, _, stale = addon.input_watchdog(signature, signature, last_change, 100.0, 3.0, False)
    assert not stale  # unchanged neutral input is normal
    _, _, stale = addon.input_watchdog(signature, signature, last_change, 100.0, 0.0, True)
    assert not stale  # explicit disable permits long constant holds
    _, changed, stale = addon.input_watchdog(signature, (2, (0, 0)), last_change, 4.2, 3.0, False)
    assert not stale and changed == 4.2
    for curve in (0.25, 0.5, 1.0, 1.5, 4.0):
        assert addon.axis_value(6655, 0.16, curve, 6655) == 0.0
        assert addon.axis_value(7000, 0.16, curve, 6655) == 0.0
    waiting, elapsed = True, 0.0
    for _ in range(100):
        waiting, elapsed = addon.neutral_input_gate(waiting, elapsed, False, 0.01)
    assert waiting and elapsed == 0.0
    for _ in range(20):
        waiting, elapsed = addon.neutral_input_gate(waiting, elapsed, True, 0.01)
    assert not waiting
    waiting, _ = addon.neutral_input_gate(waiting, elapsed, False, 0.01)
    assert not waiting  # deliberate movement is allowed after neutral confirmation
    assert addon.axis_value(6655, 0.16, 1.5, 6655) == 0.0
    assert addon.axis_value(-6145, 0.16, 1.5, -6145) == 0.0
    assert_close(addon.axis_value(32767, 0.16, 1.5, 6655), 1.0)
    assert_close(addon.axis_value(-32768, 0.16, 1.5, 6655), -1.0)
    velocity, idle = Vector((1.0, 0.0, 0.0)), 0.0
    for _ in range(60):
        velocity, idle = addon.movement_velocity(
            velocity, Vector(), 10.0, 0.1, idle, 0.01
        )
    assert velocity.length == 0.0
    velocity, idle = addon.movement_velocity(
        Vector((1.0, 0.0, 0.0)), Vector((-1.0, 0.0, 0.0)),
        10.0, 0.1, 0.4, 0.05,
    )
    assert velocity.x < 0.3
    assert idle == 0.0
    assert addon.axis_value(1000, 0.16, 1.5) == 0.0
    assert addon.axis_value(32767, 0.16, 2.0) == 1.0
    linear = addon.axis_value(16384, 0.16, 1.0)
    curved = addon.axis_value(16384, 0.16, 2.0)
    assert 0.0 < curved < linear < 1.0

    full = addon.exponential_blend(0.0, 1.0, 10.0, 0.1)
    half = addon.exponential_blend(0.0, 1.0, 10.0, 0.05)
    two_halves = addon.exponential_blend(half, 1.0, 10.0, 0.05)
    assert_close(full, two_halves)
    assert_close(addon.smoothstep(0.0), 0.0)
    assert_close(addon.smoothstep(0.5), 0.5)
    assert_close(addon.smoothstep(1.0), 1.0)
    assert_close(addon.adaptive_response(0.0, 2.0), 0.0)
    assert_close(addon.adaptive_response(0.5, 2.0), 0.75)
    assert_close(addon.adaptive_response(1.0, 2.0), 1.0)
    assert addon.adaptive_response(0.5, 4.0) > addon.adaptive_response(0.5, 1.0)


def test_adaptive_scene_speed_interaction():
    session = addon.GamepadNavigationSession
    prefs = SimpleNamespace(
        fly_speed=10.0,
        scene_scale_speed=True,
        adaptive_speed=True,
        adaptive_min_speed=0.05,
    )
    session.speed_gear = 0
    session.scene_speed_scale = 100.0

    session.adaptive_speed_scale = 1.0
    assert_close(session.calculate_fly_speed(prefs), 1000.0)
    assert_close(session.active_scene_scale, 100.0)

    session.adaptive_speed_scale = 0.05
    assert_close(session.calculate_fly_speed(prefs), 0.5)
    assert_close(session.active_scene_scale, 1.0)

    session.adaptive_speed_scale = 0.525
    speed = session.calculate_fly_speed(prefs)
    assert_close(session.active_scene_scale, 50.5)
    assert_close(speed, 265.125)


def test_button_edges():
    session = addon.GamepadNavigationSession
    session.previous_buttons = 0
    assert session.button_pressed(addon.XINPUT_GAMEPAD_DPAD_UP, addon.XINPUT_GAMEPAD_DPAD_UP)
    session.previous_buttons = addon.XINPUT_GAMEPAD_DPAD_UP
    assert not session.button_pressed(
        addon.XINPUT_GAMEPAD_DPAD_UP, addon.XINPUT_GAMEPAD_DPAD_UP
    )


def test_scene_scale():
    reset_scene()
    bpy.ops.mesh.primitive_cube_add(scale=(50.0, 50.0, 50.0))
    expected = math.sqrt(3.0)
    assert_close(addon.GamepadNavigationSession.calculate_scene_speed_scale(), expected)


def test_edit_component_pivot_and_unchanged_view():
    reset_scene()
    bpy.ops.mesh.primitive_cube_add(location=(2.0, 3.0, 4.0))
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    mesh = bmesh.from_edit_mesh(bpy.context.edit_object.data)
    mesh.verts.ensure_lookup_table()
    mesh.verts[0].select = True
    bmesh.update_edit_mesh(bpy.context.edit_object.data)

    rv3d = SimpleNamespace(
        view_location=Vector((1.0, 2.0, 3.0)),
        view_distance=10.0,
        view_rotation=Quaternion((1.0, 0.0, 0.0, 0.0)),
    )
    session = addon.GamepadNavigationSession
    session.rv3d = rv3d
    expected_pivot = bpy.context.edit_object.matrix_world @ mesh.verts[0].co
    before_location = rv3d.view_location.copy()
    before_rotation = rv3d.view_rotation.copy()
    before_distance = rv3d.view_distance

    session.focus_orbit_view()

    assert (session.orbit_pivot - expected_pivot).length < 1.0e-6
    assert (rv3d.view_location - before_location).length < 1.0e-6
    assert rv3d.view_rotation.rotation_difference(before_rotation).angle < 1.0e-6
    assert rv3d.view_distance == before_distance


def test_transition_and_history():
    session = addon.GamepadNavigationSession
    rv3d = SimpleNamespace(
        view_location=Vector((0.0, 0.0, 0.0)),
        view_distance=10.0,
        view_rotation=Quaternion((1.0, 0.0, 0.0, 0.0)),
    )
    session.rv3d = rv3d
    session.orbit_pivot = Vector((0.0, 0.0, 0.0))
    session.history_back = []
    session.history_forward = []
    session.effective_mode = "FLY"

    target = session.capture_view_state()
    target["view_location"] = Vector((10.0, 0.0, 0.0))
    target["orbit_pivot"] = Vector((10.0, 0.0, 0.0))
    assert session.begin_transition(target, 1.0)
    session.transition_start_time = 0.0
    assert session.update_transition(0.5)
    assert_close(rv3d.view_location.x, 5.0)
    assert session.update_transition(1.0)
    assert_close(rv3d.view_location.x, 10.0)
    assert session.transition_end is None

    assert session.navigate_history(-1, 0.0)
    assert_close(rv3d.view_location.x, 0.0)
    assert session.navigate_history(1, 0.0)
    assert_close(rv3d.view_location.x, 10.0)


def test_face_target_preserves_camera_position():
    reset_scene()
    bpy.ops.mesh.primitive_cube_add(location=(5.0, 0.0, 0.0))
    session = addon.GamepadNavigationSession
    session.rv3d = SimpleNamespace(
        view_location=Vector((0.0, 0.0, 0.0)),
        view_distance=10.0,
        view_rotation=Quaternion((1.0, 0.0, 0.0, 0.0)),
    )
    session.orbit_pivot = None
    session.effective_mode = "FLY"
    camera_before = session.camera_position()
    assert session.face_target(0.0)
    camera_after = session.camera_position()
    assert (camera_before - camera_after).length < 1.0e-6


def test_bookmark_persistence():
    bookmark = bpy.context.scene.gamepad_view_bookmarks.add()
    bookmark.name = "Persistent View"
    bookmark.view_location = (1.0, 2.0, 3.0)
    bookmark.view_rotation = (1.0, 0.0, 0.0, 0.0)
    bookmark.view_distance = 25.0
    bookmark.navigation_mode = "ORBIT"
    bookmark.speed_gear = 2

    handle, path = tempfile.mkstemp(suffix=".blend")
    os.close(handle)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        restored = bpy.context.scene.gamepad_view_bookmarks[0]
        assert restored.name == "Persistent View"
        assert tuple(restored.view_location) == (1.0, 2.0, 3.0)
        assert restored.navigation_mode == "ORBIT"
        assert restored.speed_gear == 2
    finally:
        os.unlink(path)


def test_horizon_level_preserves_forward_direction():
    forward = Vector((1.0, 0.2, -0.3)).normalized()
    base = forward.to_track_quat("-Z", "Y")
    rolled = Quaternion(forward, 0.7) @ base
    leveled = addon.GamepadNavigationSession.leveled_rotation(rolled)
    leveled_forward = leveled @ Vector((0.0, 0.0, -1.0))
    assert (leveled_forward - forward).length < 1.0e-6
    leveled_right = leveled @ Vector((1.0, 0.0, 0.0))
    assert abs(leveled_right.z) < 1.0e-6


def test_ground_walk_and_dynamic_clipping():
    reset_scene()
    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 0.0, 0.0))
    bpy.context.view_layer.update()
    session = addon.GamepadNavigationSession
    ground_prefs = SimpleNamespace(
        collision_avoidance=False,
        collision_radius=0.3,
        ground_eye_height=1.7,
        ground_step_height=0.5,
        ground_probe_distance=10.0,
        ground_slope_angle=math.radians(50.0),
    )
    session.ground_initialized = False
    result = session.apply_ground_walk(
        Vector((0.0, 0.0, 0.4)),
        Vector((1.0, 0.0, 0.0)),
        ground_prefs,
        0.5,
    )
    assert_close(result.x, 1.0)
    assert_close(result.z, 1.7)
    assert session.ground_initialized

    session.ground_initialized = False
    result = session.apply_ground_walk(
        Vector((0.0, 0.0, 5.0)),
        Vector((1.0, 0.0, 0.0)),
        ground_prefs,
        1.0,
    )
    assert_close(result.x, 1.0)
    assert_close(result.z, 1.7)

    bpy.ops.mesh.primitive_plane_add(
        size=10.0,
        location=(1.0, 0.0, 2.0),
        rotation=(0.0, math.radians(90.0), 0.0),
    )
    bpy.context.view_layer.update()
    ground_prefs.collision_avoidance = True
    ground_prefs.vibration_feedback = False
    ground_prefs.vibration_strength = 0.0
    result = session.apply_ground_walk(
        Vector((0.0, 0.0, 1.7)),
        Vector((2.0, 0.0, 0.0)),
        ground_prefs,
        1.0,
    )
    assert_close(result.x, 0.7)
    assert_close(result.z, 1.7)

    session.space = SimpleNamespace(clip_start=0.1, clip_end=1000.0)
    session.original_clip_start = 0.1
    session.original_clip_end = 1000.0
    session.scene_diagonal = 10000.0
    session.current_fly_speed = 100.0
    session.last_clip_time = 0.0
    session.update_dynamic_clipping(SimpleNamespace(dynamic_clipping=True), 1.0)
    assert_close(session.space.clip_start, 0.1)
    assert_close(session.space.clip_end, 40000.0)
    session.update_dynamic_clipping(SimpleNamespace(dynamic_clipping=False), 1.1)
    assert_close(session.space.clip_start, 0.1)
    assert_close(session.space.clip_end, 1000.0)
    session.space = None


def test_native_navigation_rebase_preserves_view():
    reset_scene()
    bpy.ops.mesh.primitive_cube_add(location=(3.0, 0.0, 0.0))
    session = addon.GamepadNavigationSession
    session.rv3d = SimpleNamespace(
        view_location=Vector((0.0, 0.0, 9.99)),
        view_distance=0.01,
        view_rotation=Quaternion((1.0, 0.0, 0.0, 0.0)),
    )
    session.scene_diagonal = math.sqrt(12.0)
    camera_before = session.camera_position()
    rotation_before = session.rv3d.view_rotation.copy()

    session.prepare_native_navigation()

    camera_after = session.camera_position()
    assert (camera_after - camera_before).length < 1.0e-6
    assert session.rv3d.view_rotation.rotation_difference(rotation_before).angle < 1.0e-6
    assert_close(session.rv3d.view_distance, 10.0)
    assert (session.rv3d.view_location - Vector((0.0, 0.0, 0.0))).length < 1.0e-6

    bpy.ops.object.select_all(action="DESELECT")
    session.rv3d.view_location = Vector((0.0, 0.0, 9.999))
    session.rv3d.view_distance = 0.001
    session.scene_diagonal = 1000.0
    camera_before = session.camera_position()
    session.prepare_native_navigation()
    assert (session.camera_position() - camera_before).length < 1.0e-6
    assert_close(session.rv3d.view_distance, 20.0)

    session.rv3d.view_perspective = "ORTHO"
    location_before = session.rv3d.view_location.copy()
    distance_before = session.rv3d.view_distance
    session.prepare_native_navigation()
    assert (session.rv3d.view_location - location_before).length < 1.0e-6
    assert session.rv3d.view_distance == distance_before


def test_sculpt_focus_follows_object_without_view_change():
    reset_scene()
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    bpy.ops.object.mode_set(mode="SCULPT")
    manager = addon.LargeSceneNavigationManager
    manager.focus_by_object.clear()
    key = manager.object_key(obj)
    manager.focus_by_object[key] = {
        "local_location": Vector((1.0, 0.0, 0.0)),
        "world_fallback": Vector((1.0, 0.0, 0.0)),
    }
    obj.location = (10.0, 2.0, 0.0)
    bpy.context.view_layer.update()

    focus = manager.sculpt_focus(bpy.context)
    assert (focus - Vector((11.0, 2.0, 0.0))).length < 1.0e-6

    rv3d = SimpleNamespace(
        view_location=Vector((2.0, 3.0, 4.0)),
        view_rotation=Quaternion((1.0, 0.0, 0.0, 0.0)),
        view_distance=25.0,
    )
    view_before = manager.capture_view(rv3d)
    assert (manager.sculpt_focus(bpy.context) - focus).length < 1.0e-6
    view_after = manager.capture_view(rv3d)
    assert manager.views_match(view_before, view_after)
    manager.focus_by_object.clear()


def test_native_view_history_is_per_viewport():
    class Pointer:
        def __init__(self, value):
            self.value = value

        def as_pointer(self):
            return self.value

    class Area(Pointer):
        def tag_redraw(self):
            pass

    manager = addon.LargeSceneNavigationManager
    rv3d = SimpleNamespace(
        view_location=Vector((5.0, 0.0, 0.0)),
        view_rotation=Quaternion((1.0, 0.0, 0.0, 0.0)),
        view_distance=20.0,
    )
    window, area, space = Pointer(1), Area(2), Pointer(3)
    space.region_3d = rv3d
    context = SimpleNamespace(window=window, area=area, space_data=space)
    key = manager.viewport_key(window, area, space)
    previous = {
        "view_location": Vector(),
        "view_rotation": Quaternion((1.0, 0.0, 0.0, 0.0)),
        "view_distance": 10.0,
    }
    manager.viewport_states[key] = {
        "rv3d": rv3d,
        "area": area,
        "back": [previous],
        "forward": [],
        "last": manager.capture_view(rv3d),
        "committed": manager.capture_view(rv3d),
        "moving": False,
        "suppress_until": 0.0,
    }

    assert manager.history_step(context, -1)
    assert rv3d.view_location.length == 0.0
    assert_close(rv3d.view_distance, 10.0)
    assert manager.history_step(context, 1)
    assert (rv3d.view_location - Vector((5.0, 0.0, 0.0))).length < 1.0e-6
    assert_close(rv3d.view_distance, 20.0)
    manager.viewport_states.clear()


def test_release_defaults():
    properties = addon.GamepadNavigationPreferences.bl_rna.properties
    assert_close(properties["fly_speed"].default, 30.0)
    assert properties["adaptive_speed"].default
    assert_close(math.degrees(properties["ground_slope_angle"].default), 89.0, 1.0e-4)
    assert properties["vibration_feedback"].default
    assert_close(properties["vibration_strength"].default, 1.0)


def main():
    addon.register()
    try:
        test_input_math()
        test_adaptive_scene_speed_interaction()
        test_button_edges()
        test_scene_scale()
        test_edit_component_pivot_and_unchanged_view()
        test_transition_and_history()
        test_face_target_preserves_camera_position()
        test_bookmark_persistence()
        test_horizon_level_preserves_forward_direction()
        test_ground_walk_and_dynamic_clipping()
        test_native_navigation_rebase_preserves_view()
        test_sculpt_focus_follows_object_without_view_change()
        test_native_view_history_is_per_viewport()
        test_release_defaults()
    finally:
        addon.unregister()
    print("ALL_TESTS_PASSED")


if __name__ == "__main__":
    main()
