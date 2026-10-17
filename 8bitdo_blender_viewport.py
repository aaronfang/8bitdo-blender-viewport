bl_info = {
    "name": "8BitDo / XInput Viewport Navigation",
    "author": "Aaron Fang, OpenAI Codex",
    "version": (1, 2, 0),
    "blender": (4, 5, 0),
    "location": "3D Viewport > Sidebar > View > Gamepad Navigation",
    "description": "Navigate the 3D viewport with an XInput-compatible gamepad",
    "category": "3D View",
}

import ctypes
import math
import sys
import time

import bmesh
import blf
import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)
from mathutils import Quaternion, Vector


ADDON_ID = __package__ or __name__
XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_A = 0x1000
XINPUT_GAMEPAD_B = 0x2000
TEMPORARY_MODE_BUTTONS = XINPUT_GAMEPAD_LEFT_THUMB | XINPUT_GAMEPAD_RIGHT_THUMB
LB_TAP_SECONDS = 0.25


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


def load_xinput():
    if sys.platform != "win32":
        return None
    for dll_name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            dll = ctypes.WinDLL(dll_name)
            dll.XInputGetState.argtypes = [ctypes.c_ulong, ctypes.POINTER(XINPUT_STATE)]
            dll.XInputGetState.restype = ctypes.c_ulong
            return dll
        except OSError:
            continue
    return None


XINPUT = load_xinput()


def axis_value(raw, deadzone, response_curve=1.0):
    value = max(-1.0, min(1.0, raw / 32767.0))
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    scaled = ((magnitude - deadzone) / (1.0 - deadzone)) ** response_curve
    return math.copysign(scaled, value)


def trigger_value(raw, threshold):
    value = raw / 255.0
    if value <= threshold:
        return 0.0
    return (value - threshold) / (1.0 - threshold)


def exponential_blend(current, target, response, dt):
    factor = 1.0 - math.exp(-max(response, 0.001) * max(dt, 0.0))
    return current + (target - current) * factor


def draw_gamepad_status():
    session = GamepadNavigationSession
    if not session.active or not session.show_hud:
        return
    try:
        if bpy.context.area != session.area:
            return
    except ReferenceError:
        return

    status = session.effective_mode
    status += f"  SPEED {10.0 ** session.speed_gear:g}x"
    if session.effective_mode == "FLY":
        status += f"  {session.current_fly_speed:.2f} u/s"
    if session.height_locked:
        status += "  HEIGHT LOCK"
    if not session.connected:
        status += "  CONTROLLER DISCONNECTED"

    font_id = 0
    blf.position(font_id, 18, 42, 0)
    blf.size(font_id, 14.0)
    blf.color(font_id, 0.92, 0.95, 1.0, 0.9)
    blf.draw(font_id, status)


class GamepadViewBookmark(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="View")
    view_location: FloatVectorProperty(size=3, subtype="XYZ")
    view_rotation: FloatVectorProperty(size=4, subtype="QUATERNION")
    view_distance: FloatProperty(default=10.0, min=0.001)
    orbit_pivot: FloatVectorProperty(size=3, subtype="XYZ")
    orbit_pivot_valid: BoolProperty(default=False)
    navigation_mode: EnumProperty(
        items=(("ORBIT", "Orbit", ""), ("FLY", "Fly", "")),
        default="FLY",
    )
    speed_gear: IntProperty(default=0, min=-3, max=3)


class GamepadNavigationPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    navigation_mode: EnumProperty(
        name="Navigation Mode",
        items=(
            ("ORBIT", "Orbit", "Orbit, pan, and zoom around a point"),
            ("FLY", "Fly", "Move freely through the scene without a zoom limit"),
        ),
        default="FLY",
    )
    controller_index: IntProperty(
        name="Controller",
        description="XInput controller index (usually 0 for the first controller)",
        default=0,
        min=0,
        max=3,
    )
    left_stick_deadzone: FloatProperty(
        name="Left Stick Deadzone",
        default=0.16,
        min=0.0,
        max=0.8,
        subtype="FACTOR",
    )
    right_stick_deadzone: FloatProperty(
        name="Right Stick Deadzone",
        default=0.16,
        min=0.0,
        max=0.8,
        subtype="FACTOR",
    )
    left_stick_curve: FloatProperty(
        name="Left Stick Curve",
        description="Higher values provide finer control near the stick center",
        default=1.5,
        min=0.25,
        max=4.0,
    )
    right_stick_curve: FloatProperty(
        name="Right Stick Curve",
        description="Higher values provide finer look control near the stick center",
        default=1.5,
        min=0.25,
        max=4.0,
    )
    trigger_deadzone: FloatProperty(
        name="Trigger Deadzone",
        default=0.05,
        min=0.0,
        max=0.8,
        subtype="FACTOR",
    )
    orbit_speed: FloatProperty(
        name="Orbit Speed",
        description="Orbit speed in radians per second",
        default=1.8,
        min=0.05,
        max=10.0,
    )
    pan_speed: FloatProperty(
        name="Pan Speed",
        description="Pan speed relative to the current view distance",
        default=0.9,
        min=0.01,
        max=10.0,
    )
    zoom_speed: FloatProperty(
        name="Zoom Speed",
        default=2.2,
        min=0.05,
        max=10.0,
    )
    fly_speed: FloatProperty(
        name="Fly Move Speed",
        description="Free-flight speed in Blender units per second",
        default=10.0,
        min=0.001,
        soft_max=1000.0,
        max=1000000.0,
    )
    fly_look_speed: FloatProperty(
        name="Fly Look Speed",
        description="Free-flight look speed in radians per second",
        default=1.8,
        min=0.05,
        max=10.0,
    )
    fly_acceleration: FloatProperty(
        name="Fly Acceleration",
        description="How quickly Fly movement reaches the requested speed",
        default=10.0,
        min=0.1,
        max=50.0,
    )
    fly_damping: FloatProperty(
        name="Fly Damping",
        description="How quickly Fly movement stops after releasing the stick",
        default=14.0,
        min=0.1,
        max=50.0,
    )
    look_response: FloatProperty(
        name="Look Response",
        description="How quickly Fly look reaches the requested turn rate",
        default=18.0,
        min=0.1,
        max=50.0,
    )
    scene_scale_speed: BoolProperty(
        name="Scene Scale Speed",
        description="Scale Fly speed from the cached scene bounds",
        default=False,
    )
    adaptive_speed: BoolProperty(
        name="Adaptive Surface Speed",
        description="Slow Fly movement when approaching visible geometry",
        default=False,
    )
    show_hud: BoolProperty(
        name="Viewport Status",
        description="Show navigation mode and speed in the viewport",
        default=True,
    )
    transition_duration: FloatProperty(
        name="View Transition",
        description="Duration of focus, facing, history, and bookmark transitions",
        default=0.25,
        min=0.0,
        max=2.0,
        subtype="TIME",
    )
    invert_orbit_y: BoolProperty(name="Invert Right Stick Y", default=False)
    invert_pan_y: BoolProperty(name="Invert Left Stick Y", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "navigation_mode", expand=True)
        layout.prop(self, "controller_index")
        layout.prop(self, "left_stick_deadzone")
        layout.prop(self, "right_stick_deadzone")
        layout.prop(self, "left_stick_curve")
        layout.prop(self, "right_stick_curve")
        layout.prop(self, "trigger_deadzone")
        layout.separator()
        layout.prop(self, "orbit_speed")
        layout.prop(self, "pan_speed")
        layout.prop(self, "zoom_speed")
        layout.prop(self, "fly_speed")
        layout.prop(self, "fly_look_speed")
        layout.prop(self, "fly_acceleration")
        layout.prop(self, "fly_damping")
        layout.prop(self, "look_response")
        layout.prop(self, "scene_scale_speed")
        layout.prop(self, "adaptive_speed")
        layout.prop(self, "show_hud")
        layout.prop(self, "transition_duration")
        layout.prop(self, "invert_orbit_y")
        layout.prop(self, "invert_pan_y")


class GamepadNavigationSession:
    """Poll XInput without occupying Blender's modal operator event chain."""

    active = False
    connected = False
    area = None
    rv3d = None
    last_time = 0.0
    lb_was_down = False
    lb_press_time = 0.0
    effective_mode = "ORBIT"
    last_sculpt_location = None
    last_sculpt_object = None
    orbit_pivot = None
    previous_buttons = 0
    speed_gear = 0
    scene_speed_scale = 1.0
    adaptive_speed_scale = 1.0
    last_proximity_time = 0.0
    fly_velocity = Vector((0.0, 0.0, 0.0))
    look_velocity = Vector((0.0, 0.0))
    current_fly_speed = 0.0
    height_locked = False
    show_hud = True
    draw_handler = None
    history_back = []
    history_forward = []
    transition_start = None
    transition_end = None
    transition_start_time = 0.0
    transition_duration = 0.0

    @classmethod
    def start(cls, context):
        cls.area = context.area
        cls.rv3d = getattr(context.space_data, "region_3d", None)
        cls.last_time = time.perf_counter()
        cls.connected = False
        cls.lb_was_down = False
        cls.lb_press_time = 0.0
        addon = context.preferences.addons.get(ADDON_ID)
        cls.effective_mode = addon.preferences.navigation_mode if addon else "FLY"
        cls.last_sculpt_location = None
        cls.last_sculpt_object = None
        cls.orbit_pivot = None
        cls.previous_buttons = 0
        cls.speed_gear = 0
        cls.scene_speed_scale = cls.calculate_scene_speed_scale()
        cls.adaptive_speed_scale = 1.0
        cls.last_proximity_time = 0.0
        cls.fly_velocity = Vector((0.0, 0.0, 0.0))
        cls.look_velocity = Vector((0.0, 0.0))
        cls.current_fly_speed = 0.0
        cls.height_locked = False
        cls.show_hud = addon.preferences.show_hud if addon else True
        cls.history_back = []
        cls.history_forward = []
        cls.transition_start = None
        cls.transition_end = None
        cls.active = True
        if cls.draw_handler is None:
            cls.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                draw_gamepad_status, (), "WINDOW", "POST_PIXEL"
            )
        if not bpy.app.timers.is_registered(gamepad_navigation_timer):
            bpy.app.timers.register(gamepad_navigation_timer, first_interval=0.01)

    @classmethod
    def stop(cls):
        cls.active = False
        cls.connected = False
        cls.lb_was_down = False
        cls.fly_velocity = Vector((0.0, 0.0, 0.0))
        cls.look_velocity = Vector((0.0, 0.0))
        cls.height_locked = False
        try:
            cls.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass
        cls.area = None
        cls.rv3d = None
        cls.orbit_pivot = None
        cls.transition_start = None
        cls.transition_end = None
        if cls.draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(cls.draw_handler, "WINDOW")
            cls.draw_handler = None

    @classmethod
    def capture_view_state(cls):
        if cls.rv3d is None:
            return None
        addon = bpy.context.preferences.addons.get(ADDON_ID)
        mode = addon.preferences.navigation_mode if addon else cls.effective_mode
        return {
            "view_location": cls.rv3d.view_location.copy(),
            "view_rotation": cls.rv3d.view_rotation.copy(),
            "view_distance": float(cls.rv3d.view_distance),
            "orbit_pivot": cls.orbit_pivot.copy() if cls.orbit_pivot is not None else None,
            "navigation_mode": mode,
            "speed_gear": cls.speed_gear,
        }

    @classmethod
    def apply_view_state(cls, state):
        if state is None or cls.rv3d is None:
            return
        cls.rv3d.view_location = state["view_location"].copy()
        cls.rv3d.view_rotation = state["view_rotation"].copy()
        cls.rv3d.view_distance = state["view_distance"]
        pivot = state.get("orbit_pivot")
        cls.orbit_pivot = pivot.copy() if pivot is not None else None
        cls.speed_gear = state.get("speed_gear", cls.speed_gear)
        addon = bpy.context.preferences.addons.get(ADDON_ID)
        if addon is not None:
            addon.preferences.navigation_mode = state.get(
                "navigation_mode", addon.preferences.navigation_mode
            )

    @classmethod
    def push_history(cls):
        state = cls.capture_view_state()
        if state is None:
            return
        cls.history_back.append(state)
        del cls.history_back[:-32]
        cls.history_forward.clear()

    @classmethod
    def begin_transition(cls, target, duration, record_history=True):
        current = cls.capture_view_state()
        if current is None or target is None:
            return False
        if record_history:
            cls.history_back.append(current)
            del cls.history_back[:-32]
            cls.history_forward.clear()
        if duration <= 0.0:
            cls.apply_view_state(target)
            return True
        cls.transition_start = current
        cls.transition_end = target
        cls.transition_start_time = time.perf_counter()
        cls.transition_duration = duration
        return True

    @classmethod
    def update_transition(cls, now):
        if cls.transition_end is None:
            return False
        factor = min(
            max((now - cls.transition_start_time) / cls.transition_duration, 0.0),
            1.0,
        )
        eased = factor * factor * (3.0 - 2.0 * factor)
        start = cls.transition_start
        end = cls.transition_end
        cls.rv3d.view_location = start["view_location"].lerp(
            end["view_location"], eased
        )
        cls.rv3d.view_rotation = start["view_rotation"].slerp(
            end["view_rotation"], eased
        )
        cls.rv3d.view_distance = (
            start["view_distance"]
            + (end["view_distance"] - start["view_distance"]) * eased
        )
        start_pivot = start.get("orbit_pivot")
        end_pivot = end.get("orbit_pivot")
        if start_pivot is None:
            start_pivot = start["view_location"]
        if end_pivot is None:
            end_pivot = end["view_location"]
        cls.orbit_pivot = start_pivot.lerp(end_pivot, eased)
        if factor >= 1.0:
            cls.apply_view_state(end)
            cls.transition_start = None
            cls.transition_end = None
        return True

    @classmethod
    def cancel_transition(cls):
        cls.transition_start = None
        cls.transition_end = None

    @classmethod
    def focus_target(cls, duration):
        target_point = cls.orbit_focus()
        target = cls.capture_view_state()
        if target is None:
            return False
        target["view_location"] = target_point.copy()
        target["orbit_pivot"] = target_point.copy()
        return cls.begin_transition(target, duration)

    @classmethod
    def face_target(cls, duration):
        target_point = cls.orbit_focus()
        target = cls.capture_view_state()
        if target is None:
            return False
        camera_position = cls.camera_position()
        direction = target_point - camera_position
        if direction.length <= 0.000001:
            return False
        rotation = direction.normalized().to_track_quat("-Z", "Y")
        distance = max(cls.rv3d.view_distance, 0.001)
        target["view_rotation"] = rotation
        target["view_location"] = (
            camera_position - rotation @ Vector((0.0, 0.0, distance))
        )
        target["orbit_pivot"] = target_point.copy()
        return cls.begin_transition(target, duration)

    @classmethod
    def navigate_history(cls, direction, duration):
        source = cls.history_back if direction < 0 else cls.history_forward
        destination = cls.history_forward if direction < 0 else cls.history_back
        if not source:
            return False
        current = cls.capture_view_state()
        target = source.pop()
        if current is not None:
            destination.append(current)
            del destination[:-32]
        return cls.begin_transition(target, duration, record_history=False)

    @classmethod
    def calculate_scene_speed_scale(cls):
        minimum = Vector((math.inf, math.inf, math.inf))
        maximum = Vector((-math.inf, -math.inf, -math.inf))
        found = False
        for obj in bpy.context.scene.objects:
            try:
                for corner in obj.bound_box:
                    point = obj.matrix_world @ Vector(corner)
                    minimum.x = min(minimum.x, point.x)
                    minimum.y = min(minimum.y, point.y)
                    minimum.z = min(minimum.z, point.z)
                    maximum.x = max(maximum.x, point.x)
                    maximum.y = max(maximum.y, point.y)
                    maximum.z = max(maximum.z, point.z)
                    found = True
            except (AttributeError, ReferenceError, TypeError):
                continue
        if not found:
            return 1.0
        diagonal = (maximum - minimum).length
        return max(0.01, min(diagonal / 100.0, 1000.0))

    @classmethod
    def update_adaptive_speed(cls, prefs, now, rotation):
        if not prefs.adaptive_speed:
            cls.adaptive_speed_scale = 1.0
            return
        if now - cls.last_proximity_time < 0.1:
            return
        cls.last_proximity_time = now

        origin = cls.camera_position(rotation)
        direction = rotation @ Vector((0.0, 0.0, -1.0))
        reference = max(cls.scene_speed_scale * 100.0 * 0.02, 0.1)
        try:
            hit, _location, _normal, _index, _object, _matrix = (
                bpy.context.scene.ray_cast(
                    bpy.context.evaluated_depsgraph_get(),
                    origin,
                    direction,
                    distance=reference,
                )
            )
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            hit = False
            _location = None

        if hit:
            distance = (Vector(_location) - origin).length
            cls.adaptive_speed_scale = max(0.05, min(distance / reference, 1.0))
        else:
            cls.adaptive_speed_scale = 1.0

    @classmethod
    def button_pressed(cls, buttons, mask):
        return bool(buttons & mask) and not bool(cls.previous_buttons & mask)

    @classmethod
    def capture_sculpt_location(cls):
        active_object = bpy.context.active_object
        if active_object is None or active_object.mode != "SCULPT":
            return

        try:
            operators = reversed(bpy.context.window_manager.operators)
        except (AttributeError, ReferenceError):
            return

        for operator in operators:
            if getattr(operator, "bl_idname", "") != "SCULPT_OT_brush_stroke":
                continue
            try:
                stroke = getattr(operator, "stroke", None)
                if stroke is None:
                    stroke = getattr(operator.properties, "stroke", None)
                if stroke:
                    cls.last_sculpt_location = Vector(stroke[-1].location)
                    cls.last_sculpt_object = active_object.name
            except (AttributeError, ReferenceError, TypeError):
                pass
            break

    @classmethod
    def selected_objects_center(cls):
        points = []
        for obj in bpy.context.selected_objects:
            try:
                points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
            except (AttributeError, ReferenceError, TypeError):
                try:
                    points.append(obj.matrix_world.translation.copy())
                except (AttributeError, ReferenceError):
                    pass
        if not points:
            return None
        return sum(points, Vector()) / len(points)

    @classmethod
    def selected_components_center(cls):
        points = []
        objects = getattr(bpy.context, "objects_in_mode_unique_data", ())
        for obj in objects:
            if obj.type != "MESH" or obj.mode != "EDIT":
                continue
            try:
                mesh = bmesh.from_edit_mesh(obj.data)
                points.extend(
                    obj.matrix_world @ vertex.co
                    for vertex in mesh.verts
                    if vertex.select
                )
            except (ReferenceError, RuntimeError, TypeError):
                continue
        if not points:
            return None
        return sum(points, Vector()) / len(points)

    @classmethod
    def orbit_focus(cls):
        active_object = bpy.context.active_object
        if (
            active_object is not None
            and active_object.mode == "SCULPT"
            and cls.last_sculpt_object == active_object.name
            and cls.last_sculpt_location is not None
        ):
            return cls.last_sculpt_location.copy()
        if active_object is not None and active_object.mode == "EDIT":
            component_center = cls.selected_components_center()
            if component_center is not None:
                return component_center
        if bpy.context.mode == "OBJECT":
            object_center = cls.selected_objects_center()
            if object_center is not None:
                return object_center
        return cls.rv3d.view_location.copy()

    @classmethod
    def focus_orbit_view(cls):
        cls.orbit_pivot = cls.orbit_focus()

    @classmethod
    def camera_position(cls, rotation=None):
        rv3d = cls.rv3d
        rotation = rotation or rv3d.view_rotation
        distance = max(rv3d.view_distance, 0.001)
        return rv3d.view_location + rotation @ Vector((0.0, 0.0, distance))

    @classmethod
    def set_camera_transform(cls, camera_position, rotation):
        rv3d = cls.rv3d
        distance = max(rv3d.view_distance, 0.001)
        rv3d.view_rotation = rotation
        rv3d.view_location = (
            camera_position - rotation @ Vector((0.0, 0.0, distance))
        )

    @classmethod
    def tick(cls):
        if not cls.active:
            return None

        try:
            if cls.area.type != "VIEW_3D":
                cls.stop()
                return None
        except (AttributeError, ReferenceError):
            cls.stop()
            return None

        addon = bpy.context.preferences.addons.get(ADDON_ID)
        if addon is None:
            cls.stop()
            return None
        prefs = addon.preferences
        cls.capture_sculpt_location()
        state = XINPUT_STATE()
        result = XINPUT.XInputGetState(prefs.controller_index, ctypes.byref(state))
        cls.connected = result == 0
        cls.area.tag_redraw()
        if not cls.connected:
            cls.last_time = time.perf_counter()
            cls.lb_was_down = False
            cls.previous_buttons = 0
            cls.effective_mode = prefs.navigation_mode
            return 0.05

        gamepad = state.Gamepad
        buttons = gamepad.wButtons
        if buttons & XINPUT_GAMEPAD_BACK:
            cls.stop()
            return None

        now = time.perf_counter()
        dt = min(now - cls.last_time, 0.05)
        cls.last_time = now

        lx = axis_value(
            gamepad.sThumbLX, prefs.left_stick_deadzone, prefs.left_stick_curve
        )
        ly = axis_value(
            gamepad.sThumbLY, prefs.left_stick_deadzone, prefs.left_stick_curve
        )
        rx = axis_value(
            gamepad.sThumbRX, prefs.right_stick_deadzone, prefs.right_stick_curve
        )
        ry = axis_value(
            gamepad.sThumbRY, prefs.right_stick_deadzone, prefs.right_stick_curve
        )
        lt = trigger_value(gamepad.bLeftTrigger, prefs.trigger_deadzone)
        rt = trigger_value(gamepad.bRightTrigger, prefs.trigger_deadzone)

        if prefs.invert_pan_y:
            ly = -ly
        if prefs.invert_orbit_y:
            ry = -ry

        if cls.button_pressed(buttons, XINPUT_GAMEPAD_DPAD_UP):
            cls.speed_gear = min(cls.speed_gear + 1, 3)
        if cls.button_pressed(buttons, XINPUT_GAMEPAD_DPAD_DOWN):
            cls.speed_gear = max(cls.speed_gear - 1, -3)

        lb_down = bool(buttons & XINPUT_GAMEPAD_LEFT_SHOULDER)
        if lb_down and not cls.lb_was_down:
            cls.lb_press_time = now
        elif not lb_down and cls.lb_was_down:
            if now - cls.lb_press_time < LB_TAP_SECONDS:
                prefs.navigation_mode = (
                    "FLY" if prefs.navigation_mode == "ORBIT" else "ORBIT"
                )
        cls.lb_was_down = lb_down

        previous_mode = cls.effective_mode
        temporary_mode = lb_down or bool(buttons & TEMPORARY_MODE_BUTTONS)
        cls.effective_mode = prefs.navigation_mode
        if temporary_mode:
            cls.effective_mode = "FLY" if prefs.navigation_mode == "ORBIT" else "ORBIT"

        if previous_mode != "ORBIT" and cls.effective_mode == "ORBIT":
            cls.focus_orbit_view()
            cls.fly_velocity = Vector((0.0, 0.0, 0.0))
            cls.look_velocity = Vector((0.0, 0.0))
        elif cls.effective_mode == "ORBIT" and cls.orbit_pivot is None:
            cls.focus_orbit_view()

        rb_down = bool(buttons & XINPUT_GAMEPAD_RIGHT_SHOULDER)
        speed_scale = 1.0
        if rb_down and cls.effective_mode == "ORBIT":
            speed_scale *= 3.0

        rv3d = cls.rv3d
        rotation = rv3d.view_rotation.copy()

        manual_input = max(abs(lx), abs(ly), abs(rx), abs(ry), lt, rt) > 0.01
        if manual_input:
            cls.cancel_transition()
        else:
            if cls.button_pressed(buttons, XINPUT_GAMEPAD_A):
                cls.focus_target(prefs.transition_duration)
            elif cls.button_pressed(buttons, XINPUT_GAMEPAD_B):
                cls.face_target(prefs.transition_duration)
            elif cls.button_pressed(buttons, XINPUT_GAMEPAD_DPAD_LEFT):
                cls.navigate_history(-1, prefs.transition_duration)
            elif cls.button_pressed(buttons, XINPUT_GAMEPAD_DPAD_RIGHT):
                cls.navigate_history(1, prefs.transition_duration)

        if cls.update_transition(now):
            cls.previous_buttons = buttons
            return 0.01

        if cls.effective_mode == "FLY":
            distance = max(rv3d.view_distance, 0.001)
            cls.height_locked = rb_down
            cls.show_hud = prefs.show_hud
            cls.update_adaptive_speed(prefs, now, rotation)

            target_look = Vector((rx, ry))
            cls.look_velocity = exponential_blend(
                cls.look_velocity, target_look, prefs.look_response, dt
            )
            smooth_rx, smooth_ry = cls.look_velocity

            if abs(smooth_rx) > 0.0001 or abs(smooth_ry) > 0.0001:
                camera_position = (
                    rv3d.view_location
                    + rotation @ Vector((0.0, 0.0, distance))
                )
                yaw = Quaternion(
                    (0.0, 0.0, 1.0),
                    -smooth_rx * prefs.fly_look_speed * dt,
                )
                pitch_axis = rotation @ Vector((1.0, 0.0, 0.0))
                pitch = Quaternion(
                    pitch_axis,
                    smooth_ry * prefs.fly_look_speed * dt,
                )
                rotation = (pitch @ yaw @ rotation).normalized()
                rv3d.view_rotation = rotation
                rv3d.view_location = (
                    camera_position
                    - rotation @ Vector((0.0, 0.0, distance))
                )

            vertical = rt - lt
            target_velocity = Vector((lx, ly, vertical))
            if rb_down:
                target_velocity.z = 0.0
            movement_response = (
                prefs.fly_acceleration
                if target_velocity.length > cls.fly_velocity.length
                else prefs.fly_damping
            )
            cls.fly_velocity = exponential_blend(
                cls.fly_velocity, target_velocity, movement_response, dt
            )

            scene_scale = cls.scene_speed_scale if prefs.scene_scale_speed else 1.0
            cls.current_fly_speed = (
                prefs.fly_speed
                * (10.0 ** cls.speed_gear)
                * scene_scale
                * cls.adaptive_speed_scale
            )

            if cls.fly_velocity.length > 0.0001:
                right = rotation @ Vector((1.0, 0.0, 0.0))
                forward = rotation @ Vector((0.0, 0.0, -1.0))
                movement = (
                    right * cls.fly_velocity.x
                    + forward * cls.fly_velocity.y
                    + Vector((0.0, 0.0, cls.fly_velocity.z))
                )
                if rb_down:
                    movement.z = 0.0
                rv3d.view_location += movement * cls.current_fly_speed * dt
        else:
            cls.height_locked = False
            cls.current_fly_speed = 0.0
            cls.show_hud = prefs.show_hud
            if lx or ly:
                right = rotation @ Vector((1.0, 0.0, 0.0))
                up = rotation @ Vector((0.0, 1.0, 0.0))
                distance_scale = max(rv3d.view_distance, 0.01)
                movement = right * lx + up * ly
                translation = movement * prefs.pan_speed * distance_scale * dt * speed_scale
                rv3d.view_location += translation
                cls.orbit_pivot += translation

            if rx or ry:
                camera_position = cls.camera_position(rotation)
                yaw = Quaternion((0.0, 0.0, 1.0), -rx * prefs.orbit_speed * dt * speed_scale)
                pitch_axis = rotation @ Vector((1.0, 0.0, 0.0))
                pitch = Quaternion(pitch_axis, ry * prefs.orbit_speed * dt * speed_scale)
                delta = pitch @ yaw
                rotation = (delta @ rotation).normalized()
                camera_position = (
                    cls.orbit_pivot
                    + delta @ (camera_position - cls.orbit_pivot)
                )
                cls.set_camera_transform(camera_position, rotation)

            zoom_input = rt - lt
            if zoom_input:
                camera_position = cls.camera_position(rv3d.view_rotation)
                zoom_factor = math.exp(-zoom_input * prefs.zoom_speed * dt * speed_scale)
                camera_position = (
                    cls.orbit_pivot
                    + (camera_position - cls.orbit_pivot) * zoom_factor
                )
                cls.set_camera_transform(camera_position, rv3d.view_rotation.copy())

        cls.previous_buttons = buttons
        return 0.01


def gamepad_navigation_timer():
    return GamepadNavigationSession.tick()


class VIEW3D_OT_gamepad_navigation(bpy.types.Operator):
    bl_idname = "view3d.gamepad_navigation"
    bl_label = "Toggle Gamepad Navigation"
    bl_description = "Start or stop XInput viewport navigation"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        if GamepadNavigationSession.active:
            GamepadNavigationSession.stop()
            self.report({"INFO"}, "Gamepad navigation stopped")
            return {"FINISHED"}

        if XINPUT is None:
            self.report({"ERROR"}, "XInput is unavailable; this add-on requires Windows")
            return {"CANCELLED"}

        if getattr(context.space_data, "region_3d", None) is None:
            self.report({"ERROR"}, "Run this command with the mouse over a 3D viewport")
            return {"CANCELLED"}

        GamepadNavigationSession.start(context)
        self.report({"INFO"}, "Gamepad navigation started; Back stops it")
        return {"FINISHED"}


class VIEW3D_OT_gamepad_view_action(bpy.types.Operator):
    bl_idname = "view3d.gamepad_view_action"
    bl_label = "Gamepad View Action"
    bl_options = {"REGISTER"}

    action: EnumProperty(
        items=(
            ("FOCUS", "Focus", "Center the active navigation target"),
            ("FACE", "Face", "Turn toward the active navigation target"),
            ("BACK", "Previous", "Return to the previous view"),
            ("FORWARD", "Next", "Advance to the next view"),
        )
    )

    @classmethod
    def poll(cls, context):
        return GamepadNavigationSession.active

    def execute(self, context):
        session = GamepadNavigationSession
        prefs = context.preferences.addons[ADDON_ID].preferences
        if self.action == "FOCUS":
            changed = session.focus_target(prefs.transition_duration)
        elif self.action == "FACE":
            changed = session.face_target(prefs.transition_duration)
        elif self.action == "BACK":
            changed = session.navigate_history(-1, prefs.transition_duration)
        else:
            changed = session.navigate_history(1, prefs.transition_duration)
        return {"FINISHED"} if changed else {"CANCELLED"}


class VIEW3D_OT_gamepad_bookmark_save(bpy.types.Operator):
    bl_idname = "view3d.gamepad_bookmark_save"
    bl_label = "Save View Bookmark"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return GamepadNavigationSession.active

    def execute(self, context):
        state = GamepadNavigationSession.capture_view_state()
        if state is None:
            return {"CANCELLED"}
        bookmark = context.scene.gamepad_view_bookmarks.add()
        name = context.scene.gamepad_bookmark_name.strip()
        bookmark.name = name or f"View {len(context.scene.gamepad_view_bookmarks)}"
        bookmark.view_location = state["view_location"]
        bookmark.view_rotation = tuple(state["view_rotation"])
        bookmark.view_distance = state["view_distance"]
        pivot = state.get("orbit_pivot")
        bookmark.orbit_pivot_valid = pivot is not None
        if pivot is not None:
            bookmark.orbit_pivot = pivot
        bookmark.navigation_mode = state["navigation_mode"]
        bookmark.speed_gear = state["speed_gear"]
        context.scene.gamepad_bookmark_name = ""
        return {"FINISHED"}


class VIEW3D_OT_gamepad_bookmark_recall(bpy.types.Operator):
    bl_idname = "view3d.gamepad_bookmark_recall"
    bl_label = "Recall View Bookmark"

    index: IntProperty()

    @classmethod
    def poll(cls, context):
        return GamepadNavigationSession.active

    def execute(self, context):
        bookmarks = context.scene.gamepad_view_bookmarks
        if self.index < 0 or self.index >= len(bookmarks):
            return {"CANCELLED"}
        bookmark = bookmarks[self.index]
        pivot = Vector(bookmark.orbit_pivot) if bookmark.orbit_pivot_valid else None
        state = {
            "view_location": Vector(bookmark.view_location),
            "view_rotation": Quaternion(bookmark.view_rotation),
            "view_distance": bookmark.view_distance,
            "orbit_pivot": pivot,
            "navigation_mode": bookmark.navigation_mode,
            "speed_gear": bookmark.speed_gear,
        }
        prefs = context.preferences.addons[ADDON_ID].preferences
        GamepadNavigationSession.begin_transition(
            state, prefs.transition_duration, record_history=True
        )
        return {"FINISHED"}


class VIEW3D_OT_gamepad_bookmark_delete(bpy.types.Operator):
    bl_idname = "view3d.gamepad_bookmark_delete"
    bl_label = "Delete View Bookmark"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty()

    def execute(self, context):
        bookmarks = context.scene.gamepad_view_bookmarks
        if self.index < 0 or self.index >= len(bookmarks):
            return {"CANCELLED"}
        bookmarks.remove(self.index)
        return {"FINISHED"}


class VIEW3D_PT_gamepad_navigation(bpy.types.Panel):
    bl_label = "Gamepad Navigation"
    bl_idname = "VIEW3D_PT_gamepad_navigation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "View"

    def draw(self, context):
        layout = self.layout
        addon = context.preferences.addons.get(ADDON_ID)
        prefs = addon.preferences if addon else None

        if prefs:
            layout.prop(prefs, "navigation_mode", expand=True)
            if GamepadNavigationSession.active:
                layout.label(
                    text="Active: " + GamepadNavigationSession.effective_mode.title(),
                    icon="ORIENTATION_VIEW",
                )

        if not GamepadNavigationSession.active:
            layout.operator("view3d.gamepad_navigation", text="Start", icon="PLAY")
            layout.label(text="Controller inactive", icon="RADIOBUT_OFF")
        else:
            layout.operator("view3d.gamepad_navigation", text="Stop", icon="PAUSE")
            if GamepadNavigationSession.connected:
                layout.label(text="Controller connected", icon="RADIOBUT_ON")
            else:
                layout.label(text="Waiting for XInput controller", icon="ERROR")

        box = layout.box()
        box.label(text="Controls")
        if prefs and prefs.navigation_mode == "FLY":
            box.label(text="Left stick: Strafe / Forward")
            box.label(text="Right stick: Look")
            box.label(text="LT / RT: Down / Up")
        else:
            box.label(text="Left stick: Pan")
            box.label(text="Right stick: Orbit")
            box.label(text="LT / RT: Zoom out / in")
        box.label(text="LB tap: Toggle Orbit / Fly")
        box.label(text="Hold LB: Temporary opposite mode")
        box.label(text="P1 / P2: Temporary opposite mode")
        box.label(text="Map rear buttons to L3 / R3")
        box.label(text="D-pad Up / Down: Speed gear")
        box.label(text="A / B: Focus / Face target")
        box.label(text="D-pad Left / Right: View history")
        if prefs and prefs.navigation_mode == "FLY":
            box.label(text="Hold RB: Lock world height")
        else:
            box.label(text="RB: Fast")
        box.label(text="Back: Stop")

        view_box = layout.box()
        view_box.label(text="Views")
        row = view_box.row(align=True)
        operator = row.operator("view3d.gamepad_view_action", text="Focus")
        operator.action = "FOCUS"
        operator = row.operator("view3d.gamepad_view_action", text="Face")
        operator.action = "FACE"
        row = view_box.row(align=True)
        operator = row.operator("view3d.gamepad_view_action", text="Previous")
        operator.action = "BACK"
        operator = row.operator("view3d.gamepad_view_action", text="Next")
        operator.action = "FORWARD"

        view_box.prop(context.scene, "gamepad_bookmark_name", text="")
        view_box.operator("view3d.gamepad_bookmark_save", text="Save Bookmark")
        for index, bookmark in enumerate(context.scene.gamepad_view_bookmarks):
            row = view_box.row(align=True)
            operator = row.operator(
                "view3d.gamepad_bookmark_recall", text=bookmark.name
            )
            operator.index = index
            operator = row.operator("view3d.gamepad_bookmark_delete", text="", icon="X")
            operator.index = index

        if prefs:
            layout.separator()
            layout.prop(prefs, "controller_index")
            layout.prop(prefs, "orbit_speed")
            if prefs.navigation_mode == "FLY":
                layout.prop(prefs, "fly_speed")
                layout.prop(prefs, "fly_look_speed")
                layout.prop(prefs, "fly_acceleration")
                layout.prop(prefs, "fly_damping")
                layout.prop(prefs, "look_response")
                layout.prop(prefs, "scene_scale_speed")
                layout.prop(prefs, "adaptive_speed")
            else:
                layout.prop(prefs, "pan_speed")
                layout.prop(prefs, "zoom_speed")
            layout.prop(prefs, "left_stick_deadzone")
            layout.prop(prefs, "right_stick_deadzone")
            layout.prop(prefs, "left_stick_curve")
            layout.prop(prefs, "right_stick_curve")
            layout.prop(prefs, "show_hud")
            layout.prop(prefs, "invert_orbit_y")
            if prefs.navigation_mode == "ORBIT":
                layout.prop(prefs, "invert_pan_y")


classes = (
    GamepadViewBookmark,
    GamepadNavigationPreferences,
    VIEW3D_OT_gamepad_navigation,
    VIEW3D_OT_gamepad_view_action,
    VIEW3D_OT_gamepad_bookmark_save,
    VIEW3D_OT_gamepad_bookmark_recall,
    VIEW3D_OT_gamepad_bookmark_delete,
    VIEW3D_PT_gamepad_navigation,
)


addon_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.gamepad_view_bookmarks = CollectionProperty(
        type=GamepadViewBookmark
    )
    bpy.types.Scene.gamepad_bookmark_name = StringProperty(
        name="Bookmark Name", default=""
    )

    wm = bpy.context.window_manager
    keyconfig = wm.keyconfigs.addon
    if keyconfig:
        keymap = keyconfig.keymaps.new(name="3D View", space_type="VIEW_3D")
        item = keymap.keymap_items.new(
            "view3d.gamepad_navigation", "J", "PRESS", ctrl=True, shift=True
        )
        addon_keymaps.append((keymap, item))


def unregister():
    GamepadNavigationSession.stop()
    if bpy.app.timers.is_registered(gamepad_navigation_timer):
        bpy.app.timers.unregister(gamepad_navigation_timer)

    for keymap, item in addon_keymaps:
        keymap.keymap_items.remove(item)
    addon_keymaps.clear()

    del bpy.types.Scene.gamepad_bookmark_name
    del bpy.types.Scene.gamepad_view_bookmarks

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
