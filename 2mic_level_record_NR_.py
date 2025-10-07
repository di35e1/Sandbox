import sounddevice as sd
import subprocess
import numpy as np
import tkinter as tk
from tkinter import font as tkfont
import sys
import os
import threading
from collections import deque
import wave
import time
import noisereduce as nr

class AudioLevelMeter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Audio Level Meter")
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
        self.window_width = 76 if self.input_channels == 1 else 96
        self.window_height = 350

        # Калибровка уровней
        self.LEVEL_RANGE = 60
        self.PEAK_HOLD_TIME = 1
        self.DECAY_RATE = 25
        
        # Состояние уровней
        self.peak_level = [-self.LEVEL_RANGE] * self.input_channels
        self.rms_level = [-self.LEVEL_RANGE] * self.input_channels
        self.smoothed_level = [-self.LEVEL_RANGE] * self.input_channels
        self.last_peak_time = [0] * self.input_channels
        self.peak_hold_counter = [0] * self.input_channels
        
        # Состояние мониторинга
        self.monitoring = False
        self.output_stream = None
        self.audio_buffer = deque(maxlen=10)
        self.buffer_lock = threading.Lock()
        
        # Состояние записи
        self.recording = False
        self.audio_file = None
        self.recording_start_time = 0
        self.recorded_data = []
        self.bullet_visible = False
        
        # Шумоподавление
        self.noise_reduction = False
        self.noise_profile = None
        self.noise_profile_captured = False
        self.noise_capture_frames = 0
        self.noise_samples = []
        self.profile_capture_start = None
        self.NOISE_PROFILE_DURATION = 3.0  # Сэмпл шума в секундах
        self.noise_decrease = 0.6 # Уровень шумоподавления 0 - 1.0
        
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
        title = "Mic Level"
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
        
        # Создаем основной фрейм для индикаторов и шкалы
        self.main_meter_frame = tk.Frame(self.meter_frame, bg='black')
        self.main_meter_frame.pack(padx=0)
        
        # Фрейм для индикаторов каналов
        self.indicators_frame = tk.Frame(self.main_meter_frame, bg='black')
        self.indicators_frame.pack(side=tk.LEFT, padx=5)
        
        self.canvases = []
        if self.input_channels == 1:
            channel_label = "Mono"
            canvas = self.create_indicator(self.indicators_frame, channel_label)
            self.canvases.append(canvas)
        else:
            for i in range(self.input_channels):
                channel_label = "L" if i == 0 else "R"
                canvas = self.create_indicator(self.indicators_frame, channel_label)
                self.canvases.append(canvas)
        
        # Создаем общую шкалу справа
        self.scale_canvas = self.create_scale(self.main_meter_frame)

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

        self.noise_reduction_button_canvas = tk.Canvas(
                self.buttons_frame,
                width=self.window_width,
                height=20,
                bg='black',
                highlightthickness=0
            )
        self.noise_reduction_button_canvas.pack(pady=2)
        self.setup_noise_reduction_button()
                
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
        """Создает индикатор уровня для указанного канала без шкалы"""
        channel_frame = tk.Frame(parent, bg='black')
        channel_frame.pack(side=tk.LEFT, padx=1)
                
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
            width=20,
            height=225, 
            bg='black', 
            highlightthickness=0
        )
        canvas.pack(pady=0)

        canvas.channel_label = channel_label
        
        # Создаем только индикатор уровня (полоску)
        canvas.level_bar = canvas.create_rectangle(
            0, 220, 20, 220,  # Занимает почти всю ширину canvas
            fill='green', 
            outline='white', 
            width=1
        )
        
        # Пиковый индикатор - тонкая линия сверху индикатора
        canvas.peak_bar = canvas.create_line(
            0, 220, 20, 220, 
            fill='red', 
            width=1.5
        )
        
        return canvas

    def create_scale(self, parent):
        """Создает общую шкалу уровней справа"""
        scale_frame = tk.Frame(parent, bg='black')
        scale_frame.pack(side=tk.LEFT, padx=0)

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

        db_scale = [-1, -6, -12, -18, -24, -30, -35, -40, -45, -50, -55, -60]
        for db in db_scale:
            y_pos = 220 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            color = "red" if db >= -6 else "orange" if db >= -12 else "green"
            canvas.create_line(0, y_pos, 10, y_pos, fill=color, width=1.5)
            canvas.create_text(
                28, 
                y_pos, 
                text=f"{db}", 
                fill="white", 
                font=("Arial", 8), 
                anchor="e"
            )
        
        return canvas

    def setup_noise_reduction_button(self):
        """Настраивает кнопку шумоподавления"""
        canvas = self.noise_reduction_button_canvas
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

        indicator_size = 3
        indicator_x = x_center - button_width // 2 + 8
        indicator_y = button_height // 2
        indicator = canvas.create_oval(
            indicator_x - indicator_size, indicator_y - indicator_size,
            indicator_x + indicator_size, indicator_y + indicator_size,
            fill='#333333', outline=''
        )

        button_text = canvas.create_text(
            x_center+3, button_height // 2,
            text="NR OFF",
            fill='#555555',
            font=("Helvetica", 9)
        )

        canvas.button_bg = button_bg
        canvas.button_text = button_text
        canvas.indicator = indicator
        canvas.command = self.toggle_noise_reduction

        canvas.bind("<Button-1>", self.on_button_click)
        canvas.bind("<Enter>", self.on_noise_button_enter)
        canvas.bind("<Leave>", self.on_noise_button_leave)

    def toggle_noise_reduction(self):
        """Включает/выключает шумоподавление"""
            
        self.noise_reduction = not self.noise_reduction

        
        if self.noise_reduction:
            # Сбрасываем профиль шума
            self.noise_profile = None
            self.noise_profile_captured = False
            self.noise_capture_frames = 0
            self.noise_samples = []
            self.profile_capture_start = time.time()
            
            # Обновляем внешний вид кнопки
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_text, 
                text="learning",
                fill='yellow'
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.indicator,
                fill='yellow'
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_bg,
                fill='#333300'
            )
            print("Noise reduction enabled - capturing noise profile...")
        else:
            # Обновляем внешний вид кнопки
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_text, 
                text="NR OFF",
                fill='#555555'
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.indicator,
                fill='#333333'
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_bg,
                fill='#000000'
            )
            print("Noise reduction disabled")

    def on_noise_button_enter(self, event):
        """Обработчик наведения на кнопку шумоподавления"""
            
        canvas = event.widget
        if self.noise_reduction:
            if not self.noise_profile_captured:
                canvas.itemconfig(canvas.button_bg, fill='#444400')
            else:
                canvas.itemconfig(canvas.button_bg, fill='#004400')
        else:
            canvas.itemconfig(canvas.button_bg, fill='#330000')
        canvas.itemconfig(canvas.button_text, fill='white')

    def on_noise_button_leave(self, event):
        """Обработчик ухода с кнопки шумоподавления"""
            
        canvas = event.widget
        if self.noise_reduction:
            if not self.noise_profile_captured:
                canvas.itemconfig(canvas.button_bg, fill='#333300')
                canvas.itemconfig(canvas.button_text, fill='yellow')
            else:
                canvas.itemconfig(canvas.button_bg, fill='#003300')
                canvas.itemconfig(canvas.button_text, fill='white')
        else:
            canvas.itemconfig(canvas.button_bg, fill='#000000')
            canvas.itemconfig(canvas.button_text, fill='#555555')

    def setup_record_button(self):
        """Настраивает кнопку записи с буллетом"""
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

        bullet_size = 3
        bullet_x = x_center
        bullet_y = button_height // 2
        bullet = canvas.create_oval(
            bullet_x - bullet_size, bullet_y - bullet_size,
            bullet_x + bullet_size, bullet_y + bullet_size,
            fill='red', outline=''
        )
        canvas.itemconfig(bullet, state='hidden')

        button_text = canvas.create_text(
            x_center, button_height // 2,
            text="Record",
            fill='#555555',
            font=("Helvetica", 10)
        )

        canvas.button_bg = button_bg
        canvas.button_text = button_text
        canvas.bullet = bullet
        canvas.command = self.toggle_record

        canvas.bind("<Button-1>", self.on_button_click)
        canvas.bind("<Enter>", self.on_button_enter)
        canvas.bind("<Leave>", self.on_button_leave)

    def setup_button(self, canvas, text, command):
        """Настраивает обычную кнопку без буллета"""
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
        if canvas == self.close_button_canvas:
            color = 'black'
            canvas.itemconfig(canvas.button_text, fill='white')
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
        else:
            canvas.itemconfig(canvas.button_text, fill='#555555')

    def format_recording_time(self):
        """Форматирует время записи в формат ЧЧ:ММ:СС"""
        if not self.recording:
            return ""
        elapsed = int(time.time() - self.recording_start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def update_recording_time(self):
        """Обновляет отображение времени записи"""
        if self.recording:
            self.record_button_canvas.itemconfig(
                self.record_button_canvas.button_text, 
                text=self.format_recording_time()
            )
            self.root.after(1000, self.update_recording_time)

    def capture_noise_profile(self, audio_data):
        """Захватывает профиль шума"""
        if self.noise_profile_captured or not self.noise_reduction:
            return
            
        # Простой захват профиля по времени
        if self.profile_capture_start is None:
            self.profile_capture_start = time.time()
            
        elapsed = time.time() - self.profile_capture_start
        
        if elapsed < self.NOISE_PROFILE_DURATION:
            # Накопление samples
            self.noise_samples.append(audio_data.copy())
        else:
            # Захват завершен
            try:
                if len(self.noise_samples) > 0:
                    self.noise_profile = np.concatenate(self.noise_samples, axis=0)
                    self.noise_profile_captured = True
                    
                    # Обновляем кнопку
                    self.noise_reduction_button_canvas.itemconfig(
                        self.noise_reduction_button_canvas.button_text, 
                        text="NR ON",
                        fill='white'
                    )
                    self.noise_reduction_button_canvas.itemconfig(
                        self.noise_reduction_button_canvas.indicator,
                        fill='green'
                    )
                    self.noise_reduction_button_canvas.itemconfig(
                        self.noise_reduction_button_canvas.button_bg,
                        fill='#003300'
                    )
                    print("Noise profile captured successfully!")
            except Exception as e:
                print(f"Error capturing noise profile: {e}")
                self.noise_reduction = False

    def apply_noise_reduction(self, audio_data):
        """Применяет шумоподавление к аудиоданным"""
        if not self.noise_reduction:
            return audio_data
            
        try:
            # Если профиль еще не захвачен, продолжаем захват
            if not self.noise_profile_captured:
                self.capture_noise_profile(audio_data)
                return audio_data
            
            # Проверяем, что у нас есть профиль шума
            if self.noise_profile is None or len(self.noise_profile) == 0:
                return audio_data
            
            # Упрощенное шумоподавление с проверками
            if self.input_channels == 1:
                # Моно аудио
                audio_clean = nr.reduce_noise(
                    y=audio_data.flatten(),
                    sr=self.sample_rate,
                    y_noise=self.noise_profile.flatten() if len(self.noise_profile.flatten()) > 0 else audio_data.flatten(),
                    prop_decrease=self.noise_decrease,
                    stationary=True
                )
                return audio_clean.reshape(-1, 1)
            else:
                # Стерео аудио - обрабатываем каждый канал
                processed_channels = []
                for ch in range(self.input_channels):
                    # Берем часть профиля шума для этого канала
                    noise_channel = self.noise_profile[:, ch] if self.noise_profile.shape[1] > ch else self.noise_profile[:, 0]
                    
                    audio_clean = nr.reduce_noise(
                        y=audio_data[:, ch],
                        sr=self.sample_rate,
                        y_noise=noise_channel,
                        prop_decrease=self.noise_decrease,
                        stationary=True
                    )
                    processed_channels.append(audio_clean)
                
                return np.column_stack(processed_channels)
                
        except Exception as e:
            print(f"Noise reduction error: {e}")
            # Отключаем шумоподавление при ошибке
            self.noise_reduction = False
            return audio_data
        
    def toggle_record(self):
        """Включает/выключает запись звука"""
        if not self.recording:
            # Начинаем запись
            try:
                timestamp = time.strftime("%H-%M %d%m%Y")
                desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
                filename = os.path.join(desktop_path, f"Record {timestamp}.wav")
                
                self.audio_file = wave.open(filename, 'wb')
                self.audio_file.setnchannels(self.input_channels)
                self.audio_file.setsampwidth(2)
                self.audio_file.setframerate(self.sample_rate)
                
                self.recording = True
                self.recording_start_time = time.time()
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, text="00:00:00")
                
                # Запускаем обновление времени записи
                self.update_recording_time()
                
                # Сбрасываем профиль шума при начале записи
                if self.noise_reduction:
                    self.noise_profile = None
                    self.noise_profile_captured = False
                    self.noise_capture_frames = 0
                    self.noise_samples = []
                    self.profile_capture_start = time.time()
                    
                    self.noise_reduction_button_canvas.itemconfig(
                        self.noise_reduction_button_canvas.button_text, 
                        text="learning",
                        fill='yellow'
                    )
                    self.noise_reduction_button_canvas.itemconfig(
                        self.noise_reduction_button_canvas.indicator,
                        fill='yellow'
                    )
                    self.noise_reduction_button_canvas.itemconfig(
                        self.noise_reduction_button_canvas.button_bg,
                        fill='#333300'
                    )
                
                print(f"Recording started: {filename}")

            except Exception as e:
                print(f"Error starting recording: {e}")
                self.recording = False
        else:
            # Останавливаем запись
            try:
                self.recording = False
                self.record_button_canvas.itemconfig(self.record_button_canvas.bullet, state='hidden')
                
                if self.audio_file:
                    self.audio_file.close()
                    self.audio_file = None
                    print("Recording stopped and file saved")
                
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, text="Record")
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, fill='#555555')
            except Exception as e:
                print(f"Error stopping recording: {e}")

    def setup_audio(self):
        try:
            device_info = sd.query_devices(sd.default.device[0])
            self.sample_rate = int(device_info['default_samplerate'])
            
            print(f"Using device sample rate: {self.sample_rate} Hz")
            
            self.audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.input_channels,
                blocksize=1024,
                callback=self.audio_callback
            )
            self.audio_stream.start()
        except Exception as e:
            print(f"Audio error: {e}")
            self.root.destroy()
            raise

    def audio_callback(self, indata, frames, time, status):
        if status:
            print(status)

        # Применяем шумоподавление если включено и доступно
        processed_data = indata.copy()
        if self.noise_reduction:
            processed_data = self.apply_noise_reduction(indata)

        # Записываем данные в файл
        if self.recording and self.audio_file:
            try:
                audio_data_int16 = (processed_data * 32767).astype(np.int16)
                self.audio_file.writeframes(audio_data_int16.tobytes())
            except Exception as e:
                print(f"Error writing to audio file: {e}")
        
        # Обновляем уровни
        for channel in range(self.input_channels):
            channel_data = processed_data[:, channel]
            rms = np.sqrt(np.mean(channel_data**2))
            self.rms_level[channel] = 20 * np.log10(max(rms, 10**(-60/20)))

            peak = np.max(np.abs(channel_data))
            peak_db = 20 * np.log10(max(peak, 1e-6))
            
            if peak_db > self.peak_level[channel]:
                self.peak_level[channel] = peak_db
                self.last_peak_time[channel] = time.currentTime
                self.peak_hold_counter[channel] = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)

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

            if self.rms_level[channel] > self.smoothed_level[channel]:
                self.smoothed_level[channel] = self.rms_level[channel]
            else:
                decay_amount = self.DECAY_RATE * (self.update_interval/1000)
                self.smoothed_level[channel] = max(
                    self.smoothed_level[channel] - decay_amount, 
                    -self.LEVEL_RANGE
                )
            
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
            
            rms_pos = db_to_pos(self.smoothed_level[channel])
            peak_pos = db_to_pos(self.peak_level[channel])
            
            canvas.coords(canvas.level_bar, 0, rms_pos, 18, 220)
            canvas.coords(canvas.peak_bar, 0, peak_pos, 18, peak_pos)
            
            if self.smoothed_level[channel] > -6:
                color = 'red'
            elif self.smoothed_level[channel] > -15:
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
        
        try:
            sys.exit(0)
        except:
            os._exit(0)


if __name__ == "__main__":
    try:
        app = AudioLevelMeter()
    except Exception as e:
        print(f"Application error: {e}")
