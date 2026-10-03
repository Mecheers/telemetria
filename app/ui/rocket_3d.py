from collections import deque
from typing import Optional

import numpy as np
from PyQt6 import QtGui
import pyqtgraph.opengl as gl


# ============================================================
# MESH HELPERS
# Todas las piezas se crean directamente en coordenadas locales
# definitivas. Así resetTransform() no pierde su posición original.
# ============================================================
def _lathe_mesh(profile, cols=64, cap_start=True, cap_end=True):
    """Crea una superficie de revolución a partir de [(z, radio), ...]."""
    profile = np.asarray(profile, dtype=np.float32)
    theta = np.linspace(0.0, 2.0 * np.pi, cols, endpoint=False, dtype=np.float32)
    ct, st = np.cos(theta), np.sin(theta)

    rings = []
    for z, radius in profile:
        rings.append(np.column_stack((radius * ct, radius * st, np.full(cols, z, dtype=np.float32))))
    verts = np.vstack(rings).astype(np.float32)

    faces = []
    rows = len(profile)
    for row in range(rows - 1):
        a0 = row * cols
        b0 = (row + 1) * cols
        for i in range(cols):
            j = (i + 1) % cols
            faces.append([a0 + i, a0 + j, b0 + j])
            faces.append([a0 + i, b0 + j, b0 + i])

    if cap_start and profile[0, 1] > 0:
        center_i = len(verts)
        verts = np.vstack((verts, [[0.0, 0.0, profile[0, 0]]])).astype(np.float32)
        for i in range(cols):
            j = (i + 1) % cols
            faces.append([center_i, j, i])

    if cap_end and profile[-1, 1] > 0:
        center_i = len(verts)
        verts = np.vstack((verts, [[0.0, 0.0, profile[-1, 0]]])).astype(np.float32)
        base = (rows - 1) * cols
        for i in range(cols):
            j = (i + 1) % cols
            faces.append([center_i, base + i, base + j])

    return gl.MeshData(vertexes=verts, faces=np.asarray(faces, dtype=np.int32))


def _ogive_profile(z0, length, radius, points=22):
    """Perfil de ogiva tangente: radio completo en la base y cero en la punta."""
    rho = (radius * radius + length * length) / (2.0 * radius)
    x = np.linspace(0.0, length, points, dtype=np.float32)
    # Fórmula clásica medida desde la punta. Aquí invertimos el eje para que
    # x=0 sea la base (radio=radius) y x=length sea la punta (radio=0).
    x_from_tip = length - x
    y = np.sqrt(np.maximum(0.0, rho * rho - (length - x_from_tip) ** 2)) + radius - rho
    y[0] = radius
    y[-1] = 0.0
    return [(z0 + float(v), float(r)) for v, r in zip(x, y)]


def _rotate_mesh_z(mesh, angle_deg):
    """Devuelve una copia del mesh rotada en Z, horneando la orientación."""
    verts = np.asarray(mesh.vertexes(), dtype=np.float32).copy()
    a = np.deg2rad(float(angle_deg))
    c, s = np.cos(a), np.sin(a)
    x = verts[:, 0].copy()
    y = verts[:, 1].copy()
    verts[:, 0] = c * x - s * y
    verts[:, 1] = s * x + c * y
    return gl.MeshData(vertexes=verts, faces=np.asarray(mesh.faces(), dtype=np.int32).copy())


def _fin_mesh(z_root0, z_root1, span, sweep, thickness, body_r):
    """Aleta trapezoidal barrida con espesor real."""
    # Plano local: X radial, Y tangencial, Z longitudinal.
    x0 = body_r * 0.94
    x1 = body_r + span
    z0 = z_root0
    z1 = z_root1
    z_tip0 = z0 + sweep
    z_tip1 = z1 - 0.20
    t = thickness / 2.0

    outline = np.array(
        [
            [x0, -t, z0],
            [x0, -t, z1],
            [x1, -t, z_tip1],
            [x1, -t, z_tip0],
            [x0, t, z0],
            [x0, t, z1],
            [x1, t, z_tip1],
            [x1, t, z_tip0],
        ],
        dtype=np.float32,
    )
    faces = np.array(
        [
            [0, 1, 2], [0, 2, 3],
            [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1],
            [1, 5, 6], [1, 6, 2],
            [2, 6, 7], [2, 7, 3],
            [3, 7, 4], [3, 4, 0],
        ],
        dtype=np.int32,
    )
    return gl.MeshData(vertexes=outline, faces=faces)


def _sector_shell(z0, z1, radius, a0_deg, a1_deg, cols=10):
    """Panel superficial curvo para detalles de pintura/checkerboard."""
    angles = np.linspace(np.deg2rad(a0_deg), np.deg2rad(a1_deg), cols, dtype=np.float32)
    verts = []
    for z in (z0, z1):
        for a in angles:
            verts.append([radius * np.cos(a), radius * np.sin(a), z])
    faces = []
    for i in range(cols - 1):
        faces += [[i, i + 1, cols + i + 1], [i, cols + i + 1, cols + i]]
    return gl.MeshData(vertexes=np.asarray(verts, dtype=np.float32), faces=np.asarray(faces, dtype=np.int32))


def _translate_mesh_z(mesh, offset):
    """Desplaza una malla en Z horneando la traslación en sus vértices."""
    verts = np.asarray(mesh.vertexes(), dtype=np.float32).copy()
    verts[:, 2] += float(offset)
    return gl.MeshData(
        vertexes=verts,
        faces=np.asarray(mesh.faces(), dtype=np.int32).copy(),
    )


class Rocket3DWidget(gl.GLViewWidget):
    """Vista 3D del vehículo con modelo procedural detallado y cámara de seguimiento."""

    def __init__(self):
        super().__init__()
        self.setCameraPosition(distance=18, elevation=20, azimuth=45)
        try:
            self.setBackgroundColor((1, 5, 8, 255))
        except Exception:
            pass

        self.grid = gl.GLGridItem()
        self.grid.setSize(90, 90, 1)
        self.grid.setSpacing(2, 2, 1)
        self.addItem(self.grid)

        self.axis = gl.GLAxisItem()
        self.axis.setSize(x=6, y=6, z=6)
        self.addItem(self.axis)

        self.rocket_parts = []
        self.flame_parts = []
        self.body_len = 4.5
        self.body_r = 0.31
        # La cara inferior de la tobera queda exactamente en Z=0.
        # El modelo completo se construye desde el suelo hacia arriba y rota
        # alrededor de ese punto de apoyo, evitando que atraviese la grilla.
        self._ground_offset = 3.23
        self._rocket_center_z = 3.35
        self._build_rocket()

        self.trail_pts = deque(maxlen=4000)
        self.trail = gl.GLLinePlotItem(pos=np.zeros((2, 3), dtype=np.float32), width=1, antialias=True)
        self.addItem(self.trail)

        self.x = self.y = self.z = 0.0
        self.control_mode = "AUTO"
        self._telemetry_attitude = (0.0, 0.0, 0.0)
        self._manual_attitude = (0.0, 0.0, 0.0)
        self.autofit = True
        self._fit_every = 1
        self._fit_counter = 0
        self._min_dist = 8.0
        self._max_dist = 450.0
        self._center_alpha = 0.25
        self._cx = self._cy = 0.0
        self._cz = self._rocket_center_z
        self.chase_cam = True
        self._az_alpha = 0.18
        self._az_smoothed = float(self.opts.get("azimuth", 45))
        self._tile = 10.0
        self._grid_snap_x = None
        self._grid_snap_y = None
        self._update_infinite_grid()
        self._apply_attitude(0.0, 0.0, 0.0, update_camera=False)

    def _add_mesh(self, mesh, color, smooth=True, shader="shaded", moving=True):
        # Se hornea el desplazamiento vertical en todas las piezas del vehículo.
        # De esta forma, la base de la tobera es el origen local Z=0.
        mesh = _translate_mesh_z(mesh, self._ground_offset)
        item = gl.GLMeshItem(meshdata=mesh, smooth=smooth, shader=shader, color=color)
        self.addItem(item)
        if moving:
            self.rocket_parts.append(item)
        return item

    def _build_rocket(self):
        r = self.body_r
        z_bottom = -2.25
        z_top = 2.25

        # Fuselaje principal, dividido en secciones para dar sensación de etapas.
        self.part_body = self._add_mesh(
            _lathe_mesh([(z_bottom, r), (-0.15, r), (z_top, r)], cols=72),
            (0.78, 0.81, 0.83, 1.0),
        )

        # Hombro y nariz ogival.
        nose_base = z_top
        shoulder = _lathe_mesh([(nose_base - 0.08, r * 1.01), (nose_base + 0.08, r * 1.01)], cols=72)
        self._add_mesh(shoulder, (0.15, 0.17, 0.19, 1.0))
        ogive = _lathe_mesh(_ogive_profile(nose_base, 1.38, r, points=28), cols=72, cap_start=True, cap_end=False)
        self.part_nose = self._add_mesh(ogive, (0.92, 0.93, 0.94, 1.0))

        # Boat-tail y tobera escalonada.
        boat = _lathe_mesh([(z_bottom, r), (z_bottom - 0.34, r * 0.70), (z_bottom - 0.48, r * 0.60)], cols=64)
        self._add_mesh(boat, (0.27, 0.29, 0.31, 1.0))
        nozzle = _lathe_mesh(
            [(z_bottom - 0.46, r * 0.48), (z_bottom - 0.72, r * 0.40), (z_bottom - 0.93, r * 0.55)],
            cols=64,
        )
        self.part_noz = self._add_mesh(nozzle, (0.08, 0.09, 0.10, 1.0))
        nozzle_lip = _lathe_mesh([(z_bottom - 0.91, r * 0.57), (z_bottom - 0.98, r * 0.57)], cols=64)
        self._add_mesh(nozzle_lip, (0.35, 0.37, 0.39, 1.0))

        # Anillos estructurales y banda de identificación.
        for zc, width, color, scale in [
            (-1.55, 0.08, (0.12, 0.14, 0.16, 1.0), 1.018),
            (-0.15, 0.07, (0.12, 0.14, 0.16, 1.0), 1.018),
            (1.05, 0.30, (0.72, 0.08, 0.08, 1.0), 1.022),
            (1.92, 0.07, (0.12, 0.14, 0.16, 1.0), 1.018),
        ]:
            ring = _lathe_mesh([(zc - width / 2, r * scale), (zc + width / 2, r * scale)], cols=72)
            self._add_mesh(ring, color)

        # Paneles negros alternados alrededor del fuselaje (detalle visual tipo cohete real).
        panel_r = r * 1.026
        for a0 in (0, 180):
            self._add_mesh(_sector_shell(0.18, 0.88, panel_r, a0, a0 + 55, cols=14), (0.035, 0.045, 0.052, 1.0))
        for a0 in (90, 270):
            self._add_mesh(_sector_shell(-1.15, -0.45, panel_r, a0, a0 + 48, cols=14), (0.035, 0.045, 0.052, 1.0))

        # Cuatro aletas aerodinámicas barridas.
        self.fins = []
        md_fin = _fin_mesh(z_bottom + 0.12, z_bottom + 1.18, span=0.64, sweep=0.25, thickness=0.055, body_r=r)
        for k in range(4):
            # La rotación se hornea en los vértices. Así resetTransform() no
            # borra la orientación individual de cada aleta.
            fin = self._add_mesh(_rotate_mesh_z(md_fin, k * 90.0), (0.12, 0.14, 0.16, 1.0), smooth=False)
            self.fins.append(fin)

        # Pequeñas aletas de control delanteras.
        md_canard = _fin_mesh(1.34, 1.74, span=0.24, sweep=0.08, thickness=0.032, body_r=r)
        for k in range(4):
            self._add_mesh(
                _rotate_mesh_z(md_canard, 45.0 + k * 90.0),
                (0.30, 0.32, 0.34, 1.0),
                smooth=False,
            )

        # Llama en tres capas para mayor profundidad.
        flame_profiles = [
            ([(z_bottom - 0.98, r * 0.37), (z_bottom - 1.72, r * 0.18), (z_bottom - 2.28, 0.0)], (1.0, 0.22, 0.02, 0.38)),
            ([(z_bottom - 1.00, r * 0.25), (z_bottom - 1.58, r * 0.12), (z_bottom - 2.02, 0.0)], (1.0, 0.68, 0.05, 0.62)),
            ([(z_bottom - 1.02, r * 0.14), (z_bottom - 1.42, r * 0.07), (z_bottom - 1.72, 0.0)], (0.78, 0.92, 1.0, 0.82)),
        ]
        for profile, color in flame_profiles:
            flame = self._add_mesh(_lathe_mesh(profile, cols=48, cap_start=True, cap_end=False), color, moving=False)
            flame.setVisible(False)
            self.flame_parts.append(flame)
        self.flame = self.flame_parts[0]  # compatibilidad con código existente

    def set_control_mode(self, mode: str):
        mode = str(mode).upper()
        self.control_mode = "MANUAL" if mode == "MANUAL" else "AUTO"
        attitude = self._manual_attitude if self.control_mode == "MANUAL" else self._telemetry_attitude
        self._apply_attitude(*attitude, update_camera=self.control_mode == "AUTO")

    def set_manual_attitude(self, roll_deg: float, pitch_deg: float, yaw_deg: float):
        self._manual_attitude = (float(roll_deg), float(pitch_deg), float(yaw_deg))
        if self.control_mode == "MANUAL":
            # No se reajusta la cámara: el usuario puede orbitar y hacer zoom con el mouse.
            self._apply_attitude(*self._manual_attitude, update_camera=False)

    def set_autofit(self, enabled: bool):
        self.autofit = bool(enabled)

    def set_chase_cam(self, enabled: bool):
        self.chase_cam = bool(enabled)

    def _snap(self, v: float, tile: float) -> float:
        return round(v / tile) * tile

    def _update_infinite_grid(self):
        gx = self._snap(self.x, self._tile)
        gy = self._snap(self.y, self._tile)
        if self._grid_snap_x == gx and self._grid_snap_y == gy:
            return
        self._grid_snap_x, self._grid_snap_y = gx, gy
        self.grid.resetTransform()
        self.grid.translate(gx, gy, 0.0)
        self.axis.resetTransform()
        self.axis.translate(gx, gy, 0.1)

    @staticmethod
    def _wrap180(a: float) -> float:
        while a > 180:
            a -= 360
        while a < -180:
            a += 360
        return a

    def _smooth_angle(self, current: float, target: float, alpha: float) -> float:
        return current + alpha * self._wrap180(target - current)

    def _auto_fit_camera(self, yaw_deg: Optional[float] = None):
        center = np.array([self.x, self.y, self.z + self._rocket_center_z], dtype=float)
        if self.trail_pts:
            pts = np.array(self.trail_pts, dtype=float)
            diag = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
        else:
            diag = 1.0
        dist = max(self._min_dist, min(self._max_dist, max(1.0, diag * 0.60) * 3.0))

        a = self._center_alpha
        self._cx = (1 - a) * self._cx + a * center[0]
        self._cy = (1 - a) * self._cy + a * center[1]
        self._cz = (1 - a) * self._cz + a * center[2]
        self.opts["center"] = QtGui.QVector3D(float(self._cx), float(self._cy), float(self._cz))

        az = self.opts.get("azimuth", 45)
        if self.chase_cam and yaw_deg is not None:
            self._az_smoothed = self._smooth_angle(self._az_smoothed, float(yaw_deg) + 180.0, self._az_alpha)
            az = self._az_smoothed
        self.setCameraPosition(distance=dist, elevation=self.opts.get("elevation", 20), azimuth=az)
        self.update()

    def reset_scene(self):
        self.trail_pts.clear()
        self.x = self.y = self.z = 0.0
        self.trail.setData(pos=np.zeros((2, 3), dtype=np.float32))
        for item in self.rocket_parts + self.flame_parts:
            item.resetTransform()
        self.set_flame(False)
        self._fit_counter = 0
        self._cx = self._cy = 0.0
        self._cz = self._rocket_center_z
        self._az_smoothed = float(self.opts.get("azimuth", 45))
        self._grid_snap_x = self._grid_snap_y = None
        self._update_infinite_grid()
        attitude = self._manual_attitude if self.control_mode == "MANUAL" else self._telemetry_attitude
        self._apply_attitude(*attitude, update_camera=False)
        self._auto_fit_camera(yaw_deg=0.0)

    def reset_trail_only(self):
        self.trail_pts.clear()
        self.trail.setData(pos=np.zeros((2, 3), dtype=np.float32))

    def _apply_attitude(self, roll_deg: float, pitch_deg: float, yaw_deg: float, update_camera: bool):
        moving = self.rocket_parts + self.flame_parts
        for item in moving:
            item.resetTransform()
            item.rotate(yaw_deg, 0, 0, 1)
            item.rotate(pitch_deg, 0, 1, 0)
            item.rotate(roll_deg, 1, 0, 0)
            item.translate(self.x, self.y, self.z)

        if update_camera and self.autofit:
            self._fit_counter += 1
            if self._fit_counter >= self._fit_every:
                self._fit_counter = 0
                self._auto_fit_camera(yaw_deg=yaw_deg)

    def set_attitude(self, roll_deg: float, pitch_deg: float, yaw_deg: float):
        self._telemetry_attitude = (float(roll_deg), float(pitch_deg), float(yaw_deg))
        if self.control_mode == "AUTO":
            self._apply_attitude(*self._telemetry_attitude, update_camera=True)

    def set_position_estimated(self, x: float, y: float, z: float, yaw_deg: Optional[float] = None):
        self.x, self.y, self.z = float(x), float(y), float(z)
        self._update_infinite_grid()
        self.trail_pts.append((self.x, self.y, self.z))
        pts = np.array(self.trail_pts, dtype=np.float32)
        if pts.shape[0] < 2:
            pts = np.array([[self.x, self.y, self.z], [self.x, self.y, self.z]], dtype=np.float32)
        self.trail.setData(pos=pts)

        if self.control_mode == "AUTO" and self.autofit:
            self._fit_counter += 1
            if self._fit_counter >= self._fit_every:
                self._fit_counter = 0
                self._auto_fit_camera(yaw_deg=yaw_deg)

    def set_flame(self, on: bool):
        for flame in self.flame_parts:
            try:
                flame.setVisible(bool(on))
            except Exception:
                pass
