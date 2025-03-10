import sys, threading, socket, time, math, serial
import geopandas as gpd
from shapely.geometry import Point
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QFileDialog, QMessageBox
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
import numpy as np
from PyQt5.QtCore import QTimer, pyqtSlot, QMutex, QMutexLocker, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QScrollArea
from PyQt5.QtGui import QPainter, QPen, QBrush, QPalette, QColor
from PyQt5.QtCore import QThread, Qt, QPointF
from uiMain import Ui_MainWindow  # Assuming uiMain.py is in the same directory
import pandas as pd
# pyuic5 ui/ui_RV24005.ui -o uiMain.py
# b'$GPCHC,2342,210026.10,0.00,0.44,-0.13,0.35,-0.05,0.02,0.0023,0.0078,1.0002,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*64\r\n'
# b'$GPCHC,2342,210026.15,0.00,0.43,-0.24,0.33,-0.04,0.02,0.0037,0.0075,0.9999,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*6E\r\n$GPCHC,2342,210026.20,0.00,0.45,-0.16,0.33,-0.00,0.03,0.0029,0.0075,1.0000,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*64\r\n'
# b'$GPCHC,2342,210026.25,0.00,0.41,-0.17,0.34,-0.01,0.04,0.0028,0.0074,1.0000,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*65\r\n$GPCHC,2342,210026.30,0.00,0.43,-0.23,0.34,-0.01,0.01,0.0041,0.0076,0.9998,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*6C\r\n'
# 1
# res = None
# res_lock = threading.Lock()

flDebugMode = True
# Global tolerance value
TOLERANCE = 0.1 / 111320  # 10 cm tolerans

def parse_c3d_file_to_dataframe(file_path):
    # Initialize a dictionary to store the data
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
    
    # Skip the metadata lines and find the start of the data
    data_start_index = 0
    for i, line in enumerate(lines):
        if line.strip() and line[0].isdigit():
            data_start_index = i
            break
    
    # Loop through each line in the C3D file starting from the data section
    for line in lines[data_start_index:]:
        line = line.strip()
        
        # Split the line into components
        parts = line.split()
        
        # Extract relevant parts and add to the data dictionary
        try:
            data['id'].append(parts[0])                # id
            data['northing'].append(float(parts[1]))   # northing (latitude)
            data['easting'].append(float(parts[2]))    # easting (longitude)
            data['altitude'].append(float(parts[3]))   # altitude
            data['ground_altitude'].append(float(parts[4]))  # ground altitude
            data['yaw'].append(float(parts[5]))        # yaw
            data['object_type'].append('HEA160-3.3')   # Assuming all rows have this object type
        except (IndexError, ValueError):
            # Skip invalid lines
            continue
    df = pd.DataFrame(data)
    return df

def get_scaled_vehicle_coords(x, y, heading, vehicle_length=3004.71/1000, vehicle_width=880.97/1000, stake_offset=1297.53/1000):
    """Aracı temsil eden döndürülmüş şeklin koordinatlarını döndür."""
    latitude_scale = 1 / 111320  # Enlem başına metre
    longitude_scale = 1 / (111320 * np.cos(np.radians(y)))  # Boylam başına metre

    # Kare ve paletlerin yerel koordinatları
    local_coords = [
        (0, vehicle_length * latitude_scale / 2),  # Üst nokta (yuvarlanmış uç)
        (-vehicle_width * longitude_scale / 2, -vehicle_length * latitude_scale / 2),  # Sol alt
        (vehicle_width * longitude_scale / 2, -vehicle_length * latitude_scale / 2),   # Sağ alt
        (vehicle_width * longitude_scale / 2, vehicle_length * latitude_scale / 2),    # Sağ üst
        (-vehicle_width * longitude_scale / 2, vehicle_length * latitude_scale / 2)    # Sol üst
    ]

    # Kazık çakma noktasının yerel koordinatları
    stake_coords = [
        (-stake_offset * longitude_scale, 0)  # Kazık çakma noktası
    ]

    # Dönüş matrisi kullanarak döndür
    rotated_coords = [
        (
            x + (math.cos(heading) * vx - math.sin(heading) * vy),
            y + (math.sin(heading) * vx + math.cos(heading) * vy)
        )
        for vx, vy in local_coords
    ]

    # Kazık çakma noktasını döndür
    rotated_stake_coords = [
        (
            x + (math.cos(heading) * vx - math.sin(heading) * vy),
            y + (math.sin(heading) * vx + math.cos(heading) * vy)
        )
        for vx, vy in stake_coords
    ]

    return rotated_coords, rotated_stake_coords
class Joystick(QWidget):
    joystick_moved = pyqtSignal(float, float)  # Sinyal: X ve Y eksenindeki hareket

    def __init__(self, parent=None):
        super(Joystick, self).__init__(parent)
        self.setFixedSize(150, 150)  # Widget boyutu
        self.center = QPointF(self.width() / 2, self.height() / 2)
        self.knob_position = self.center  # Joystick topuzunun başlangıç pozisyonu
        self.radius = 60  # Daire yarıçapı
        self.knob_radius = 20  # Joystick topuzunun yarıçapı
        self.is_dragging = False
        self.current_x = 0  # Mevcut x değeri
        self.current_y = 0  # Mevcut y değeri

        # Joystick hareketini sürekli emite eden bir timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.emit_joystick_movement)
        self.timer.start(50)  # Her 50 ms'de bir çalışır

    def paintEvent(self, event):
        """Joystick'i çizmek için paintEvent."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Arka plan çemberi
        painter.setBrush(QBrush(Qt.lightGray))
        painter.setPen(QPen(Qt.black, 2))
        painter.drawEllipse(self.center, self.radius, self.radius)

        # Joystick topuzu
        painter.setBrush(QBrush(Qt.red))
        painter.setPen(QPen(Qt.black, 1))
        painter.drawEllipse(self.knob_position, self.knob_radius, self.knob_radius)

    def mousePressEvent(self, event):
        """Fare basıldığında joystick'i hareket ettirmeye başla."""
        if (event.pos() - self.knob_position).manhattanLength() <= self.knob_radius:
            self.is_dragging = True

    def mouseMoveEvent(self, event):
        """Fare hareketiyle joystick'i kontrol et."""
        if self.is_dragging:
            delta = event.pos() - self.center  # Joystick'in merkezine göre fare pozisyonu
            distance = math.sqrt(delta.x()**2 + delta.y()**2)

            if distance > self.radius:  # Topuzun sınırlarını kontrol et
                delta *= self.radius / distance

            self.knob_position = self.center + delta
            self.update()

            # X ve Y ekseni hareketini normalize et
            self.current_x = delta.x() / self.radius
            self.current_y = -delta.y() / self.radius  # Y ekseni ters döndürüldü

    def mouseReleaseEvent(self, event):
        """Fare bırakıldığında joystick'i merkezine geri döndür."""
        self.is_dragging = False
        self.knob_position = self.center
        self.current_x = 0
        self.current_y = 0
        self.update()

    def emit_joystick_movement(self):
        """Joystick'in hareket sinyalini sürekli yayımlar."""
        if self.current_x != 0 or self.current_y != 0:
            self.joystick_moved.emit(self.current_x, self.current_y)
class MainApp(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainApp, self).__init__(parent)
        self.setupUi(self)
        self.colors = {'red':'#B24A3B', 'green':'#2E765E', 'yellow':'#FDD05A'}
        self.msGNSS = b'$GPCHC,2351,299028.00,0.00,0.25,1.72,0.53,-0.11,0.07,-0.0300,0.0043,0.9996,38.69224905,35.61973162,1368.78,-0.041,0.084,-0.560,0.094,10,0,61,0,0002*6C'
        self.vValScale = [5,1,0.1]
        self.zoomScale = 5.0
        self.fn = externalFunctions()
        self.data = None
        self.slZoomScale.valueChanged.connect(self.slChange_Scale)
        self.pbOpen.clicked.connect(self.fnOpenFile)
        self.pushButton_2.setEnabled(False)
        self.pushButton_2.clicked.connect(self.complete_job)
        self.pushButton_3.clicked.connect(self.reset_job)  # pushButton_3'ü reset_job fonksiyonuna bağla

        if flDebugMode: self.parse_gnss_data(self.msGNSS)

        # Kiosk mod ayarları
        self.setWindowFlags(Qt.FramelessWindowHint)  # Başlık çubuğunu kaldır
        self.showFullScreen()  # Tam ekran yap
        self.setFixedSize(self.size())  # Pencere boyutunu sabitle

    def clear_project_details(self):
        """Mevcut proje detaylarını siler."""
        self.data = None
        self.gdf = None
        self.completedJobs = []
        self.row_manager = None
        self.main_canvas.ax.clear()
        self.zoom_canvas.ax.clear()
        self.main_canvas.draw()
        self.zoom_canvas.draw()
        self.lbActualPos_X.clear()
        self.lbActualPos_Y.clear()
        self.lbTargetPos_X.clear()
        self.lbTargetPos_Y.clear()
        self.lbTargetPos_Z.clear()
        self.lbSensor.clear()

    @pyqtSlot(str)
    def parse_gnss_data(self, data):
        self.dGNSS = self.fn.parse_gpchc_message(data)
        self.dStatus = self.fn.interpret_status(self.dGNSS['Status'])
        self.lbOrient_h.setText(f"{self.dGNSS['Heading']}°")
        self.lbOrient_p.setText(f"{self.dGNSS['Pitch']}°")
        self.lbOrient_r.setText(f"{self.dGNSS['Roll']}°")
        self.lbGyro_X.setText(f"{self.dGNSS['gyro x']}°/s")
        self.lbGyro_Y.setText(f"{self.dGNSS['gyro y']}°/s")
        self.lbGyro_Z.setText(f"{self.dGNSS['gyro z']}°/s")
        self.lbAcc_X.setText(f"{self.dGNSS['acc x']} m/s²")
        self.lbAcc_Y.setText(f"{self.dGNSS['acc y']} m/s²")
        self.lbAcc_Z.setText(f"{self.dGNSS['acc z']} m/s²")
        self.lbActualPos_X.setText(f"{self.dGNSS['Latitude']}")
        self.lbActualPos_Y.setText(f"{self.dGNSS['Longitude']}")
        self.lbActualPos_Z.setText(f"{self.dGNSS['Altitude']} m")
        self.lbVelocity_e.setText(f"{self.dGNSS['Ve']} m/s")
        self.lbVelocity_n.setText(f"{self.dGNSS['Vn']} m/s")
        self.lbVelocity_u.setText(f"{self.dGNSS['Vu']} m/s")
        self.lbNSV_1.setText(f"{self.dGNSS['NSV1']}")
        self.lbNSV_2.setText(f"{self.dGNSS['NSV2']}")
        self.lbSystemState.setText(f"{self.dStatus['System State Description']}")
        self.lbSatelliteState.setText(f"{self.dStatus['Satellite State Description']}")

    def plot_gdf(self):
        "GeoDataFrame ve araç pozisyonunu grMain ve grZoom'da çiz."
        with QMutexLocker(self.mutex):
            self.main_canvas.plot(self.gdf, self.vehicle_position, self.zoomScale, self.completedJobs)
            self.zoom_canvas.plot(self.gdf, self.vehicle_position, self.main_canvas.heading, self.zoomScale, self.completedJobs)

            # Kazık çakma noktasının mevcut oryantasyonunu lbActualPos_X ve lbActualPos_Y etiketlerine yaz
            _, stake_coords = get_scaled_vehicle_coords(self.vehicle_position.x, self.vehicle_position.y, self.main_canvas.heading)
            stake_x, stake_y = stake_coords[0]
            self.lbActualPos_X.setText(f"{stake_x:.8f}")
            self.lbActualPos_Y.setText(f"{stake_y:.8f}")

            # Mevcut hedef noktayı lbTargetPos_X, lbTargetPos_Y, lbTargetPos_Z etiketlerine yaz
            for i in range(len(self.completedJobs)):
                if self.completedJobs[i] == 0:
                    target_point = self.gdf.geometry[i]
                    self.lbTargetPos_X.setText(f"{target_point.x:.8f}")
                    self.lbTargetPos_Y.setText(f"{target_point.y:.8f}")
                    self.lbTargetPos_Z.setText(f"{self.data['altitude'][i]:.4f}")
                    break

    @pyqtSlot(bool)
    def update_pushButton_2(self, enabled):
        self.pushButton_2.setEnabled(enabled)

    def complete_job(self):
        for i in range(len(self.completedJobs)):
            if self.completedJobs[i] == 0:
                self.completedJobs[i] = 1
                self.row_manager.update(i, 'g')
                self.pushButton_2.setEnabled(False)
                break
        if i < len(self.completedJobs) - 1: self.row_manager.update(i+1,'y')
        self.check_all_jobs_completed()

    def reset_job(self):
        for i in range(len(self.completedJobs)):
            if self.completedJobs[i] == 0:
                self.completedJobs[i] = -1
                self.row_manager.update(i, 'r')
                self.pushButton_2.setEnabled(False)
                break
        if i < len(self.completedJobs) - 1: self.row_manager.update(i+1,'y')
        self.check_all_jobs_completed()

    def check_all_jobs_completed(self):
        if all(job != 0 for job in self.completedJobs):
            self.wdMainScreen.setCurrentWidget(self.wdSummary)

    def startProject(self):
        # UTM easting ve northing'e göre geometri oluştur
        geometry = [Point(xy) for xy in zip(self.data['easting'], self.data['northing'])]
        self.gdf = gpd.GeoDataFrame(self.data, geometry=geometry)

        # CRS'yi UTM Zone 30N (EPSG:32630) olarak ayarla
        self.gdf.set_crs(epsg=32630, inplace=True)
        
        # grMain ve grZoom için layout oluştur
        self.main_layout = QVBoxLayout(self.grMain)
        self.zoom_layout = QVBoxLayout(self.grZoom)
        # grMain ve grZoom için matplotlib canvas oluştur
        self.main_canvas = MatplotlibCanvas(self)
        self.zoom_canvas = ZoomCanvas(self)

        # Canvas'ları layout'lara ekle
        self.main_layout.addWidget(self.main_canvas)
        self.zoom_layout.addWidget(self.zoom_canvas)

        self.joystick = Joystick(self)
        self.joystick_layout = QVBoxLayout(self.wdJoystick)

        self.joystick_layout.addWidget(self.joystick)
        self.info_label = QLabel("X: 0, Y: 0", self)
        self.joystick_layout.addWidget(self.info_label)
        self.joystick.joystick_moved.connect(self.update_info)

        # Başlangıç aracı pozisyonu
        self.vehicle_position = Point(35.38464100, 38.69935827)
        # self.vehicle_position = Point(self.dGNSS['Longitude'], self.dGNSS['Latitude'])
        self.mutex = QMutex()  # UI ve threading arasında veri güvenliği
        self.ui_update_timer = QTimer(self)
        self.ui_update_timer.timeout.connect(self.plot_gdf)
        self.ui_update_timer.start(20)  # 50 ms'de bir UI güncellemesi
        # Start GNSS Thread
        if not flDebugMode:
            self.gnss_thread = GNSS_Threading("192.168.1.203", 9904)
            self.gnss_thread.sgGNSS.connect(self.parse_gnss_data)
            self.gnss_thread.start()
            self.serial_thread = SerialThread()
            self.serial_thread.sensor_data_received.connect(self.update_sensor_label)
            self.serial_thread.start()

        self.updateJobs()

        # MatplotlibCanvas sinyalini MainApp slot'una bağla
        self.main_canvas.stake_position_reached.connect(self.update_pushButton_2)

        # Start Serial Thread

    @pyqtSlot(str)
    def update_sensor_label(self, data):
        self.lbSensor.setText(data)

    def openFileNameDialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getOpenFileName(self,"QFileDialog.getOpenFileName()", "","c3d Files (*.c3d)", options=options)
        if fileName:
            self.data = parse_c3d_file_to_dataframe(fileName)
            self.row_manager = RowManager(self.scrollArea, self.wdScrollArea)
            self.completedJobs = []
            for i in range(len(self.data['id'])):
                self.row_manager.add(order=self.data['id'][i], x=self.data['easting'][i], y=self.data['northing'][i], z=self.data['altitude'][i])
                self.completedJobs.append(0)
            self.startProject()

    def updateJobs(self):
        for i in range(0, len(self.completedJobs)):
            if (self.completedJobs[i] == 0):
                idx = i
                break
        nextJob = self.row_manager.rows[idx]
        self.row_manager.update(idx,'y')

    def findLastOne(self,arr):
        v = arr[::-1]

        for i in range(0, len(v)):
            if (arr[i] == 1):
                idx = i
                return len(v) - idx
        return -1

    def fnOpenFile(self):
        if self.data is not None:
            reply = QMessageBox.question(self, 'New Project', 'Are you sure you want to open a new project?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
            self.clear_project_details()
        self.openFileNameDialog()

    def update_info(self, x, y):
        """Joystick'in hareket bilgisini güncelle."""
        self.info_label.setText(f"X: {x:.2f}, Y: {y:.2f}")
        self.move_vehicle(x,y,0.000001)

    def move_vehicle(self,dx,dy,scale):
        with QMutexLocker(self.mutex):
            self.vehicle_position = Point(self.vehicle_position.x + scale*dx, self.vehicle_position.y + scale*dy)    
            # Yön açısını (heading) joystick hareketine göre hesapla
            if dx != 0 or dy != 0:
                self.main_canvas.heading = math.atan2(dy, dx)  - math.pi / 2 # atan2(y, x) yön açısını hesaplar

    def slChange_Scale(self):
        self.zoomScale = self.vValScale[self.sender().value()]
        self.lbScale.setText(f"{self.zoomScale:.2f} m")
        self.plot_gdf()  # Zoom değiştiğinde grafiği yeniden çiz
class MatplotlibCanvas(FigureCanvas):
    stake_position_reached = pyqtSignal(bool)

    def __init__(self, parent=None):
        # Gerçek dünya boyutlarıyla 10x10 km kare figür oluştur
        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        super(MatplotlibCanvas, self).__init__(self.fig)
        # Marjinleri küçült
        self.fig.subplots_adjust(left=0.07, right=0.95, top=0.95, bottom=0.05)
        # Arkaplanı transparan yap
        self.fig.patch.set_alpha(0)  # Figür arkaplanı
        self.heading = 0  # Başlangıç yönü (radyan cinsinden)
        self.flBlink = False
        
    def plot(self, gdf, vehicle_position, zoomScale, completedJobs):
        """GeoDataFrame noktalarını, 1 metre çapında kırmızı daireler ve aracı (sarı üçgen) çiz."""
        self.ax.clear()  # Önceki çizimi temizle
        
        for i in range(0, len(completedJobs)):
            if (completedJobs[i] == 0):
                idx = i
                break
        try: current_index = idx
        except: current_index = len(completedJobs)
        # GeoDataFrame noktalarını kırmızı daireler ile çiz
        if gdf is not None:
            for i, point in enumerate(gdf.geometry):
                if i == current_index: selColor = '#FDD05A'
                elif completedJobs[i] == 1: selColor = '#2E765E'
                else: selColor = '#B24A3B'
                self.ax.add_patch(plt.Circle((point.x, point.y), facecolor=selColor, radius=1 / 111320, edgecolor='black', linewidth=1))

        # Aracı yeni şekil olarak çiz
        vehicle_coords, stake_coords = get_scaled_vehicle_coords(vehicle_position.x, vehicle_position.y, self.heading)
        vehicle_polygon = Polygon(vehicle_coords, closed=True, color='black')
        self.ax.add_patch(vehicle_polygon)

        # Kazık çakma noktasını çiz
        stake_x, stake_y = stake_coords[0]
        stake_color = 'red'
        stake_reached = False
        if gdf is not None:
            for i, point in enumerate(gdf.geometry):
                if i == current_index: 
                    if abs(stake_x - point.x) < TOLERANCE and abs(stake_y - point.y) < TOLERANCE:
                        stake_color = 'green'
                        stake_reached = True
                        break
                    else: stake_color = 'red'
        self.stake_position_reached.emit(stake_reached)
        self.ax.add_patch(plt.Circle((stake_x, stake_y), facecolor=stake_color, radius=0.5 / 111320, edgecolor='black', linewidth=1))

        # 5 km x 5 km alanı kare şeklinde ayarla
        msf = 50/111320
        self.ax.set_xlim(vehicle_position.x - msf, vehicle_position.x + msf)
        self.ax.set_ylim(vehicle_position.y - msf, vehicle_position.y + msf)
        self.ax.set_aspect('equal', 'box')  # Grafiği kare yap
        self.ax.set_xticks(np.arange(vehicle_position.x - msf, vehicle_position.x + msf, 10/111320))
        self.ax.set_yticks(np.arange(vehicle_position.y - msf, vehicle_position.y + msf, 10/111320))

        # Grid ekle ve stilini özelleştir
        self.ax.grid(
            visible=True, 
            color="#98D7C2",      # Grid rengi
            linestyle="--",    # Kesik çizgi
            linewidth=0.5,     # Çizgi kalınlığı (piksel cinsinden)
        )
        # x ve y eksenlerini tam sayı olacak şekilde ayarla
        self.ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x)}"))  # X ekseni tam sayı
        self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{int(y)}"))  # Y ekseni tam sayı
        # Border ayarları
        for spine in self.ax.spines.values():
            spine.set_linewidth(2)  # Çerçeve çizgisi kalınlığ
            spine.set_edgecolor("#167D7F")
        self.ax.patch.set_alpha(0)   # Eksen arkaplanı
        self.ax.patch.set_color("#BBBBBB")
        self.ax.set_xlabel("Easting (UTM)")
        self.ax.set_ylabel("Northing (UTM)")
        self.draw()
class ZoomCanvas(FigureCanvas):
    def __init__(self, parent=None):
        # 1 metre x 1 metre kare figür oluştur
        self.fig, self.ax = plt.subplots(figsize=(5, 5))
        super(ZoomCanvas, self).__init__(self.fig)
        self.fig.patch.set_alpha(0)  # Figür arkaplanı

    def plot(self, gdf, vehicle_position, heading, zoomScale, completedJobs):
        """Zoomed 1 metre görünümde, GeoDataFrame noktalarını ve aracı sarı nokta olarak çiz."""
        self.ax.clear()  # Önceki çizimi temizle
        target_point = None
        stake_color = 'red'
        _, stake_coords = get_scaled_vehicle_coords(vehicle_position.x, vehicle_position.y, heading)
        stake_x, stake_y = stake_coords[0]
        # Mevcut hedef noktayı bul
        for i in range(len(completedJobs)):
            if completedJobs[i] == 0:
                target_point = gdf.geometry[i]
                break
        if target_point is not None:
            # Hedef noktayı sarı yuvarlak olarak çiz
            self.ax.add_patch(plt.Circle((target_point.x, target_point.y), facecolor='yellow', radius=0.05 / 111320, edgecolor='black', linewidth=1))

            # Tolerans kadar gri yuvarlak çiz
            self.ax.add_patch(plt.Circle((target_point.x, target_point.y), facecolor='#a9a9a9', radius=TOLERANCE, edgecolor='black', linewidth=1, alpha=0.5))

            # Kazık çakma noktasını çiz

            stake_reached = False
            for i, point in enumerate(gdf.geometry):
                if abs(stake_x - target_point.x) < TOLERANCE and abs(stake_y - target_point.y) < TOLERANCE:
                    stake_color = 'green'
                    stake_reached = True
                    break
                else:
                    stake_color = 'red'
        self.ax.add_patch(plt.Circle((stake_x, stake_y), facecolor=stake_color, radius=0.05*zoomScale / 111320, edgecolor='black', linewidth=1))

        # 1 metre alanı zoom yap
        zoom_factor = zoomScale / 111320  # Yaklaşık 1 metre
        self.ax.set_xlim(stake_x - zoom_factor, stake_x + zoom_factor)
        self.ax.set_ylim(stake_y - zoom_factor, stake_y + zoom_factor)
        self.ax.set_aspect('equal', 'box')  # Kare oranı koru
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        # Border ayarları
        for spine in self.ax.spines.values():
            spine.set_linewidth(2)  # Çerçeve çizgisi kalınlığ
            spine.set_edgecolor("#167D7F")
        self.ax.patch.set_alpha(0)   # Eksen arkaplanı
        self.ax.patch.set_color("#BBBBBB")
        
        self.draw()

    def rotate_point(self, x, y, cx, cy, angle):
        """Bir noktayı belirli bir açıyla döndür."""
        s = np.sin(angle)
        c = np.cos(angle)

        # Noktayı merkeze taşı
        x -= cx
        y -= cy

        # Döndür
        x_new = x * c - y * s
        y_new = x * s + y * c

        # Noktayı geri taşı
        x_new += cx
        y_new += cy

        return x_new, y_new
class RowManager:
    def __init__(self, scroll_area, wdScrollArea):
        """
        RowManager sınıfı, QScrollArea içinde QWidget'lar ekleme ve güncelleme işlemleri için tasarlanmıştır.
        :param scroll_area: Satırların ekleneceği QScrollArea
        """
        self.scroll_area = scroll_area
        self.container_widget = wdScrollArea  # QScrollArea'nın içindeki container
        self.container_layout = QVBoxLayout(self.container_widget)
        self.container_layout.setSpacing(5)  # Satırlar arası boşluk
        self.container_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.container_widget)
        self.scroll_area.setWidgetResizable(True)
        
        self.rows = []  # Tüm satırların referanslarını tutan liste

    def add(self, order, x, y, z):
        """
        Yeni bir satır ekler.
        :param order: lblOrder değeri
        :param x: lblX değeri
        :param y: lblY değeri
        :param z: lblZ değeri
        """
        # Satır için QWidget oluştur
        row_widget = QWidget()
        row_widget.setFixedSize(400, 20)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        # QLabel'ları oluştur ve ekle
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

        # QLabel'ları layout'a ekle
        row_layout.addWidget(lbl_order)
        row_layout.addWidget(lbl_x)
        row_layout.addWidget(lbl_y)
        row_layout.addWidget(lbl_z)

        # Satırı container'a ekle
        self.container_layout.addWidget(row_widget)

        # Satırı ve QLabel referanslarını kaydet
        self.rows.append({
            "widget": row_widget,
            "labels": [lbl_order, lbl_x, lbl_y, lbl_z]
        })

    def update(self, index, color=None):
        """
        Mevcut bir satırı günceller.
        :param index: Güncellenecek satırın sırası (0 tabanlı)
        :param color: QLabel'ların yeni arka plan rengi (QColor objesi veya hex string)
        :param border_color: Satırın border rengini ayarlar (QColor objesi veya hex string)
        """
        if index < 0 or index >= len(self.rows):
            raise IndexError("Invalid row index.")

        row = self.rows[index]
        row_widget = row["widget"]
        labels = row["labels"]


        # QLabel'ların arka plan rengini değiştir
        if color == 'y':
            for label in labels: label.setStyleSheet("font: 12pt; color: rgb(229, 195, 91);")
        if color == 'r':
            for label in labels: label.setStyleSheet("font: 12pt; color: rgb(255, 0, 0);")
        if color == 'g':
            for label in labels: label.setStyleSheet("font: 12pt; color: rgb(0, 255, 0);")
        # Satırın border rengini değiştir

class GNSS_Threading(QThread):
    # res = None
    # res_lock = threading.Lock()
    sgGNSS = pyqtSignal(str)
    # host = "192.168.1.203"
    # port = 9904
    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.s = None

    def run(self):
        self.s = self.connect(self.host, self.port)
        while True:
            self.recieve(self.s)

    def connect(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((host, port))
        except Exception as e:
            print(e)

        return s

    def recieve(self, s):
        data = s.recv(1024)
        res = data.decode()
        self.sgGNSS.emit(res)
        time.sleep(0.05)
class externalFunctions:    
    def parse_gpchc_message(self,message):
        """
        Parses a $GPCHC message into a dictionary.
        Extracts the Status and Warning fields into separate dictionaries.
        
        Args:
            message (str): The GPCHC message as a string.
        
        Returns:
            dict: Parsed message data, including nested dictionaries for Status and Warning.
        """
        fields = [
            "Header", "GPSWeek", "GPSTime", "Heading", "Pitch", "Roll", "gyro x", "gyro y", "gyro z",
            "acc x", "acc y", "acc z", "Latitude", "Longitude", "Altitude", "Ve", "Vn", "Vu", "V",
            "NSV1", "NSV2", "Status", "Age", "Warning", "Cs"
        ]
        
        # Remove $ and <CR><LF> from the message, split by ',' or '*'
        message_cleaned = message.strip().decode('utf-8').replace('$', '').split('*')
        data = message_cleaned[0].split(',') + [message_cleaned[1]]
        
        parsed_data = {}
        status_dict = {}
        warning_dict = {}
        
        for i, field in enumerate(fields):
            if field == "Status":
                status_value = int(data[i])
                status_dict["System State"] = status_value & 0xF  # Lower 4 bits
                status_dict["Satellite State"] = (status_value >> 4) & 0xF  # Upper 4 bits
                parsed_data[field] = status_dict
            elif field == "Warning":
                warning_value = int(data[i])
                warning_dict["No GPS message"] = (warning_value & 0b0001) != 0
                warning_dict["No velocity message"] = (warning_value & 0b0010) != 0
                warning_dict["gyro wrong"] = (warning_value & 0b0100) != 0
                warning_dict["acc wrong"] = (warning_value & 0b1000) != 0
                parsed_data[field] = warning_dict
            else:
                parsed_data[field] = data[i]
        
        return parsed_data
    def interpret_status(self,status_dict):
        """
        Interprets the Status field from the parsed GPCHC message.

        Args:
            status_dict (dict): The Status field parsed as a dictionary with keys:
                                - "System State" (lower half byte)
                                - "Satellite State" (higher half byte)

        Returns:
            dict: A dictionary containing human-readable descriptions for both system and satellite states.
        """
        # Define the mapping for system state (lower half byte)
        system_state_map = {
            0: "Initialization",
            1: "Satellite navigation mode",
            2: "Integrated navigation mode",
            3: "IMU navigation mode"
        }

        # Define the mapping for satellite state (high half byte)
        satellite_state_map = {
            0: "No positioning and no orientation",
            1: "Single positioning and orientation",
            2: "DGPS positioning and orientation",
            3: "Integrated navigation",
            4: "RTK fixed positioning and orientation",
            5: "RTK float positioning and orientation",
            6: "Single positioning and no orientation",
            7: "DGPS positioning and no orientation",
            8: "RTK fixed positioning and no orientation",
            9: "RTK float positioning and no orientation"
        }

        # Extract system state and satellite state
        system_state = status_dict.get("System State", None)
        satellite_state = status_dict.get("Satellite State", None)

        # Translate states to human-readable descriptions
        system_description = system_state_map.get(system_state, "Unknown system state")
        satellite_description = satellite_state_map.get(satellite_state, "Unknown satellite state")

        return {
            "System State Description": system_description,
            "Satellite State Description": satellite_description
        }

class SerialThread(QThread):
    sensor_data_received = pyqtSignal(str)

    def __init__(self, port='COM6', baudrate=9600, timeout=1):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.command = bytes.fromhex('01 04 00 00 00 01 31 CA')
        self.min_val = 4000
        self.max_val = 20000
        self.min_dist = 297  # mm
        self.max_dist = 832  # mm
        self.running = True

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"Bağlantı kuruldu: {ser.name}")

            while self.running:
                response = self.send_command_and_read_response(ser, self.command)
                if response:
                    value = self.parse_response(response)
                    if value is not None:
                        scaled_value = self.scale_value(value, self.min_val, self.max_val, self.min_dist, self.max_dist)
                        self.sensor_data_received.emit(f"{scaled_value} mm")
                    else:
                        self.sensor_data_received.emit("Out of range")
                time.sleep(1)  # Her saniyede bir komut gönder ve yanıtı oku

        except serial.SerialException as e:
            print(f"Seri port hatası: {e}")
        except KeyboardInterrupt:
            print("Bağlantı sonlandırıldı.")
        finally:
            if ser.is_open:
                ser.close()
                print("Seri port kapatıldı.")

    def send_command_and_read_response(self, ser, command, response_length=7):
        try:
            ser.write(command)
            time.sleep(0.1)  # Küçük bir gecikme ekleyin
            response = ser.read(response_length)
            return response
        except serial.SerialException as e:
            print(f"Seri port hatası: {e}")
            return None

    def parse_response(self, response):
        if len(response) >= 5:
            value = response[3] << 8 | response[4]
            return value
        return None

    def scale_value(self, value, min_val, max_val, min_dist, max_dist):
        if value < min_val:
            return "Out of range"
        elif value > max_val:
            return "Out of range"
        else:
            scaled_value = min_dist + (value - min_val) * (max_dist - min_dist) / (max_val - min_val)
            return scaled_value

    def stop(self):
        self.running = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()

    sys.exit(app.exec_())

