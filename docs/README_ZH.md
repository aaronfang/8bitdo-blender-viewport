# 8BitDo Blender Viewport 中文帮助

本插件通过 Windows XInput 读取 8BitDo 或其他兼容手柄，在 Blender 4.5
视窗中提供 Fly、Orbit 和 Ground 导航。手柄导航在后台定时器中运行，不会
占用 Blender 的 modal 事件链，因此可以同时雕刻、移动物体或编辑点线面。

## 安装

1. 从 GitHub Release 下载 `8bitdo_blender_viewport.py`。
2. Blender 打开 **编辑 > 偏好设置 > 插件**。
3. 选择 **从磁盘安装**并启用插件。
4. 将手柄切换到 XInput/X 模式；可用 Windows 的 `joy.cpl` 检查输入。
5. 在 3D 视窗按 `N`，进入 **View > Gamepad Navigation**，点击 **Start**。

## 控制映射

| 输入 | Fly | Orbit |
| --- | --- | --- |
| 左摇杆 | 左右横移、前进后退 | 平移视窗 |
| 右摇杆 | 原地观察 | 围绕当前枢轴旋转 |
| LT / RT | 下降 / 上升 | 缩小 / 放大 |
| 短按 LB | 永久切换 Fly / Orbit | 永久切换 Fly / Orbit |
| 按住 LB | 临时使用 Orbit | 临时使用 Fly |
| 按住 RB | 锁定世界 Z 高度 | 3 倍导航速度 |
| L3 / R3 | 临时使用相反模式 | 临时使用相反模式 |
| 十字键上 / 下 | 调整速度档位 | 调整速度档位 |
| A / B | 聚焦目标 / 朝向目标 | 聚焦目标 / 朝向目标 |
| X / Y | Ground 模式 / 校正地平线 | Ground 模式 / 校正地平线 |
| 十字键左 / 右 | 上一个 / 下一个视图 | 上一个 / 下一个视图 |
| Back | 停止手柄导航 | 停止手柄导航 |

标准 XInput 不会把 8BitDo 的 P1/P2 背键作为独立按钮暴露。需要在 8BitDo
Ultimate Software 中把 P1/P2 映射为 L3/R3。

## Fly 和 Orbit 参数

| 参数 | 作用 |
| --- | --- |
| Fly Move Speed | Fly 基础移动速度，单位为 Blender 单位/秒。 |
| Fly Look Speed | 右摇杆观察角速度。 |
| Fly Acceleration | 推动摇杆后达到目标移动速度的快慢。 |
| Fly Damping | 松开摇杆后停止残余移动的快慢。 |
| Look Response | 右摇杆转动达到目标角速度的快慢。 |
| Orbit Speed | Orbit 旋转角速度。 |
| Pan Speed | Orbit 平移速度，相对于当前 `view_distance`。 |
| Zoom Speed | Orbit 指数缩放速度。 |
| View Transition | 聚焦、朝向、历史、书签和地平线校正动画时长。 |

## 大场景速度

### Scene Scale Speed

根据启动时缓存的场景包围盒对角线自动放大 Fly 速度。适合在不同尺度的
`.blend` 文件中复用相同设置。它不会每帧重新遍历场景。

### Adaptive Surface Speed

沿当前观察方向发射射线，只在接近可见表面时逐渐减速：

| 参数 | 作用 |
| --- | --- |
| Adaptive Start Distance | 开始减速的表面距离，单位为 Blender 单位。想更靠近地面才减速时，应调低此值。 |
| Adaptive Minimum Speed | 到达表面时保留的基础速度比例；`0.05` 表示 5%。 |
| Adaptive Curve | 越大越晚减速，并把减速集中在更靠近表面的位置。 |

同时开启 Scene Scale 与 Adaptive 时，进入减速区域后 Scene Scale 倍率会
逐渐回落到 `1x`，然后 Adaptive 继续降到最低速度。这样大场景倍率不会抵消
近处减速。

HUD 中的 `Surface 当前距离 / 开始距离`、`Scene` 和 `Adaptive` 可以用于直接
观察速度计算结果。

## Horizon Stabilization

Horizon Stabilization 会逐渐消除视角的侧向滚转，让世界 Z 轴保持为“上”。
它保留当前观察方向和俯仰角，不会强制把镜头拉回水平。长时间自由飞行后画面
倾斜时很有用。`Horizon Strength` 控制回正速度；Y 键执行一次平滑校正。

## Ground 模式

| 参数 | 作用 |
| --- | --- |
| Ground Eye Height | 观察点在地面上方的高度。 |
| Maximum Step | 一次地面更新允许跨越的最大向上高度差；超过时视为不可攀爬。 |
| Ground Probe Distance | 向下寻找可行走表面的最大距离；找不到时保持当前高度。 |
| Maximum Slope | 可作为地面的最大坡度。 |
| Collision Avoidance | 使用前向射线避免穿墙。 |
| Collision Radius | 观察点与墙面之间保留的安全距离。 |

## Dynamic View Clipping

根据场景尺寸和移动速度调整视窗的近裁剪与远裁剪，减少大场景中远处消失或
近处被切掉的问题。停止手柄导航时会恢复原始 `Clip Start/End`。

## HUD

- **Viewport Status**：模式、连接状态、实际速度、速度档、Scene/Adaptive
  倍率、表面距离以及 HEIGHT LOCK、GROUND、HORIZON、DYNAMIC CLIP 状态。
- **Control Help**：在视窗左下角显示按键映射。

两项可以分别关闭，并且只在手柄导航运行时显示。N Panel 不再重复显示大段
按键说明。

## Orbit 枢轴优先级

1. 最近一次雕刻笔刷落点。
2. 编辑模式已选点、边或面的中心。
3. 物体模式所选物体的整体包围盒中心。
4. 当前视窗焦点。

切换模式不会改变当前画面。停止插件时也会在保持观察位置和朝向不变的前提下，
重建适合 Blender 原生鼠标导航的焦点。
