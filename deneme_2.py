from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor


class RowManager:
    def __init__(self, scroll_area):
        """
        RowManager sınıfı, QScrollArea içinde QWidget'lar ekleme ve güncelleme işlemleri için tasarlanmıştır.
        :param scroll_area: Satırların ekleneceği QScrollArea
        """
        self.scroll_area = scroll_area
        self.container_widget = QWidget()  # QScrollArea'nın içindeki container
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


# Örnek Kullanım
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow, QScrollArea

    class MainApp(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("RowManager Demo")
            self.setGeometry(100, 100, 500, 600)

            # QScrollArea oluştur
            self.scroll_area = QScrollArea(self)
            self.scroll_area.setGeometry(50, 50, 400, 500)

            # RowManager örneği
            self.row_manager = RowManager(self.scroll_area)

            # Örnek satırlar ekle
            for i in range(10):
                self.row_manager.add(order=i + 1, x=f"X-{i}", y=f"Y-{i}", z=f"Z-{i}")

            # İlk satırı sarıya, ikinci satırı yeşile boyayın
            self.row_manager.update(0, color="#FFFF00")  # Sarı
            self.row_manager.update(1, color="#00FF00", border_color="#000000")  # Yeşil, siyah border

    app = QApplication(sys.argv)
    main_window = MainApp()
    main_window.show()
    sys.exit(app.exec_())
