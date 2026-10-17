bl_info = {
    "name": "8BitDo / XInput Viewport Navigation",
    "author": "Aaron Fang, OpenAI Codex",
    "version": (1, 0, 0),
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
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from mathutils import Quaternion, Vector


ADDON_ID = __package__ or __name__
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
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


def axis_value(raw, deadzone):
    value = max(-1.0, min(1.0, raw / 32767.0))
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    scaled = (magnitude - deadzone) / (1.0 - deadzone)
    return math.copysign(scaled, value)


def trigger_value(raw, threshold):
    value = raw / 255.0
    if value <= threshold:
        return 0.0
    return (value - threshold) / (1.0 - threshold)


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
    stick_deadzone: FloatProperty(
        name="Stick Deadzone",
        default=0.16,
        min=0.0,
        max=0.8,
        subtype="FACTOR",
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
    invert_orbit_y: BoolProperty(name="Invert Right Stick Y", default=False)
    invert_pan_y: BoolProperty(name="Invert Left Stick Y", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "navigation_mode", expand=True)
        layout.prop(self, "controller_index")
        layout.prop(self, "stick_deadzone")
        layout.prop(self, "trigger_deadzone")
        layout.separator()
        layout.prop(self, "orbit_speed")
        layout.prop(self, "pan_speed")
        layout.prop(self, "zoom_speed")
        layout.prop(self, "fly_speed")
        layout.prop(self, "fly_look_speed")
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
        cls.active = True
        if not bpy.app.timers.is_registered(gamepad_navigation_timer):
            bpy.app.timers.register(gamepad_navigation_timer, first_interval=0.01)

    @classmethod
    def stop(cls):
        cls.active = False
        cls.connected = False
        cls.lb_was_down = False
        try:
            cls.area.tag_redraw()
        except (AttributeError, ReferenceError):
            pass
        cls.area = None
        cls.rv3d = None
        cls.orbit_pivot = None

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
            cls.effective_mode = prefs.navigation_mode
            return 0.05

        gamepad = state.Gamepad
        if gamepad.wButtons & XINPUT_GAMEPAD_BACK:
            cls.stop()
            return None

        now = time.perf_counter()
        dt = min(now - cls.last_time, 0.05)
        cls.last_time = now

        lx = axis_value(gamepad.sThumbLX, prefs.stick_deadzone)
        ly = axis_value(gamepad.sThumbLY, prefs.stick_deadzone)
        rx = axis_value(gamepad.sThumbRX, prefs.stick_deadzone)
        ry = axis_value(gamepad.sThumbRY, prefs.stick_deadzone)
        lt = trigger_value(gamepad.bLeftTrigger, prefs.trigger_deadzone)
        rt = trigger_value(gamepad.bRightTrigger, prefs.trigger_deadzone)

        if prefs.invert_pan_y:
            ly = -ly
        if prefs.invert_orbit_y:
            ry = -ry

        lb_down = bool(gamepad.wButtons & XINPUT_GAMEPAD_LEFT_SHOULDER)
        if lb_down and not cls.lb_was_down:
            cls.lb_press_time = now
        elif not lb_down and cls.lb_was_down:
            if now - cls.lb_press_time < LB_TAP_SECONDS:
                prefs.navigation_mode = (
                    "FLY" if prefs.navigation_mode == "ORBIT" else "ORBIT"
                )
        cls.lb_was_down = lb_down

        previous_mode = cls.effective_mode
        temporary_mode = lb_down or bool(gamepad.wButtons & TEMPORARY_MODE_BUTTONS)
        cls.effective_mode = prefs.navigation_mode
        if temporary_mode:
            cls.effective_mode = "FLY" if prefs.navigation_mode == "ORBIT" else "ORBIT"

        if previous_mode != "ORBIT" and cls.effective_mode == "ORBIT":
            cls.focus_orbit_view()
        elif cls.effective_mode == "ORBIT" and cls.orbit_pivot is None:
            cls.focus_orbit_view()

        rb_down = bool(gamepad.wButtons & XINPUT_GAMEPAD_RIGHT_SHOULDER)
        speed_scale = 1.0
        if rb_down and cls.effective_mode == "ORBIT":
            speed_scale *= 3.0

        rv3d = cls.rv3d
        rotation = rv3d.view_rotation.copy()

        if cls.effective_mode == "FLY":
            distance = max(rv3d.view_distance, 0.001)

            if rx or ry:
                camera_position = (
                    rv3d.view_location
                    + rotation @ Vector((0.0, 0.0, distance))
                )
                yaw = Quaternion(
                    (0.0, 0.0, 1.0),
                    -rx * prefs.fly_look_speed * dt * speed_scale,
                )
                pitch_axis = rotation @ Vector((1.0, 0.0, 0.0))
                pitch = Quaternion(
                    pitch_axis,
                    ry * prefs.fly_look_speed * dt * speed_scale,
                )
                rotation = (pitch @ yaw @ rotation).normalized()
                rv3d.view_rotation = rotation
                rv3d.view_location = (
                    camera_position
                    - rotation @ Vector((0.0, 0.0, distance))
                )

            vertical = rt - lt
            if lx or ly or vertical:
                right = rotation @ Vector((1.0, 0.0, 0.0))
                forward = rotation @ Vector((0.0, 0.0, -1.0))
                movement = right * lx + forward * ly + Vector((0.0, 0.0, vertical))
                if rb_down:
                    movement.z = 0.0
                rv3d.view_location += movement * prefs.fly_speed * dt * speed_scale
        else:
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
        if prefs and prefs.navigation_mode == "FLY":
            box.label(text="Hold RB: Lock world height")
        else:
            box.label(text="RB: Fast")
        box.label(text="Back: Stop")

        if prefs:
            layout.separator()
            layout.prop(prefs, "controller_index")
            layout.prop(prefs, "orbit_speed")
            if prefs.navigation_mode == "FLY":
                layout.prop(prefs, "fly_speed")
                layout.prop(prefs, "fly_look_speed")
            else:
                layout.prop(prefs, "pan_speed")
                layout.prop(prefs, "zoom_speed")
            layout.prop(prefs, "invert_orbit_y")
            if prefs.navigation_mode == "ORBIT":
                layout.prop(prefs, "invert_pan_y")


classes = (
    GamepadNavigationPreferences,
    VIEW3D_OT_gamepad_navigation,
    VIEW3D_PT_gamepad_navigation,
)


addon_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

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

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
