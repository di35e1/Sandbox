# BUILD INSTRUCTIONS:
#     Build the app:
#     pyinstaller --noconfirm --windowed --icon "VUmeter.icns" --name "VU Meter" VUmeter3.py
#
#     Add microphone permission to Info.plist:
#     Open dist/VU Meter.app/Contents/Info.plist and add these lines before </dict>:
#     <key>NSMicrophoneUsageDescription</key>
#     <string>This app requires microphone access to display the audio spectrum and level meters.</string>
#
#     Resign the app:
#     codesign --force --deep --sign - "dist/VU Meter.app"

import sys
import os
import wave
import datetime
import subprocess
import time
import numpy as np
import sounddevice as sd
from scipy import signal

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QMenu)
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QAction, QShortcut, QKeySequence

class MeterCanvas(QWidget):
    """Кастомный виджет, который рисует шкалы, индикаторы и спектр"""
    def __init__(self, main_app):
        super().__init__()
        self.main = main_app

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        # Защита от отрисовки до инициализации аудио
        if not hasattr(self.main, 'input_channels') or not hasattr(self.main, 'rms_level'):
            return

        LEVEL_RANGE = self.main.LEVEL_RANGE
        bar_bottom = 215 
        bar_top = 10
        bar_max_h = bar_bottom - bar_top

        def db_to_y(db):
            db = max(-LEVEL_RANGE, min(0, db))
            ratio = (db + LEVEL_RANGE) / LEVEL_RANGE
            return bar_bottom - int(bar_max_h * ratio)

        # 1. Отрисовка каналов (Слева)
        for ch in range(self.main.input_channels):
            if ch >= len(self.main.peak_level): break
            ch_x = 10 + ch * 20
            label = "M" if self.main.input_channels == 1 else ("L" if ch == 0 else "R")
            
            if self.main.peak_level[ch] > -6:
                painter.setPen(QPen(Qt.GlobalColor.red))
            else:
                painter.setPen(QPen(Qt.GlobalColor.yellow))
            painter.drawText(ch_x, 10, label)

            if self.main.display_mode == "RMS":
                display_level = self.main.smoothed_level[ch]
            else:
                display_level = self.main.peak_display_level[ch]

            y_disp = db_to_y(display_level)
            y_peak = db_to_y(self.main.peak_level[ch])
            y_rms = db_to_y(self.main.smoothed_level[ch])

            fill_color = QColor("red") if display_level > -6 else QColor("orange") if display_level > -12 else QColor("green")
            painter.fillRect(ch_x, y_disp, 10, bar_bottom - y_disp, fill_color)

            painter.setPen(QPen(Qt.GlobalColor.red, 2))
            painter.drawLine(ch_x, y_peak, ch_x + 10, y_peak)

            if self.main.display_mode == "PEAK":
                painter.setPen(QPen(Qt.GlobalColor.white, 2))
                painter.drawLine(ch_x, y_rms, ch_x + 10, y_rms)

        # 2. Отрисовка шкалы dB (Правее каналов)
        scale_x = 10 + (self.main.input_channels * 20) + 10
        painter.setPen(QPen(Qt.GlobalColor.yellow))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(scale_x + 5, 10, "dB")

        db_scale = [-1, -6, -12, -18, -24, -30, -35, -40, -45, -50, -55, -60]
        for db in db_scale:
            y = db_to_y(db)
            color = QColor("red") if db >= -6 else QColor("orange") if db >= -12 else QColor("green")
            painter.setPen(QPen(color, 1.5))
            painter.drawLine(scale_x - 6, y, scale_x, y)
            painter.setPen(QPen(Qt.GlobalColor.white))
            painter.drawText(scale_x + 5, y + 4, str(db))

        # 3. Отрисовка спектра (Если включен)
        if self.main.show_spectrum:
            spectrum_start_x = scale_x + 35
            band_width = 10
            band_gap = 3

            for i in range(self.main.NUM_BANDS):
                x1 = spectrum_start_x + i * (band_width + band_gap)
                
                y_rms = db_to_y(self.main.smoothed_band_levels[i])
                y_peak = db_to_y(self.main.peak_band_levels[i])
                
                fill_color = QColor("red") if self.main.smoothed_band_levels[i] > -6 else QColor("orange") if self.main.smoothed_band_levels[i] > -15 else QColor("green")
                painter.fillRect(x1, y_rms, band_width, bar_bottom - y_rms, fill_color)
                
                painter.setPen(QPen(Qt.GlobalColor.red, 1))
                painter.drawLine(x1, y_peak, x1 + band_width, y_peak)
                
                if i % 2 == 0:
                    freq = int(self.main.band_centers[i])
                    if freq >= 1000:
                        text = f"{freq/1000:.1f}k".replace(".0", "")
                    else:
                        text = str(freq)
                        
                    painter.setPen(QPen(Qt.GlobalColor.lightGray))
                    painter.setFont(QFont("Arial", 7))
                    
                    rect = QRectF(x1 - 15, bar_bottom + 4, band_width + 30, 20)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)


class AudioLevelMeter(QWidget):
    def __init__(self):
        super().__init__()
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowOpacity(0.75)
        self.setStyleSheet("background-color: black; color: white;")

        # --- БАЗОВАЯ ИНИЦИАЛИЗАЦИЯ (Защита от AttributeError) ---
        self.LEVEL_RANGE = 60
        self.PEAK_HOLD_TIME = 1.5
        self.DECAY_RATE = 25
        self.rms_window_size = 50
        self.display_mode = "RMS"
        self.input_channels = 1
        self.sample_rate = 44100
        self.last_callback_time = time.time()
        
        self.rms_level = [-self.LEVEL_RANGE]
        self.peak_level = [-self.LEVEL_RANGE]
        self.smoothed_level = [-self.LEVEL_RANGE]
        self.peak_hold_counter = [0]
        self.peak_display_level = [-self.LEVEL_RANGE]
        self.rms_display_level = [-self.LEVEL_RANGE]

        self.show_spectrum = False
        self.NUM_BANDS = 31
        self.MIN_FREQ = 20
        self.MAX_FREQ = 16000
        self.available_min_freqs = [20, 50, 100, 150, 200]
        self.available_max_freqs = [10000, 16000, 20000]
        self.band_centers = np.logspace(np.log10(self.MIN_FREQ), np.log10(self.MAX_FREQ), self.NUM_BANDS)
        
        self.band_levels = np.full(self.NUM_BANDS, -self.LEVEL_RANGE, dtype=np.float32)
        self.smoothed_band_levels = np.full(self.NUM_BANDS, -self.LEVEL_RANGE, dtype=np.float32)
        self.peak_band_levels = np.full(self.NUM_BANDS, -self.LEVEL_RANGE, dtype=np.float32)
        self.peak_band_hold = np.zeros(self.NUM_BANDS)

        self.recording = False
        self.audio_file = None
        self.recording_start_time = 0

        self.setup_ui()

        # Флаг для предотвращения бесконечной рекурсии при отвале USB
        self.is_reconnecting = False
        
        # --- ГОРЯЧИЕ КЛАВИШИ ---
        self.shortcut_rec = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_rec.activated.connect(self.toggle_record)
        
        # Для плюса на основной клавиатуре (находится на кнопке "=")
        self.shortcut_spec_main = QShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Equal), self)
        self.shortcut_spec_main.activated.connect(lambda: self.toggle_spectrum(not self.show_spectrum))
        
        # Для плюса на цифровом блоке Numpad
        self.shortcut_spec_num = QShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Plus), self)
        self.shortcut_spec_num.activated.connect(lambda: self.toggle_spectrum(not self.show_spectrum))
        
        self.current_device_index = None
        self.setup_audio()
        self.apply_window_size()

        self.update_interval = 15
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_meter)
        self.timer.start(self.update_interval)
        
        self.rec_timer = QTimer()
        self.rec_timer.timeout.connect(self.update_recording_time)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        self.title_label = QLabel("VU Meter")
        self.title_label.setFont(QFont("Helvetica", 12))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        self.meter_canvas = MeterCanvas(self)
        main_layout.addWidget(self.meter_canvas, alignment=Qt.AlignmentFlag.AlignCenter)

        # Контейнер для кнопок, чтобы менять их расположение на лету
        self.buttons_container = QWidget()
        main_layout.addWidget(self.buttons_container)

        self.btn_record = self.create_button("Rec", self.toggle_record)
        self.btn_settings = self.create_button("Settings", self.show_settings_menu)
        self.btn_close = self.create_button("Close", self.close_program)

    def apply_window_size(self):
        if not hasattr(self, 'input_channels'): return
        
        base_width = 60 if self.input_channels == 1 else 85
        
        # --- БЕЗОПАСНАЯ ОЧИСТКА СТАРОГО LAYOUT ---
        old_layout = self.buttons_container.layout()
        if old_layout is not None:
            # Сначала отвязываем кнопки от старого layout, чтобы не удалить их
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
            # Удаляем сам объект старого layout
            QWidget().setLayout(old_layout)
        
        # --- НАСТРОЙКА НОВОГО LAYOUT И РАЗМЕРОВ ---
        if self.show_spectrum:
            target_width = base_width + 450
            target_height = 290 # Уменьшенная высота окна
            self.meter_canvas.setFixedSize(base_width + 420, 240)
            self.title_label.setText("VU Meter + Spectrum")
            new_layout = QHBoxLayout(self.buttons_container) # Горизонтальный ряд
        else:
            target_width = base_width + 10
            target_height = 340 # Обычная высота окна
            self.meter_canvas.setFixedSize(base_width, 240)
            self.title_label.setText("VU Meter")
            new_layout = QVBoxLayout(self.buttons_container) # Вертикальный столбик

        new_layout.setContentsMargins(0, 0, 0, 0)
        new_layout.setSpacing(5)
        new_layout.addWidget(self.btn_record)
        new_layout.addWidget(self.btn_settings)
        new_layout.addWidget(self.btn_close)

        # --- ЛОГИКА СДВИГА (Защита от выхода за экран) ---
        current_geo = self.geometry()
        screen_geo = self.screen().availableGeometry()
        
        new_x = current_geo.x()
        new_y = current_geo.y()

        if new_x + target_width > screen_geo.right():
            new_x = screen_geo.right() - target_width - 10
            
        if new_x < screen_geo.left():
            new_x = screen_geo.left() + 5

        # Защита по Y оси (поскольку мы меняем высоту, окно может уползти вниз)
        if new_y + target_height > screen_geo.bottom():
            new_y = screen_geo.bottom() - target_height - 10

        self.setGeometry(new_x, new_y, target_width, target_height)
        self.setFixedSize(target_width, target_height)

    def create_button(self, text, callback):
        btn = QPushButton(text)
        btn.setStyleSheet("""
            QPushButton { background-color: #111; color: #aaa; border: 1px solid #333; padding: 3px; }
            QPushButton:hover { background-color: #333; color: white; }
        """)
        btn.clicked.connect(callback)
        return btn

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def get_input_devices(self):
        """Безопасный опрос устройств с полным сбросом PortAudio"""
        if self.recording:
            return [(self.current_device_index, "Recording in progress...")]

        try:
            # 1. Жесткий сброс для очистки 'битых' индексов хаба
            if hasattr(self, 'audio_stream') and self.audio_stream:
                try:
                    self.audio_stream.stop()
                    self.audio_stream.close()
                except: pass
                self.audio_stream = None

            sd._terminate()
            sd._initialize()

            # 2. Получаем новый список
            devices = sd.query_devices()
            inputs = []
            for i, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    inputs.append((i, dev['name']))
            
            # 3. Проверка текущего устройства
            try:
                if self.current_device_index is not None:
                    sd.query_devices(self.current_device_index)
            except:
                self.current_device_index = sd.default.device[0]

            self.setup_audio()
            return inputs

        except Exception as e:
            print(f"Device update error: {e}")
            return [(0, "Error updating devices")]

    def show_settings_menu(self):
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #222; color: white; border: 1px solid #555; } QMenu::item:selected { background-color: #444; }")
        
        device_menu = menu.addMenu("Input Device")
        for idx, name in self.get_input_devices():
            act = QAction(name, self, checkable=True)
            act.setChecked(idx == self.current_device_index)
            act.triggered.connect(lambda checked, i=idx: self.change_device(i))
            device_menu.addAction(act)
        menu.addSeparator()

        act_sys = QAction("System Sound Settings", self)
        act_sys.triggered.connect(self.open_sound_settings)
        menu.addAction(act_sys)

        act_sys = QAction("Audio MIDI Setup", self)
        act_sys.triggered.connect(self.open_midi_setup)
        menu.addAction(act_sys)
        menu.addSeparator()

        act_spec = QAction('Show Spectrum (Cmd +)', self, checkable=True)
        act_spec.setChecked(self.show_spectrum)
        act_spec.triggered.connect(self.toggle_spectrum)
        menu.addAction(act_spec)

        min_freq_menu = menu.addMenu("Min Frequency")
        for f in self.available_min_freqs:
            act = QAction(f"{f} Hz", self, checkable=True)
            act.setChecked(self.MIN_FREQ == f)
            act.triggered.connect(lambda checked, freq=f: self.set_frequency('min', freq))
            min_freq_menu.addAction(act)

        max_freq_menu = menu.addMenu("Max Frequency")
        for f in self.available_max_freqs:
            act = QAction(f"{f} Hz", self, checkable=True)
            act.setChecked(self.MAX_FREQ == f)
            act.triggered.connect(lambda checked, freq=f: self.set_frequency('max', freq))
            max_freq_menu.addAction(act)
            
        menu.addSeparator()

        act_rms = QAction("RMS + PEAK", self, checkable=True)
        act_rms.setChecked(self.display_mode == "RMS")
        act_rms.triggered.connect(lambda: self.set_display_mode("RMS"))
        
        act_peak = QAction("PEAKs + RMS", self, checkable=True)
        act_peak.setChecked(self.display_mode == "PEAK")
        act_peak.triggered.connect(lambda: self.set_display_mode("PEAK"))

        menu.addAction(act_rms)
        menu.addAction(act_peak)
        menu.addSeparator()

        time_menu = menu.addMenu("Integration Time")
        for size in [10, 50, 300, 400]:
            act = QAction(f"{size}ms", self, checkable=True)
            act.setChecked(self.rms_window_size == size)
            act.triggered.connect(lambda checked, s=size: self.set_rms_window_size(s))
            time_menu.addAction(act)

        menu.exec(self.mapToGlobal(self.btn_settings.rect().bottomLeft()))

    def change_device(self, index):
        if index == self.current_device_index and not self.is_reconnecting:
            return
        self.current_device_index = index
        self.reconnect_audio()

    def set_frequency(self, freq_type, freq):
        if freq_type == 'min':
            self.MIN_FREQ = freq
        else:
            self.MAX_FREQ = freq
        self.band_centers = np.logspace(np.log10(self.MIN_FREQ), np.log10(self.MAX_FREQ), self.NUM_BANDS)
        self.filters = self.create_filters()
        self.filter_states = []
        for sos in self.filters:
            if sos is not None:
                self.filter_states.append(np.zeros((sos.shape[0], 2)))
            else:
                self.filter_states.append(None)
        self.band_levels.fill(-self.LEVEL_RANGE)
        self.smoothed_band_levels.fill(-self.LEVEL_RANGE)
        self.peak_band_levels.fill(-self.LEVEL_RANGE)
        self.peak_band_hold.fill(0)

    def toggle_spectrum(self, checked):
        self.show_spectrum = checked
        self.apply_window_size()

    def set_display_mode(self, mode):
        self.display_mode = mode

    def set_rms_window_size(self, size):
        self.rms_window_size = size
        self.update_rms_buffer()

    def update_rms_buffer(self):
        if hasattr(self, 'sample_rate') and self.sample_rate > 0:
            self.rms_buffer_size = int(self.rms_window_size * self.sample_rate / 1000)
            if hasattr(self, 'input_channels'):
                self.audio_buffer = np.zeros((self.rms_buffer_size, self.input_channels))
            self.buffer_index = 0

    def create_filters(self):
        filters = []
        nyquist = self.sample_rate / 2
        for i, center_freq in enumerate(self.band_centers):
            low = center_freq / (2**(1/6))
            high = center_freq * (2**(1/6))
            if i == self.NUM_BANDS - 1 and self.MAX_FREQ >= 16000:
                high = min(self.MAX_FREQ, nyquist - 1)
            try:
                order = 2 if center_freq < 200 else 4
                sos = signal.butter(order, [low, high], btype='bandpass', fs=self.sample_rate, output='sos')
                filters.append(sos)
            except:
                filters.append(None)
        return filters

    def toggle_record(self):
        if not self.recording:
            try:
                now = datetime.datetime.now()
                timestamp = now.strftime("%H-%M-%S %d%m%Y")
                date_str = now.strftime("%A %d%m%y")
                base_records_path = os.path.join(os.path.expanduser("~"), "Records")
                os.makedirs(os.path.join(base_records_path, date_str), exist_ok=True)
                
                filename = os.path.join(base_records_path, date_str, f"Record {timestamp}.wav")
                self.audio_file = wave.open(filename, 'wb')
                self.audio_file.setnchannels(self.input_channels)
                self.audio_file.setsampwidth(2)
                self.audio_file.setframerate(self.sample_rate)
                
                self.recording = True
                self.recording_start_time = now
                self.btn_record.setStyleSheet("background-color: darkred; color: white; border: 1px solid red;")
                self.rec_timer.start(1000)
                self.update_recording_time()
            except Exception as e:
                print(f"Error: {e}")
        else:
            self.recording = False
            self.rec_timer.stop()
            if self.audio_file:
                self.audio_file.close()
                self.audio_file = None
            self.btn_record.setText("Rec")
            self.btn_record.setStyleSheet("background-color: #111; color: #aaa; border: 1px solid #333;")

    def update_recording_time(self):
        if self.recording:
            elapsed = int((datetime.datetime.now() - self.recording_start_time).total_seconds())
            mins, secs = divmod(elapsed, 60)
            self.btn_record.setText(f"{mins:02d}:{secs:02d}")

    def reconnect_audio(self):
        if self.is_reconnecting:
            return
            
        self.is_reconnecting = True
        
        # Запоминаем, шла ли запись до обрыва
        was_recording = self.recording
        
        if was_recording:
            print("Обрыв потока: сохраняем текущий файл записи...")
            self.toggle_record() # Эта команда безопасно закроет текущий файл
        
        try:
            # Остановка старого стрима
            if hasattr(self, 'audio_stream') and self.audio_stream:
                try:
                    self.audio_stream.stop()
                    self.audio_stream.close()
                except Exception: pass
                self.audio_stream = None

            # Сброс PortAudio
            sd._terminate()
            sd._initialize()

            # Пытаемся настроить аудио
            self.setup_audio()
            self.apply_window_size()
            
            # Если стрим успешно создан и до обрыва шла запись
            if was_recording and hasattr(self, 'audio_stream') and self.audio_stream is not None:
                print("Связь восстановлена: начинаем запись в новый файл...")
                self.toggle_record() # Эта команда создаст новый файл и запустит таймер заново
                
        except Exception as e:
            print(f"Reconnect failed: {e}")
        finally:
            self.is_reconnecting = False

    def setup_audio(self):
        """Безопасная настройка потока с проверкой каналов"""
        try:
            if self.current_device_index is None:
                try:
                    self.current_device_index = sd.default.device[0]
                except Exception:
                    print("Аудиоустройства не найдены.")
                    return

            device_info = sd.query_devices(self.current_device_index, 'input')
            max_ch = device_info.get('max_input_channels', 0)
            
            if max_ch == 0:
                print(f"Device {self.current_device_index} has no input channels. Waiting...")
                # Пробуем откатиться на дефолт, если текущее устройство мертво
                if self.current_device_index != sd.default.device[0]:
                    self.current_device_index = None
                return

            self.input_channels = max_ch
            self.sample_rate = int(device_info.get('default_samplerate', 44100))

            # Пересоздаем массивы под актуальное кол-во каналов
            self.peak_level = [-self.LEVEL_RANGE] * self.input_channels
            self.rms_level = [-self.LEVEL_RANGE] * self.input_channels
            self.smoothed_level = [-self.LEVEL_RANGE] * self.input_channels
            self.peak_hold_counter = [0] * self.input_channels
            self.peak_display_level = [-self.LEVEL_RANGE] * self.input_channels
            self.rms_display_level = [-self.LEVEL_RANGE] * self.input_channels
            
            self.update_rms_buffer()
            self.filters = self.create_filters()
            self.filter_states = []
            for sos in self.filters:
                if sos is not None:
                    self.filter_states.append(np.zeros((sos.shape[0], 2)))
                else:
                    self.filter_states.append(None)
            
            self.audio_stream = sd.InputStream(
                device=self.current_device_index,
                samplerate=self.sample_rate,
                channels=self.input_channels,
                blocksize=2048,
                callback=self.audio_callback,
            )
            self.audio_stream.start()
            self.last_callback_time = time.time() # Фиксируем успешный старт
        except Exception as e:
            print(f"Setup failed: {e}")
            self.audio_stream = None # Больше не вызываем change_device(None), чтобы не было рекурсии

    def audio_callback(self, indata, frames, time_info, status):
        self.last_callback_time = time.time() # Фиксируем, что поток жив
        try:
            # Защита: количество каналов в данных должно совпадать с массивом уровней
            if indata.shape[1] != len(self.rms_level):
                return

            if self.recording and self.audio_file:
                audio_data_int16 = (indata * 32767).astype(np.int16)
                self.audio_file.writeframes(audio_data_int16.tobytes())
            
            frames_to_copy = min(frames, self.rms_buffer_size - self.buffer_index)
            self.audio_buffer[self.buffer_index:self.buffer_index + frames_to_copy] = indata[:frames_to_copy]
            self.buffer_index += frames_to_copy
            
            if self.buffer_index >= self.rms_buffer_size:
                self.buffer_index = 0
            
            for channel in range(self.input_channels):
                valid_data_count = min(self.buffer_index + frames, self.rms_buffer_size)
                if valid_data_count > 0:
                    channel_data = self.audio_buffer[:valid_data_count, channel]
                    rms = np.sqrt(np.mean(channel_data**2))
                    self.rms_level[channel] = 20 * np.log10(max(rms, 10**(-60/20)))
                else:
                    self.rms_level[channel] = -self.LEVEL_RANGE

                peak = np.max(np.abs(indata[:, channel]))
                peak_db = 20 * np.log10(max(min(peak, 1.0), 1e-6))
                
                if peak_db > self.peak_level[channel]:
                    self.peak_level[channel] = peak_db
                    self.peak_hold_counter[channel] = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)

                if self.display_mode == "PEAK":
                    if peak_db > self.peak_display_level[channel]:
                        self.peak_display_level[channel] = peak_db
                    if self.rms_level[channel] > self.rms_display_level[channel]:
                        self.rms_display_level[channel] = self.rms_level[channel]

            if self.show_spectrum:
                mono_signal = np.mean(indata, axis=1) if indata.shape[1] >= 2 else indata[:, 0]
                for i in range(self.NUM_BANDS):
                    sos = self.filters[i]
                    if sos is not None:
                        try:
                            filtered, self.filter_states[i] = signal.sosfilt(sos, mono_signal, zi=self.filter_states[i])
                            rms = np.sqrt(np.mean(filtered**2))
                            db_level = 20 * np.log10(max(rms, 1e-6))
                            self.band_levels[i] = max(min(db_level, 0), -self.LEVEL_RANGE)
                            if db_level > self.peak_band_levels[i]:
                                self.peak_band_levels[i] = db_level
                                self.peak_band_hold[i] = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)
                        except:
                            self.band_levels[i] = -self.LEVEL_RANGE
        except:
            pass

    def update_meter(self):
            # --- WATCHDOG (Защита от обрывов потока) ---
            if hasattr(self, 'last_callback_time') and (time.time() - self.last_callback_time > 1.5):
                # Проверяем, не находимся ли мы уже в процессе восстановления
                if not getattr(self, 'is_reconnecting', False):
                    print("Сработал Watchdog (Восстановление аудио)...")
                    self.last_callback_time = time.time()
                    self.reconnect_audio()
                return

            # Защита: если данные еще не готовы или идет переинициализация
            if not hasattr(self, 'rms_level') or len(self.rms_level) != self.input_channels:
                return

            level_exceeded = any(level > -3 for level in self.peak_level)
            self.title_label.setStyleSheet("color: red;" if level_exceeded else "color: lightgray;")

            for channel in range(self.input_channels):
                if channel >= len(self.rms_level): break
                if self.display_mode == "RMS":
                    if self.rms_level[channel] > self.smoothed_level[channel]:
                        self.smoothed_level[channel] = self.rms_level[channel]
                    else:
                        decay_amount = self.DECAY_RATE * (self.update_interval/1000)
                        self.smoothed_level[channel] = max(self.smoothed_level[channel] - decay_amount, -self.LEVEL_RANGE)
                else: 
                    if self.peak_display_level[channel] > -self.LEVEL_RANGE:
                        distance = (self.peak_display_level[channel] + self.LEVEL_RANGE) / self.LEVEL_RANGE
                        alpha = 0.005 + 0.01 * distance 
                        self.peak_display_level[channel] = (1 - alpha) * self.peak_display_level[channel] + alpha * (-self.LEVEL_RANGE)
                    if self.rms_level[channel] > self.smoothed_level[channel]:
                        alpha = 0.5
                    else:
                        distance = (self.rms_level[channel] + self.LEVEL_RANGE) / self.LEVEL_RANGE
                        alpha = 0.1 + 0.3 * distance
                    self.smoothed_level[channel] = (1 - alpha) * self.smoothed_level[channel] + alpha * self.rms_level[channel]

                if self.peak_hold_counter[channel] > 0:
                    self.peak_hold_counter[channel] -= 1
                else:
                    self.peak_level[channel] = (1 - 0.1) * self.peak_level[channel] + 0.1 * (-self.LEVEL_RANGE)

            if self.show_spectrum:
                for i in range(self.NUM_BANDS):
                    if self.band_levels[i] > self.smoothed_band_levels[i]:
                        self.smoothed_band_levels[i] = self.band_levels[i]
                    else:
                        decay_amount = self.DECAY_RATE * (self.update_interval/1000)
                        self.smoothed_band_levels[i] = max(self.smoothed_band_levels[i] - decay_amount, -self.LEVEL_RANGE)
                    if self.peak_band_hold[i] > 0:
                        self.peak_band_hold[i] -= 1
                    else:
                        decay_amount = self.DECAY_RATE * 2 * (self.update_interval/1000)
                        self.peak_band_levels[i] = max(self.peak_band_levels[i] - decay_amount, -self.LEVEL_RANGE)

            self.meter_canvas.update()

    def open_sound_settings(self):
        subprocess.run(["open", "x-apple.systempreferences:com.apple.Sound-Settings.extension"])

    def open_midi_setup(self):
        subprocess.run(["open", "-a", "Audio MIDI Setup.app"])

    def close_program(self):
        if self.recording: self.toggle_record()
        try:
            if hasattr(self, 'audio_stream') and self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
        except: pass
        self.timer.stop()
        self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    meter = AudioLevelMeter()
    screen = app.primaryScreen().geometry()
    meter.move(screen.width() - 200, screen.height() - 400)
    meter.show()
    sys.exit(app.exec())
