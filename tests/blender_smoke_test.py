import importlib
import math
import sys
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
    assert addon.axis_value(1000, 0.16, 1.5) == 0.0
    assert addon.axis_value(32767, 0.16, 2.0) == 1.0
    linear = addon.axis_value(16384, 0.16, 1.0)
    curved = addon.axis_value(16384, 0.16, 2.0)
    assert 0.0 < curved < linear < 1.0

    full = addon.exponential_blend(0.0, 1.0, 10.0, 0.1)
    half = addon.exponential_blend(0.0, 1.0, 10.0, 0.05)
    two_halves = addon.exponential_blend(half, 1.0, 10.0, 0.05)
    assert_close(full, two_halves)


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


def main():
    addon.register()
    try:
        test_input_math()
        test_button_edges()
        test_scene_scale()
        test_edit_component_pivot_and_unchanged_view()
    finally:
        addon.unregister()
    print("ALL_TESTS_PASSED")


if __name__ == "__main__":
    main()
