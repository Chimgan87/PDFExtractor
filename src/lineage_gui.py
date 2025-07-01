import sys
import os
import time
import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab
from datetime import datetime
from configparser import ConfigParser
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QWidget, QTextEdit, QSpinBox, QComboBox
)
from PyQt5.QtGui import QMovie, QPainter, QColor, QPixmap
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QPoint

INI_PATH = "setup.ini"
ICON_FOLDER = "icons"
TEMPLATE_PATH = os.path.join(ICON_FOLDER, "target.png")
SCROLL_PATH = os.path.join(ICON_FOLDER, "Skroll.png")
THRESHOLD = 0.99


def load_config():
    config = ConfigParser()
    if not os.path.exists(INI_PATH):
        config['Settings'] = {
            'delay_after_del': '3',
            'min_targets': '4',
            'screen_mode': '2560x1440'
        }
        with open(INI_PATH, "w") as f:
            config.write(f)
    else:
        config.read(INI_PATH)
    return (
        int(config['Settings'].get('delay_after_del', 3)),
        int(config['Settings'].get('min_targets', 4)),
        config['Settings'].get('screen_mode', '2560x1440')
    )


def save_config(delay, targets, screen_mode):
    config = ConfigParser()
    config['Settings'] = {
        'delay_after_del': str(delay),
        'min_targets': str(targets),
        'screen_mode': screen_mode
    }
    with open(INI_PATH, "w") as f:
        config.write(f)


class Worker(QThread):
    log = pyqtSignal(str)
    counter = pyqtSignal(tuple)

    def __init__(self, min_targets, delay_after_del, screen_mode):
        super().__init__()
        self.running = False
        self.count = 0
        self.min_targets = min_targets
        self.delay_after_del = delay_after_del
        self.screen_mode = screen_mode
        self.template = cv2.imread(TEMPLATE_PATH)
        if self.template is None:
            raise FileNotFoundError("target.png not found.")
        self.scroll_template = cv2.imread(SCROLL_PATH)
        if self.scroll_template is None:
            raise FileNotFoundError("Skroll.png not found.")

    def get_search_area(self):
        if self.screen_mode == "1920x1080":
            return (1660, 0, 260, 1080)
        else:
            return (2260, 0, 300, 1440)

    def run(self):
        self.running = True
        self.log.emit("▶ Поиск запущен...")
        sx, sy, sw, sh = self.get_search_area()
        h, w, _ = self.template.shape

        while self.running:
            rgb_screen = np.array(ImageGrab.grab())
            screen = cv2.cvtColor(rgb_screen, cv2.COLOR_RGB2BGR)
            region = screen[sy:sy + sh, sx:sx + sw]
            res = cv2.matchTemplate(region, self.template, cv2.TM_CCOEFF_NORMED)
            raw_points = list(zip(*np.where(res >= THRESHOLD)[::-1]))

            points = []
            for pt in raw_points:
                if all(np.linalg.norm(np.array(pt) - np.array(p)) > 10 for p in points):
                    points.append(pt)

            count_found = len(points)
            self.counter.emit((self.count, count_found))

            if count_found < self.min_targets:
                time.sleep(1)
                continue

            while self.running and len(points) > 0:
                pt = points[0]
                gx = sx + pt[0] + w // 2
                gy = sy + pt[1] + h // 2
                pyautogui.moveTo(gx, gy, duration=0.1)
                pyautogui.click()
                time.sleep(0.05)
                pyautogui.press('space')
                time.sleep(0.05)
                pyautogui.press('delete')
                self.log.emit(f"[✓] Выгрузка: x={gx}, y={gy}")
                self.scroll_to_bottom()
                self.count += 1
                self.counter.emit((self.count, len(points)))
                time.sleep(self.delay_after_del)

                rgb_screen = np.array(ImageGrab.grab())
                screen = cv2.cvtColor(rgb_screen, cv2.COLOR_RGB2BGR)
                region = screen[sy:sy + sh, sx:sx + sw]
                res = cv2.matchTemplate(region, self.template, cv2.TM_CCOEFF_NORMED)
                raw_points = list(zip(*np.where(res >= THRESHOLD)[::-1]))

                points = []
                for pt in raw_points:
                    if all(np.linalg.norm(np.array(pt) - np.array(p)) > 10 for p in points):
                        points.append(pt)

    def scroll_to_bottom(self):
        screenshot = np.array(ImageGrab.grab())
        screen = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
        res = cv2.matchTemplate(screen, self.scroll_template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= THRESHOLD)
        for pt in zip(*loc[::-1]):
            x, y = pt
            pyautogui.moveTo(x + 5, y + 2, duration=0.1)
            pyautogui.click()
            self.log.emit("↘ Скролл после выгрузки")
            break

    def stop(self):
        self.running = False
        self.log.emit("■ Остановка")


class LogTextEdit(QTextEdit):
    """Text edit with a watermark in the bottom-left corner."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(QColor(255, 255, 255, 80))
        rect = self.viewport().rect()
        metrics = self.fontMetrics()
        x = 5
        y = rect.bottom() - metrics.descent() - 2
        painter.drawText(x, y, "by Enigmati")
        painter.end()


class LineageWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFixedSize(850, 550)
        self.offset = QPoint()
        self.worker = None
        self.running = False
        self.delay_val, self.target_val, self.screen_mode = load_config()
        self.close_button = QPushButton("✖")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setStyleSheet("background-color: #550000; color: white; font-weight: bold; border: 1px solid #a33;")
        self.close_button.clicked.connect(self.close)

        self.min_button = QPushButton("➖")
        self.min_button.setFixedSize(24, 24)
        self.min_button.setStyleSheet("background-color: #333333; color: white; font-weight: bold; border: 1px solid #777;")
        self.min_button.clicked.connect(self.showMinimized)

        self.gif_label = QLabel()
        self.gif_label.setVisible(True)
        self.gif_label.setFixedSize(300, 380)

        gif_path = os.path.join(ICON_FOLDER, 'wolf.giff')
        if os.path.exists(gif_path):
            self.movie = QMovie(gif_path)
            self.movie.setScaledSize(self.gif_label.size())
            self.gif_label.setMovie(self.movie)
            self.movie.start()
        else:
            self.gif_label.setText("🐺 wolf.gif не найден")

        self.logo_label = QLabel()
        logo_path = os.path.join(ICON_FOLDER, 'logo_nextfarm.png')
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaledToHeight(60, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedHeight(66)

        self.status_log = LogTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setStyleSheet("background-color: #1a1a1a; color: #adff2f; font-family: 'Georgia'; font-size: 12px; border: 1px solid #666;")

        self.counter_label = QLabel("Выгружено: 0")
        self.counter_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 14px")

        self.found_label = QLabel("Найдено: 0")
        self.found_label.setStyleSheet("color: #ffaa00; font-weight: bold; font-size: 14px")

        self.target_spin = QSpinBox()
        self.target_spin.setRange(1, 14)
        self.target_spin.setValue(self.target_val)
        self.target_spin.setFixedWidth(60)
        self.target_spin.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #555;")
        self.target_spin.valueChanged.connect(self.on_target_changed)

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(1, 10)
        self.delay_spin.setValue(self.delay_val)
        self.delay_spin.setSuffix(" сек")
        self.delay_spin.setFixedWidth(60)
        self.delay_spin.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #555;")
        self.delay_spin.valueChanged.connect(self.on_delay_changed)

        self.screen_combo = QComboBox()
        self.screen_combo.addItems(["1920x1080", "2560x1440"])
        self.screen_combo.setCurrentText(self.screen_mode)
        self.screen_combo.setFixedWidth(100)
        self.screen_combo.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #555;")
        self.screen_combo.currentTextChanged.connect(self.update_screen_mode)

        self.start_button = QPushButton("▶ Старт")
        self.start_button.setStyleSheet("padding: 10px; background-color: #384a3c; color: #eeeeee; font-weight: bold; border: 1px solid #5d8c4a;")
        self.start_button.clicked.connect(self.toggle_autokick)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.counter_label)
        top_bar.addWidget(self.found_label)
        top_bar.addStretch()
        top_bar.addWidget(self.min_button)
        top_bar.addWidget(self.close_button)

        settings_layout = QVBoxLayout()
        for label, widget in [
            (QLabel("Мин. целей:"), self.target_spin),
            (QLabel("Задержка:"), self.delay_spin),
            (QLabel("Разрешение:"), self.screen_combo),
        ]:
            label.setStyleSheet("color: white; font-size: 12px")
            row = QHBoxLayout()
            row.addWidget(label)
            row.addWidget(widget)
            settings_layout.addLayout(row)
            settings_layout.addSpacing(5)
        settings_layout.addStretch()

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.gif_label)
        left_layout.addLayout(settings_layout)
        left_layout.addWidget(self.logo_label)

        right_layout = QVBoxLayout()
        right_layout.addLayout(top_bar)
        right_layout.addWidget(self.start_button)
        right_layout.addWidget(self.status_log)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)

        container = QWidget()
        container.setLayout(main_layout)
        container.setStyleSheet("background-color: #0e0e0e; border: 2px solid #705f4f;")
        self.setCentralWidget(container)

    def toggle_autokick(self):
        if not self.running:
            self.start_autokick()
        else:
            self.stop_autokick()

    def start_autokick(self):
        self.append_log("▶ Запуск...")
        min_targets = self.target_spin.value()
        delay_sec = self.delay_spin.value()
        save_config(delay_sec, min_targets, self.screen_mode)
        self.worker = Worker(min_targets, delay_sec, self.screen_mode)
        self.worker.log.connect(self.append_log)
        self.worker.counter.connect(self.update_counter)
        self.worker.start()
        self.start_button.setText("■ Стоп")
        self.start_button.setStyleSheet("padding: 10px; background-color: #7a2c2c; color: #ffffff; font-weight: bold; border: 1px solid #aa4c4c;")
        self.running = True

    def stop_autokick(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        self.append_log("■ Остановка...")
        self.start_button.setText("▶ Старт")
        self.start_button.setStyleSheet("padding: 10px; background-color: #384a3c; color: #eeeeee; font-weight: bold; border: 1px solid #5d8c4a;")
        self.running = False

    def append_log(self, text):
        now = datetime.now().strftime("[%H:%M:%S]")
        self.status_log.append(f"{now} {text}")
        self.status_log.verticalScrollBar().setValue(self.status_log.verticalScrollBar().maximum())

    def update_counter(self, data):
        count, found = data
        self.counter_label.setText(f"Выгружено: {count}")
        self.found_label.setText(f"Найдено: {found}")

    def update_screen_mode(self, mode):
        self.screen_mode = mode
        save_config(self.delay_spin.value(), self.target_spin.value(), mode)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.offset)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor("#705f4f"))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def on_delay_changed(self, val):
        save_config(val, self.target_spin.value(), self.screen_mode)
        if self.worker:
            self.worker.delay_after_del = val

    def on_target_changed(self, val):
        save_config(self.delay_spin.value(), val, self.screen_mode)
        if self.worker:
            self.worker.min_targets = val


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LineageWindow()
    window.show()
    sys.exit(app.exec_())
