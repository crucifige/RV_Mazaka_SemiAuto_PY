from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtGui import QPainter, QPen, QBrush
from PyQt5.QtCore import Qt, QPointF, pyqtSignal
import math


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
            x = delta.x() / self.radius
            y = -delta.y() / self.radius  # Y ekseni ters döndürüldü
            self.joystick_moved.emit(x, y)

    def mouseReleaseEvent(self, event):
        """Fare bırakıldığında joystick'i merkezine geri döndür."""
        self.is_dragging = False
        self.knob_position = self.center
        self.update()
        self.joystick_moved.emit(0, 0)  # Joystick serbest bırakıldığında hareket durur


class MainWindow(QWidget):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle("Joystick Widget")
        self.setFixedSize(200, 200)

        # Layout oluştur
        layout = QVBoxLayout(self)

        # Joystick widget ekle
        self.joystick = Joystick(self)
        layout.addWidget(self.joystick)

        # Hareket bilgisi için bir label
        self.info_label = QLabel("X: 0, Y: 0", self)
        layout.addWidget(self.info_label)

        # Joystick sinyalini hareket bilgisine bağla
        self.joystick.joystick_moved.connect(self.update_info)

    def update_info(self, x, y):
        """Joystick'in hareket bilgisini güncelle."""
        self.info_label.setText(f"X: {x:.2f}, Y: {y:.2f}")


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
