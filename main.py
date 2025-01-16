import sys
import threading
import time
import geopandas as gpd
from shapely.geometry import Point
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
import numpy as np
from PyQt5.QtCore import QTimer, pyqtSlot, QMutex, QMutexLocker
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QScrollArea
from PyQt5.QtGui import QPainter, QPen, QBrush, QPalette, QColor
from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from uiMain import Ui_MainWindow  # Assuming uiMain.py is in the same directory
import pandas as pd
# pyuic5 ui/ui_RV24005.ui -o uiMain.py
# b'$GPCHC,2342,210026.10,0.00,0.44,-0.13,0.35,-0.05,0.02,0.0023,0.0078,1.0002,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*64\r\n'
# b'$GPCHC,2342,210026.15,0.00,0.43,-0.24,0.33,-0.04,0.02,0.0037,0.0075,0.9999,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*6E\r\n$GPCHC,2342,210026.20,0.00,0.45,-0.16,0.33,-0.00,0.03,0.0029,0.0075,1.0000,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*64\r\n'
# b'$GPCHC,2342,210026.25,0.00,0.41,-0.17,0.34,-0.01,0.04,0.0028,0.0074,1.0000,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*65\r\n$GPCHC,2342,210026.30,0.00,0.43,-0.23,0.34,-0.01,0.01,0.0041,0.0076,0.9998,0.00000000,0.00000000,0.00,0.000,0.000,0.000,0.000,4,0,00,0,0002*6C\r\n'

import math
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
    
    # Loop through each line in the C3D file
    for line in lines:
        line = line.strip()
        
        # Ignore lines that don't contain numerical data (e.g., headers)
        if line and not line.startswith('{') and not line.startswith('"'):
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
                # The object type can be manually assigned or extracted, depending on your need
                data['object_type'].append('HEA160-3.3')   # Assuming all rows have this object type
            except (IndexError, ValueError):
                # Skip invalid lines
                continue
    
    # Convert the dictionary to a pandas DataFrame
    df = pd.DataFrame(data)
    return df

# # Example usage
# file_path = 'masa_irlanda_1.c3d'  # Replace with the actual path to your .c3d file
# coordinates = parse_c3d_file(file_path)

def get_scaled_triangle_coords(x, y, heading, vehicle_length=2, vehicle_width=1):
        
        """Aracı temsil eden döndürülmüş üçgenin koordinatlarını döndür."""
        latitude_scale = 1 / 111320  # Enlem başına metre
        longitude_scale = 1 / (111320 * np.cos(np.radians(y)))  # Boylam başına metre

        # Üçgenin yerel koordinatları (2 metre uzunluk, 1 metre genişlik)
        local_coords = [
            (0, vehicle_length * latitude_scale / 2),  # Üst nokta
            (-vehicle_width * longitude_scale / 2, -vehicle_length * latitude_scale / 2),  # Sol alt
            (vehicle_width * longitude_scale / 2, -vehicle_length * latitude_scale / 2)   # Sağ alt
        ]

        # Dönüş matrisi kullanarak döndür
        rotated_coords = [
            (
                x + (math.cos(heading) * vx - math.sin(heading) * vy),
                y + (math.sin(heading) * vx + math.cos(heading) * vy)
            )
            for vx, vy in local_coords
        ]

        return rotated_coords
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
        # Simüle edilmiş C3D verileri (GeoPandas DataFrame)
        self.data = {
            'id': ['01.01', '01.02', '01.03', '01.04'],
            'northing': [38.69935828, 38.69933937, 38.69932034, 38.69930095],
            'easting': [35.38464149, 35.38461696, 35.38459262, 35.38456917],
            'altitude': [1101.32, 1101.32, 1101.32, 1101.32]
        }
        self.row_manager = RowManager(self.scrollArea, self.wdScrollArea)

        for i in range(10):
            self.row_manager.add(order=i + 1, x=f"X-{i}", y=f"Y-{i}", z=f"Z-{i}")


        self.vValScale = [100,50,10,5,1,0.1,0.01]
        self.zoomScale = 5.0
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
        self.vehicle_position = Point(35.3847, 38.6993)
        self.mutex = QMutex()  # UI ve threading arasında veri güvenliği

        # Butonları araç hareket fonksiyonlarına bağla
        # self.pbUp.clicked.connect(self.move_up)
        # self.pbDown.clicked.connect(self.move_down)
        # self.pbLeft.clicked.connect(self.move_left)
        # self.pbRight.clicked.connect(self.move_right)
        self.slZoomScale.valueChanged.connect(self.slChange_Scale)
        # UI güncelleyici zamanlayıcı başlat
        self.ui_update_timer = QTimer(self)
        self.ui_update_timer.timeout.connect(self.plot_gdf)
        self.ui_update_timer.start(20)  # 50 ms'de bir UI güncellemesi
        
        

    def update_info(self, x, y):
        """Joystick'in hareket bilgisini güncelle."""
        self.info_label.setText(f"X: {x:.2f}, Y: {y:.2f}")
        self.move_vehicle(x,y,0.000001)
    def plot_gdf(self):
        "GeoDataFrame ve araç pozisyonunu grMain ve grZoom'da çiz."
        with QMutexLocker(self.mutex):
            self.main_canvas.plot(self.gdf, self.vehicle_position, self.zoomScale)
            self.zoom_canvas.plot(self.gdf, self.vehicle_position, self.zoomScale)
    def move_vehicle(self,dx,dy,scale):
        with QMutexLocker(self.mutex):
            self.vehicle_position = Point(self.vehicle_position.x + scale*dx, self.vehicle_position.y + scale*dy)    
            # Yön açısını (heading) joystick hareketine göre hesapla
            if dx != 0 or dy != 0:
                self.main_canvas.heading = math.atan2(dy, dx)  - math.pi / 2 # atan2(y, x) yön açısını hesaplar
    def slChange_Scale(self):
        self.zoomScale = self.vValScale[self.sender().value()]
        self.lbScale.setText(f"{self.zoomScale:.2f} m")
        # pass

class MatplotlibCanvas(FigureCanvas):
    def __init__(self, parent=None):
        # Gerçek dünya boyutlarıyla 10x10 km kare figür oluştur
        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        super(MatplotlibCanvas, self).__init__(self.fig)
        # Marjinleri küçült
        self.fig.subplots_adjust(left=0.07, right=0.95, top=0.95, bottom=0.05)
        # Arkaplanı transparan yap
        self.fig.patch.set_alpha(0)  # Figür arkaplanı
        self.heading = 0  # Başlangıç yönü (radyan cinsinden)
        
    def plot(self, gdf, vehicle_position, zoomScale):
        """GeoDataFrame noktalarını, 1 metre çapında kırmızı daireler ve aracı (sarı üçgen) çiz."""
        self.ax.clear()  # Önceki çizimi temizle
        
        # GeoDataFrame noktalarını kırmızı daireler ile çiz
        for point in gdf.geometry:
            self.ax.add_patch(plt.Circle((point.x, point.y), radius=self.get_meter_to_degree(1, point.y), 
                                         edgecolor='red', linewidth=2))

            # Dairelerin merkezine kırmızı çarpı işareti ekle
            self.ax.text(point.x, point.y, 'x', color='red', fontsize=12, ha='center', va='center')

        # Aracı sarı üçgen olarak çiz
        triangle = Polygon(get_scaled_triangle_coords(vehicle_position.x, vehicle_position.y,self.heading), closed=True, color='black')
        self.ax.add_patch(triangle)
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
        # self.ax.set_title("C3D Noktaları ve Araç Pozisyonu")
        self.ax.set_xlabel("Easting (UTM)")
        self.ax.set_ylabel("Northing (UTM)")
        self.draw()

    def get_meter_to_degree(self, meters, latitude):
        """Metreyi, enleme bağlı olarak dereceye çevir."""
        return meters / (111320 * np.cos(np.radians(latitude)))

    

class ZoomCanvas(FigureCanvas):
    def __init__(self, parent=None):
        # 1 metre x 1 metre kare figür oluştur
        self.fig, self.ax = plt.subplots(figsize=(5, 5))
        super(ZoomCanvas, self).__init__(self.fig)
        self.fig.patch.set_alpha(0)  # Figür arkaplanı

    def plot(self, gdf, vehicle_position, zoomScale):
        """Zoomed 1 metre görünümde, GeoDataFrame noktalarını ve aracı sarı nokta olarak çiz."""
        self.ax.clear()  # Önceki çizimi temizle
        
        # GeoDataFrame noktalarını kırmızı çarpı işaretleri ile çiz
        for point in gdf.geometry:
            # if self.is_within_limits(point.x, point.y, self.ax.get_xlim(), self.ax.get_ylim()):
            self.ax.text(point.x, point.y, 'x', color='red', fontsize=12, ha='center', va='center')

        # Aracı sarı nokta olarak çiz
        # self.ax.plot(vehicle_position.x, vehicle_position.y, 'yo', markersize=10)
        triangle = Polygon(get_scaled_triangle_coords(vehicle_position.x, vehicle_position.y,0,1,0.5), closed=True, color='black')
        self.ax.add_patch(triangle)

        # 1 metre alanı zoom yap
        zoom_factor = zoomScale/111320  # Yaklaşık 1 metre
        self.ax.set_xlim(vehicle_position.x - zoom_factor, vehicle_position.x + zoom_factor)
        self.ax.set_ylim(vehicle_position.y - zoom_factor, vehicle_position.y + zoom_factor)
        self.ax.set_aspect('equal', 'box')  # Kare oranı koru
        # self.ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x)}"))  # X ekseni tam sayı
        # self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{int(y)}"))  # Y ekseni tam sayı
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        # Border ayarları
        for spine in self.ax.spines.values():
            spine.set_linewidth(2)  # Çerçeve çizgisi kalınlığ
            spine.set_edgecolor("#167D7F")
        self.ax.patch.set_alpha(0)   # Eksen arkaplanı
        self.ax.patch.set_color("#BBBBBB")
        
        self.draw()
    def is_within_limits(self,x, y, xlim, ylim):
        """Bir noktanın verilen sınırlar içinde olup olmadığını kontrol eder."""
        return xlim[0] <= x <= xlim[1] and ylim[0] <= y <= ylim[1]

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

    def update(self, index, color=None, border_color=None):
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
        if color:
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(color))
            for label in labels:
                label.setAutoFillBackground(True)
                label.setPalette(palette)

        # Satırın border rengini değiştir
        if border_color:
            row_widget.setStyleSheet(f"border: 1px solid {border_color};")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()

    sys.exit(app.exec_())
