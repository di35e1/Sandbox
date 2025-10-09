import sounddevice as sd
import subprocess
import numpy as np
import tkinter as tk
from tkinter import font as tkfont
import os
from collections import deque
import wave
import datetime

class AudioLevelMeter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("VU Meter")
        self.root.config(menu=tk.Menu(self.root))

        # Window movement handlers
        self.root.bind("<ButtonPress-1>", self.start_move)
        self.root.bind("<ButtonRelease-1>", self.stop_move)
        self.root.bind("<B1-Motion>", self.do_move)

        # Получаем информацию о доступных устройствах
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        self.input_channels = devices[default_input]['max_input_channels']

        # Параметры окна (ширина зависит от количества каналов)
        self.window_width = 60 if self.input_channels == 1 else 70
        self.window_height = 350

        # Калибровка уровней
        self.LEVEL_RANGE = 60
        self.PEAK_HOLD_TIME = 1
        self.DECAY_RATE = 25
        
        # Размер окна RMS по умолчанию (в миллисекундах)
        self.rms_window_size = 300  # 300ms по умолчанию
        
        # Состояние уровней
        self.peak_level = [-self.LEVEL_RANGE] * self.input_channels
        self.rms_level = [-self.LEVEL_RANGE] * self.input_channels
        self.smoothed_level = [-self.LEVEL_RANGE] * self.input_channels
        self.peak_hold_counter = [0] * self.input_channels
        
        # Для режима PEAK - отдельные переменные для отображения
        self.peak_display_level = [-self.LEVEL_RANGE] * self.input_channels
        self.rms_display_level = [-self.LEVEL_RANGE] * self.input_channels  # Для плавного RMS
        
        # Режим отображения (RMS или PEAK)
        self.display_mode = "RMS"  # По умолчанию RMS
        
        # Состояние записи
        self.recording = False
        self.audio_file = None
        self.recording_start_time = 0
        self.recorded_data = []

        # Буфер для хранения данных (будет инициализирован после получения sample_rate)
        self.rms_buffer_size = 0
        self.audio_buffer = None
        self.buffer_index = 0

        self.setup_window()
        self.setup_ui()
        self.setup_audio()
        
        self.update_interval = 30
        self.root.after(self.update_interval, self.update_meter)
        self.root.mainloop()

    def setup_window(self):
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.7)
        self.root.configure(bg='black')
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - (120 if self.input_channels == 1 else 200)
        y = (screen_height - 440)
        self.root.geometry(f"+{x}+{y}")

    def setup_ui(self):
        title_font = tkfont.Font(family='Helvetica', size=12, weight='normal')
        title = "VU" if self.input_channels == 1 else "VU Meter"
        self.title_label = tk.Label(
            self.root, 
            width=self.window_width,
            text=title, 
            bg='black', 
            fg='lightgray', 
            font=title_font
        )
        self.title_label.pack(pady=5)

        self.meter_frame = tk.Frame(self.root, bg='black')
        self.meter_frame.pack()
        
        # Фрейм для индикаторов каналов
        self.indicators_frame = tk.Frame(self.meter_frame, bg='black')
        self.indicators_frame.pack(side=tk.LEFT, padx=(7,3))
        
        self.canvases = []
        if self.input_channels == 1:
            channel_label = "M"
            canvas = self.create_indicator(self.indicators_frame, channel_label)
            self.canvases.append(canvas)
        else:
            for i in range(self.input_channels):
                channel_label = "L" if i == 0 else "R"
                canvas = self.create_indicator(self.indicators_frame, channel_label)
                self.canvases.append(canvas)
        
        # Создаем шкалу
        self.scale_canvas = self.create_scale(self.meter_frame)

        self.buttons_frame = tk.Frame(self.root, bg='black')
        self.buttons_frame.pack(pady=5,side=tk.BOTTOM)

        # Кнопка Record
        self.record_button_canvas = tk.Canvas(
            self.buttons_frame,
            width=self.window_width,
            height=20,
            bg='black',
            highlightthickness=0
        )
        self.record_button_canvas.pack(pady=2)
        self.setup_record_button()

        # Кнопка Settings
        self.settings_button_canvas = tk.Canvas(
            self.buttons_frame,
            width=self.window_width,
            height=20,
            bg='black',
            highlightthickness=0
        )
        self.settings_button_canvas.pack(pady=2)
        self.setup_button(self.settings_button_canvas, "Settings", self.open_settings)

        # Кнопка Close
        self.close_button_canvas = tk.Canvas(
            self.buttons_frame,
            width=self.window_width,
            height=20,
            bg='black',
            highlightthickness=0
        )
        self.close_button_canvas.pack(pady=2)
        self.setup_button(self.close_button_canvas, "Close", self.close_program)

    def create_indicator(self, parent, channel):
        """Создает индикатор уровня для указанного канала"""
        channel_frame = tk.Frame(parent, bg='black')
        channel_frame.pack(side=tk.LEFT, padx=(2,1))
                
        channel_label = tk.Label(
            channel_frame, 
            text=channel, 
            bg='black', 
            fg='yellow', 
            font=("Arial", 8)
        )
        channel_label.pack(pady=0)

        canvas = tk.Canvas(
            channel_frame, 
            width=12,
            height=225, 
            bg='black', 
            highlightthickness=0
        )
        canvas.pack(pady=0)

        canvas.channel_label = channel_label
        
        # Основной индикатор (столбик)
        canvas.level_bar = canvas.create_rectangle(
            0, 220, 10, 220,
            fill='green', 
            outline='white', 
            width=0
        )
        
        # Пиковый индикатор (красная черта)
        canvas.peak_bar = canvas.create_line(
            0, 220, 10, 220, 
            fill='red', 
            width=1.5
        )
        
        # RMS индикатор (черная черта) - создаем, но скрываем по умолчанию
        canvas.rms_bar = canvas.create_line(
            0, 220, 10, 220, 
            fill='white', 
            width=2,
            state='hidden'  # Скрываем по умолчанию
        )
        
        return canvas

    def create_scale(self, parent):
        """Создает шкалу"""
        scale_frame = tk.Frame(parent, bg='black')
        scale_frame.pack(side=tk.LEFT, padx=(0,0))

        scale_label = tk.Label(
            scale_frame, 
            text="dB", 
            bg='black', 
            fg='yellow', 
            font=("Arial", 8)
        )
        scale_label.pack()

        canvas = tk.Canvas(
            scale_frame, 
            width=30, 
            height=225, 
            bg='black', 
            highlightthickness=0
        )
        canvas.pack(pady=0)

        # Создаем контекстное меню для шкалы
        self.scale_menu = tk.Menu(self.root, tearoff=0)
        
        # Переменные для отслеживания выбранного режима
        self.rms_mode_var = tk.BooleanVar(value=True)  # По умолчанию RMS выбран
        self.peak_mode_var = tk.BooleanVar(value=False)
        
        # Добавляем команды с галочками
        self.scale_menu.add_checkbutton(
            label="RMS Mode", 
            variable=self.rms_mode_var,
            command=lambda: self.set_display_mode("RMS")
        )
        self.scale_menu.add_checkbutton(
            label="PEAK Mode", 
            variable=self.peak_mode_var,
            command=lambda: self.set_display_mode("PEAK")
        )
        
        # Добавляем разделитель
        self.scale_menu.add_separator()
        
        # Добавляем подменю для выбора размера окна RMS
        self.rms_window_menu = tk.Menu(self.scale_menu, tearoff=0)
        
        # Переменные для отслеживания выбранного размера окна
        self.rms_window_vars = {
            25: tk.BooleanVar(value=False),
            50: tk.BooleanVar(value=False),
            100: tk.BooleanVar(value=False),
            200: tk.BooleanVar(value=False),
            300: tk.BooleanVar(value=True)  # По умолчанию 300ms
        }
        
        # Добавляем опции размера окна RMS
        self.rms_window_menu.add_checkbutton(
            label="RMS Window: 25ms",
            variable=self.rms_window_vars[25],
            command=lambda: self.set_rms_window_size(25)
        )       
        self.rms_window_menu.add_checkbutton(
            label="RMS Window: 50ms",
            variable=self.rms_window_vars[50],
            command=lambda: self.set_rms_window_size(50)
        )
        self.rms_window_menu.add_checkbutton(
            label="RMS Window: 100ms", 
            variable=self.rms_window_vars[100],
            command=lambda: self.set_rms_window_size(100)
        )
        self.rms_window_menu.add_checkbutton(
            label="RMS Window: 200ms",
            variable=self.rms_window_vars[200],
            command=lambda: self.set_rms_window_size(200)
        )
        self.rms_window_menu.add_checkbutton(
            label="RMS Window: 300ms",
            variable=self.rms_window_vars[300],
            command=lambda: self.set_rms_window_size(300)
        )
        
        # Добавляем подменю в основное меню
        self.scale_menu.add_cascade(label="RMS Window Size", menu=self.rms_window_menu)
        
        # Привязываем правую кнопку мыши (Button-2) к показу меню
        canvas.bind("<Button-2>", self.show_scale_menu)
        scale_frame.bind("<Button-2>", self.show_scale_menu)

        db_scale = [-1, -6, -12, -18, -24, -30, -35, -40, -45, -50, -55, -60]
        for db in db_scale:
            y_pos = 220 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            color = "red" if db >= -6 else "orange" if db >= -12 else "green"
            canvas.create_line(0, y_pos, 6, y_pos, fill=color, width=1.5)
            canvas.create_text(
                23, 
                y_pos, 
                text=f"{db}", 
                fill="white", 
                font=("Arial", 8), 
                anchor="e"
            )
        
        return canvas

    def show_scale_menu(self, event):
        """Показывает контекстное меню для выбора режима отображения и размера окна RMS"""
        # Обновляем галочки перед показом меню
        if self.display_mode == "RMS":
            self.rms_mode_var.set(True)
            self.peak_mode_var.set(False)
        else:
            self.rms_mode_var.set(False)
            self.peak_mode_var.set(True)
        
        # Обновляем галочки размера окна RMS
        for size, var in self.rms_window_vars.items():
            var.set(size == self.rms_window_size)
        
        try:
            self.scale_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.scale_menu.grab_release()

    def set_display_mode(self, mode):
        """Устанавливает режим отображения (RMS или PEAK)"""
        self.display_mode = mode
        
        # Обновляем галочки в меню
        if mode == "RMS":
            self.rms_mode_var.set(True)
            self.peak_mode_var.set(False)
        else:
            self.rms_mode_var.set(False)
            self.peak_mode_var.set(True)
        
        print(f"Display mode changed to: {mode}")
        
        # Показываем или скрываем RMS черту в зависимости от режима
        for canvas in self.canvases:
            if mode == "PEAK":
                canvas.itemconfig(canvas.rms_bar, state='normal')  # Показываем
            else:
                canvas.itemconfig(canvas.rms_bar, state='hidden')  # Скрываем

    def set_rms_window_size(self, window_size_ms):
        """Устанавливает размер окна для расчета RMS"""
        if window_size_ms != self.rms_window_size:
            self.rms_window_size = window_size_ms
            self.update_rms_buffer()
            print(f"RMS window size changed to: {window_size_ms}ms")

    def update_rms_buffer(self):
        """Обновляет размер буфера RMS при изменении размера окна"""
        if hasattr(self, 'sample_rate') and self.sample_rate > 0:
            # Пересчитываем размер буфера
            self.rms_buffer_size = int(self.rms_window_size * self.sample_rate / 1000)
            
            # Создаем новый буфер
            self.audio_buffer = np.zeros((self.rms_buffer_size, self.input_channels))
            self.buffer_index = 0
            
            print(f"RMS buffer updated: {self.rms_buffer_size} samples ({self.rms_window_size}ms)")

    def setup_record_button(self):
        """Настраивает кнопку записи c таймингом"""
        canvas = self.record_button_canvas
        button_width = canvas.winfo_reqwidth() - 10
        button_height = canvas.winfo_reqheight() - 4
        x_center = self.window_width // 2
        x1 = x_center - button_width // 2
        x2 = x_center + button_width // 2

        button_bg = canvas.create_rectangle(
            x1, 0, x2, button_height,
            fill='#000000',
            outline="#333333",
            width=1
        )

        button_text = canvas.create_text(
            x_center, button_height // 2,
            text="Rec",
            fill='#555555',
            font=("Helvetica", 10)
        )

        canvas.button_bg = button_bg
        canvas.button_text = button_text
        canvas.command = self.toggle_record

        canvas.bind("<Button-1>", self.on_button_click)
        canvas.bind("<Enter>", self.on_button_enter)
        canvas.bind("<Leave>", self.on_button_leave)

    def setup_button(self, canvas, text, command):
        """Настраивает обычную кнопку"""
        button_width = canvas.winfo_reqwidth() - 10
        button_height = canvas.winfo_reqheight() - 4 
        x_center = self.window_width // 2
        x1 = x_center - button_width // 2
        x2 = x_center + button_width // 2

        button_bg = canvas.create_rectangle(
            x1, 0, x2, button_height,
            fill='#000000',
            outline="#333333",
            width=1
        )

        button_text = canvas.create_text(
            x_center, button_height // 2,
            text=text,
            fill='#555555',
            font=("Helvetica", 10)
        )

        canvas.button_bg = button_bg
        canvas.button_text = button_text
        canvas.command = command

        canvas.bind("<Button-1>", self.on_button_click)
        canvas.bind("<Enter>", self.on_button_enter)
        canvas.bind("<Leave>", self.on_button_leave)

    def on_button_click(self, event):
        canvas = event.widget
        canvas.itemconfig(canvas.button_bg, fill="black")
        self.root.after(100, lambda: canvas.command())
        
    def on_button_enter(self, event):
        canvas = event.widget
        if canvas == self.close_button_canvas or canvas == self.settings_button_canvas:
            color = '#555555'
        elif canvas == self.record_button_canvas and self.recording:
            canvas.itemconfig(canvas.button_text, fill='white')
            canvas.itemconfig(canvas.button_text, text="STOP")
            color='red'
        elif canvas == self.record_button_canvas:
            color = 'red'
        canvas.itemconfig(canvas.button_bg, fill=color)
        canvas.itemconfig(canvas.button_text, fill='white')

    def on_button_leave(self, event):
        canvas = event.widget
        canvas.itemconfig(canvas.button_bg, fill='#000000')
        if canvas == self.record_button_canvas and self.recording:
            canvas.itemconfig(canvas.button_text, text=self.format_recording_time())
            canvas.itemconfig(canvas.button_bg, fill='#550000')
        else:
            canvas.itemconfig(canvas.button_text, fill='#555555')

    def format_recording_time(self):
        """Форматирует время записи в формат ММ:СС или ЧЧ:ММ:СС"""
        if not self.recording:
            return ""
        current_time = datetime.datetime.now()
        time_difference = (current_time - self.recording_start_time)
        elapsed = int(time_difference.total_seconds())
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        
        if hours > 0 or minutes >= 60:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}m {seconds:02d}s"

    def update_recording_time(self):
        """Обновляет отображение времени записи"""
        if self.recording:
            self.record_button_canvas.itemconfig(
                self.record_button_canvas.button_text, 
                text=self.format_recording_time()
            )
            self.root.after(1000, self.update_recording_time)
        
    def toggle_record(self):
        """Включает/выключает запись звука"""
        if not self.recording:
            # Начинаем запись
            try:
                now = datetime.datetime.now()
                timestamp = now.strftime("%H-%M-%S %d%m%Y")
                date_str = now.strftime("%A %d%m%y")
                base_records_path = os.path.join(os.path.expanduser("~"), "Records")
                records_path = os.path.join(base_records_path, date_str)

                os.makedirs(records_path, exist_ok=True)
                filename = os.path.join(records_path, f"Record {timestamp}.wav")
                
                self.audio_file = wave.open(filename, 'wb')
                self.audio_file.setnchannels(self.input_channels)
                self.audio_file.setsampwidth(2)
                self.audio_file.setframerate(self.sample_rate)
                
                self.recording = True
                self.recording_start_time = now
                
                # Запускаем обновление времени записи
                self.update_recording_time()
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, fill='white')
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_bg, fill='#550000')
                print(f"Recording started: {filename}")

            except Exception as e:
                print(f"Error starting recording: {e}")
                self.recording = False
        else:
            # Останавливаем запись
            try:
                self.recording = False
                if self.audio_file:
                    self.audio_file.close()
                    self.audio_file = None
                    print("Recording stopped and file saved")
                
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, text="Record")
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, fill='#555555')
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_bg, fill='black')
            except Exception as e:
                print(f"Error stopping recording: {e}")

    def setup_audio(self):
        try:
            device_info = sd.query_devices(sd.default.device[0])
            self.sample_rate = int(device_info['default_samplerate'])
            print(f"Using device sample rate: {self.sample_rate} Hz")
            
            # Инициализация буфера для RMS данных
            self.update_rms_buffer()  # Использует текущий rms_window_size
            
            self.audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.input_channels,
                blocksize=2048,
                callback=self.audio_callback,
            )
            self.audio_stream.start()

        except Exception as e:
            print(f"Audio error: {e}")
            self.root.destroy()
            raise

    def audio_callback(self, indata, frames, time, status):
        if status:
            print(status)

        # Записываем данные в файл, WAV 16bit
        if self.recording and self.audio_file:
            try:
                audio_data_int16 = (indata * 32767).astype(np.int16)
                self.audio_file.writeframes(audio_data_int16.tobytes())
            except Exception as e:
                print(f"Error writing to audio file: {e}")
        
        # Добавляем новые данные в буфер
        frames_to_copy = min(frames, self.rms_buffer_size - self.buffer_index)
        self.audio_buffer[self.buffer_index:self.buffer_index + frames_to_copy] = indata[:frames_to_copy]
        self.buffer_index += frames_to_copy
        
        # Если буфер заполнен, сдвигаем данные
        if self.buffer_index >= self.rms_buffer_size:
            self.buffer_index = 0
        
        # Обновляем уровни
        for channel in range(self.input_channels):
            # Используем все доступные данные из буфера для расчета RMS
            valid_data_count = min(self.buffer_index + frames, self.rms_buffer_size)
            if valid_data_count > 0:
                channel_data = self.audio_buffer[:valid_data_count, channel]
                rms = np.sqrt(np.mean(channel_data**2))
                self.rms_level[channel] = 20 * np.log10(max(rms, 10**(-60/20)))
            else:
                self.rms_level[channel] = -self.LEVEL_RANGE

            # Пик рассчитывается только из текущего блока (как раньше)
            peak = np.max(np.abs(indata[:, channel]))
            peak_capped = min(peak, 1.0)  # ограничивает индикатор на 0 dB (1.0)

            peak_db = 20 * np.log10(max(peak_capped, 1e-6))
            
            # Обновляем пиковый уровень с задержкой (для красной черты)
            if peak_db > self.peak_level[channel]:
                self.peak_level[channel] = peak_db
                self.peak_hold_counter[channel] = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)

            # Для режима PEAK - обновляем отображаемые уровни
            if self.display_mode == "PEAK":
                # Столбик - пиковые значения с плавным затуханием (в 2 раза быстрее)
                if peak_db > self.peak_display_level[channel]:
                    self.peak_display_level[channel] = peak_db
                else:
                    # Плавное затухание для peak_display_level (в 2 раза быстрее чем RMS)
                    decay_amount = self.DECAY_RATE * 2 * (self.update_interval/1000)
                    self.peak_display_level[channel] = max(
                        self.peak_display_level[channel] - decay_amount, 
                        -self.LEVEL_RANGE
                    )
                
                # Черная черта RMS - плавное обновление с DECAY_RATE = 25
                if self.rms_level[channel] > self.rms_display_level[channel]:
                    self.rms_display_level[channel] = self.rms_level[channel]
                else:
                    # Плавное затухание для RMS черты с DECAY_RATE = 25
                    decay_amount = self.DECAY_RATE * (self.update_interval/1000)
                    self.rms_display_level[channel] = max(
                        self.rms_display_level[channel] - decay_amount, 
                        -self.LEVEL_RANGE
                    )

    def update_meter(self):
        level_exceeded_title = any(level > -3 for level in self.peak_level)
        new_color = 'red' if level_exceeded_title else 'black'
        if new_color != self.title_label.cget('bg'):
            self.title_label.configure(bg=new_color)

        for channel in range(self.input_channels):
            canvas = self.canvases[channel]

            level_exceeded_channel = self.peak_level[channel] > -6
            new_color = 'red' if level_exceeded_channel else 'orange'
            if new_color != canvas.channel_label.cget('fg'):
                canvas.channel_label.config(fg=new_color)

            # Обновляем smoothed_level в зависимости от режима отображения
            if self.display_mode == "RMS":
                # Режим RMS - работает как раньше
                if self.rms_level[channel] > self.smoothed_level[channel]:
                    self.smoothed_level[channel] = self.rms_level[channel]
                else:
                    decay_amount = self.DECAY_RATE * (self.update_interval/1000)
                    self.smoothed_level[channel] = max(
                        self.smoothed_level[channel] - decay_amount, 
                        -self.LEVEL_RANGE
                    )
                
                # Используем smoothed_level для отображения столбика
                display_level = self.smoothed_level[channel]
            else:
                # Режим PEAK - используем peak_display_level для отображения столбика (плавный, но быстрый)
                display_level = self.peak_display_level[channel]
            
            # Обновляем пиковую черту (как раньше)
            if self.peak_hold_counter[channel] > 0:
                self.peak_hold_counter[channel] -= 1
            else:
                decay_amount = self.DECAY_RATE * 2 * (self.update_interval/1000)
                self.peak_level[channel] = max(
                    self.peak_level[channel] - decay_amount, 
                    -self.LEVEL_RANGE
                )
            
            def db_to_pos(db):
                return 220 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            
            # Позиции для отображения
            display_pos = db_to_pos(display_level)
            peak_pos = db_to_pos(self.peak_level[channel])
            
            # В режиме PEAK используем плавный RMS для черной черты
            if self.display_mode == "PEAK":
                rms_pos = db_to_pos(self.rms_display_level[channel])
            else:
                rms_pos = db_to_pos(self.rms_level[channel])
            
            # Обновляем основной столбик
            canvas.coords(canvas.level_bar, 0, display_pos, 10, 220)
            
            # Обновляем пиковую черту (красная линия)
            canvas.coords(canvas.peak_bar, 0, peak_pos, 10, peak_pos)
            
            # Обновляем RMS черту (черная линия) только в режимe PEAK
            if self.display_mode == "PEAK":
                canvas.coords(canvas.rms_bar, 0, rms_pos, 10, rms_pos)
            
            # Выбираем цвет для основного столбика
            if display_level > -6:
                color = 'red'
            elif display_level > -12:
                color = 'orange'
            else:
                color = 'green'
            
            canvas.itemconfig(canvas.level_bar, fill=color)
        
        self.root.after(self.update_interval, self.update_meter)

    def start_move(self, event):
        self.drag_data = {"x": event.x, "y": event.y}

    def stop_move(self, event):
        self.drag_data = None

    def do_move(self, event):
        x = self.root.winfo_x() + (event.x - self.drag_data["x"])
        y = self.root.winfo_y() + (event.y - self.drag_data["y"])
        self.root.geometry(f"+{x}+{y}")

    def open_settings(self):
        sound_uri = "x-apple.systempreferences:com.apple.Sound-Settings.extension"
        subprocess.run(["open", sound_uri], check=True)

    def close_program(self):
        """Корректно закрывает программу"""
        try:
            if self.recording:
                self.recording = False
                if self.audio_file:
                    self.audio_file.close()
                    self.audio_file = None
            
            if hasattr(self, 'audio_stream') and self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
            if hasattr(self, 'output_stream') and self.output_stream:
                self.output_stream.stop()
                self.output_stream.close()
        except Exception as e:
            print(f"Error closing audio streams: {e}")
        
        try:
            self.root.after_cancel(self.update_meter)
        except:
            pass
        
        try:
            self.root.destroy()
        except:
            pass
            print("Oops")

if __name__ == "__main__":
    try:
        app = AudioLevelMeter()
    except Exception as e:
        print(f"Application error: {e}")
