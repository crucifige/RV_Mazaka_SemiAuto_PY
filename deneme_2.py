import sys
import threading
import time
import geopandas as gpd
from shapely.geometry import Point
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QFileDialog
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Circle
import numpy as np
from PyQt5.QtCore import QTimer, pyqtSlot, QMutex, QMutexLocker
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QScrollArea
from PyQt5.QtGui import QPainter, QPen, QBrush
from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from uiMain import Ui_MainWindow  # Assuming uiMain.py is in the same directory
import pandas as pd
import math

def parse_c3d_file_to_dataframe(file_path):
    data = {
        'id': [],
        'northing': [],
        'easting': [],
        'altitude': [],
        'ground_altitude': [],
        'yaw': [],
        'object_type': []
    }

    with open(file_path, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if line and not line.startswith('}\n}') and not line.startswith('"') and len(line) > 1 and line[1].isdigit():
            parts = line.split()
            try:
                data['id'].append(parts[0])
                data['northing'].append(float(parts[1]))
                data['easting'].append(float(parts[2]))
                data['altitude'].append(float(parts[3]))
                data['ground_altitude'].append(float(parts[4]))
                data['yaw'].append(float(parts[5]))
                data['object_type'].append('HEA160-3.3')
            except (IndexError, ValueError):
                continue
    df = pd.DataFrame(data)
    return df

def get_scaled_triangle_coords(x, y, heading, vehicle_length=3004.71/1000, vehicle_width=880.97/1000):
    latitude_scale = 1 / 111320
    longitude_scale = 1 / (111320 * np.cos(np.radians(y)))

    local_coords = [
        (0, vehicle_length * latitude_scale / 2),
        (-vehicle_width * longitude_scale / 2, -vehicle_length * latitude_scale / 2),
        (vehicle_width * longitude_scale / 2, -vehicle_length * latitude_scale / 2)
    ]

    rotated_coords = [
        (
            x + (math.cos(heading) * vx - math.sin(heading) * vy),
            y + (math.sin(heading) * vx + math.cos(heading) * vy)
        )
        for vx, vy in local_coords
    ]

    return rotated_coords

class Joystick(QWidget):
    joystick_moved = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super(Joystick, self).__init__(parent)
        self.setFixedSize(150, 150)
        self.center = QPointF(self.width() / 2, self.height() / 2)
        self.knob_position = self.center
        self.radius = 60
        self.knob_radius = 20
        self.is_dragging = False
        self.current_x = 0
        self.current_y = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.emit_joystick_movement)
        self.timer.start(50)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(Qt.lightGray))
        painter.setPen(QPen(Qt.black, 2))
        painter.drawEllipse(self.center, self.radius, self.radius)
        painter.setBrush(QBrush(Qt.red))
        painter.setPen(QPen(Qt.black, 1))
        painter.drawEllipse(self.knob_position, self.knob_radius, self.knob_radius)

    def mousePressEvent(self, event):
        if (event.pos() - self.knob_position).manhattanLength() <= self.knob_radius:
            self.is_dragging = True

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            delta = event.pos() - self.center
            distance = math.sqrt(delta.x()**2 + delta.y()**2)

            if distance > self.radius:
                delta *= self.radius / distance

            self.knob_position = self.center + delta
            self.update()

            self.current_x = delta.x() / self.radius
            self.current_y = -delta.y() / self.radius

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        self.knob_position = self.center
        self.current_x = 0
        self.current_y = 0
        self.update()

    def emit_joystick_movement(self):
        if self.current_x != 0 or self.current_y != 0:
            self.joystick_moved.emit(self.current_x, self.current_y)

class MainApp(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainApp, self).__init__(parent)
        self.setupUi(self)
        self.colors = {'red': '#B24A3B', 'green': '#2E765E', 'yellow': '#FDD05A'}
        self.vValScale = [100, 50, 10, 5, 1, 0.1, 0.01]
        self.zoomScale = 5.0
        self.pbOpen.clicked.connect(self.fnOpenFile)
        self.pushButton_2.setEnabled(False)
        self.pushButton_2.clicked.connect(self.process_current_point)
        self.pushButton_3.clicked.connect(self.skip_current_point)

    def openFileNameDialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileName()", "", "c3d Files (*.c3d)", options=options)
        if fileName:
            self.data = parse_c3d_file_to_dataframe(fileName)
            self.row_manager = RowManager(self.scrollArea, self.wdScrollArea)
            self.completedJobs = []
            for i in range(len(self.data['id'])):
                self.row_manager.add(order=self.data['id'][i], x=self.data['easting'][i], y=self.data['northing'][i], z=self.data['altitude'][i])
                self.completedJobs.append(0)
            self.startProject()

    def startProject(self):
        geometry = [Point(xy) for xy in zip(self.data['easting'], self.data['northing'])]
        self.gdf = gpd.GeoDataFrame(self.data, geometry=geometry)
        self.gdf.set_crs(epsg=32630, inplace=True)

        self.main_layout = QVBoxLayout(self.grMain)
        self.zoom_layout = QVBoxLayout(self.grZoom)
        self.main_canvas = MatplotlibCanvas(self)
        self.zoom_canvas = ZoomCanvas(self)

        self.main_layout.addWidget(self.main_canvas)
        self.zoom_layout.addWidget(self.zoom_canvas)

        self.joystick = Joystick(self)
        self.joystick_layout = QVBoxLayout(self.wdJoystick)

        self.joystick_layout.addWidget(self.joystick)
        self.info_label = QLabel("X: 0, Y: 0", self)
        self.joystick_layout.addWidget(self.info_label)
        self.joystick.joystick_moved.connect(self.update_info)

        self.vehicle_position = Point(35.3847, 38.6993)
        self.current_index = 0
        self.mutex = QMutex()
        self.ui_update_timer = QTimer(self)
        self.ui_update_timer.timeout.connect(self.plot_gdf)
        self.ui_update_timer.start(20)
        self.updateJobs()

    def updateJobs(self):
        for i in range(0, len(self.completedJobs)):
            if self.completedJobs[i] == 0:
                self.current_index = i
                self.row_manager.update(i, 'y')
                break

    def process_current_point(self):
        if self.current_index < len(self.completedJobs):
            self.completedJobs[self.current_index] = 1
            self.row_manager.update(self.current_index, 'g')
            self.current_index += 1
            self.updateJobs()

    def skip_current_point(self):
        if self.current_index < len(self.completedJobs):
            self.completedJobs[self.current_index] = -1
            self.row_manager.update(self.current_index, 'r')
            self.current_index += 1
            self.updateJobs()
    def fnOpenFile(self):
        self.openFileNameDialog()
    def update_info(self, x, y):
        self.info_label.setText(f"X: {x:.2f}, Y: {y:.2f}")
        self.move_vehicle(x, y, 0.000001)

    def plot_gdf(self):
        with QMutexLocker(self.mutex):
            self.main_canvas.plot(self.gdf, self.vehicle_position, self.zoomScale, self.current_index)
            self.zoom_canvas.plot(self.gdf, self.vehicle_position, self.zoomScale)

    def move_vehicle(self, dx, dy, scale):
        with QMutexLocker(self.mutex):
            self.vehicle_position = Point(self.vehicle_position.x + scale * dx, self.vehicle_position.y + scale * dy)
            if dx != 0 or dy != 0:
                self.main_canvas.heading = math.atan2(dy, dx) - math.pi / 2

class MatplotlibCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        super(MatplotlibCanvas, self).__init__(self.fig)
        self.fig.subplots_adjust(left=0.07, right=0.95, top=0.95, bottom=0.05)
        self.fig.patch.set_alpha(0)
        self.heading = 0

    def plot(self, gdf, vehicle_position, zoomScale, current_index):
        self.ax.clear()
        for i, point in enumerate(gdf.geometry):
            color = 'yellow' if i == current_index else 'red'
            self.ax.add_patch(Circle((point.x, point.y), radius=0.00001, edgecolor=color, linewidth=2))
            self.ax.text(point.x, point.y, 'x', color=color, fontsize=12, ha='center', va='center')

        triangle = Polygon(get_scaled_triangle_coords(vehicle_position.x, vehicle_position.y, self.heading), closed=True, color='black')
        self.ax.add_patch(triangle)
        msf = 50 / 111320
        self.ax.set_xlim(vehicle_position.x - msf, vehicle_position.x + msf)
        self.ax.set_ylim(vehicle_position.y - msf, vehicle_position.y + msf)
        self.ax.set_aspect('equal', 'box')
        self.ax.grid(visible=True, color="#98D7C2", linestyle="--", linewidth=0.5)
        self.draw()

class ZoomCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig, self.ax = plt.subplots(figsize=(5, 5))
        super(ZoomCanvas, self).__init__(self.fig)
        self.fig.patch.set_alpha(0)

    def plot(self, gdf, vehicle_position, zoomScale):
        self.ax.clear()
        for point in gdf.geometry:
            self.ax.text(point.x, point.y, 'x', color='red', fontsize=12, ha='center', va='center')

        triangle = Polygon(get_scaled_triangle_coords(vehicle_position.x, vehicle_position.y, 0, 1, 0.5), closed=True, color='black')
        self.ax.add_patch(triangle)

        zoom_factor = zoomScale / 111320
        self.ax.set_xlim(vehicle_position.x - zoom_factor, vehicle_position.x + zoom_factor)
        self.ax.set_ylim(vehicle_position.y - zoom_factor, vehicle_position.y + zoom_factor)
        self.ax.set_aspect('equal', 'box')
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw()

class RowManager:
    def __init__(self, scroll_area, wdScrollArea):
        self.scroll_area = scroll_area
        self.container_widget = wdScrollArea
        self.container_layout = QVBoxLayout(self.container_widget)
        self.container_layout.setSpacing(5)
        self.container_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.container_widget)
        self.scroll_area.setWidgetResizable(True)
        self.rows = []

    def add(self, order, x, y, z):
        row_widget = QWidget()
        row_widget.setFixedSize(400, 20)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        lbl_order = QLabel(str(order))
        lbl_order.setFixedWidth(40)
        lbl_x = QLabel(str(x))
        lbl_x.setFixedWidth(120)
        lbl_y = QLabel(str(y))
        lbl_y.setFixedWidth(120)
        lbl_z = QLabel(str(z))
        lbl_z.setFixedWidth(120)
        lbl_order.setStyleSheet("font: 12pt;")
        lbl_x.setStyleSheet("font: 12pt;")
        lbl_y.setStyleSheet("font: 12pt;")
        lbl_z.setStyleSheet("font: 12pt;")

        row_layout.addWidget(lbl_order)
        row_layout.addWidget(lbl_x)
        row_layout.addWidget(lbl_y)
        row_layout.addWidget(lbl_z)

        self.container_layout.addWidget(row_widget)
        self.rows.append({"widget": row_widget, "labels": [lbl_order, lbl_x, lbl_y, lbl_z]})

    def update(self, index, color=None):
        if index < 0 or index >= len(self.rows):
            raise IndexError("Invalid row index.")

        row = self.rows[index]
        labels = row["labels"]

        if color == 'y':
            for label in labels: label.setStyleSheet("font: 12pt; color: rgb(255, 255, 0);")
        if color == 'r':
            for label in labels: label.setStyleSheet("font: 12pt; color: rgb(255, 0, 0);")
        if color == 'g':
            for label in labels: label.setStyleSheet("font: 12pt; color: rgb(0, 255, 0);")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec_())
