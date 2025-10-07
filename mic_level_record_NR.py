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
        self.window_width = 70 if self.input_channels == 1 else 120
        self.window_height = 350  # Увеличиваем высоту для кнопки

        # Калибровка уровней
        self.LEVEL_RANGE = 60  # Диапазон 60 dB
        self.PEAK_HOLD_TIME = 1 # Удержание пика (сек)
        self.DECAY_RATE = 25  # Скорость затухания (dB/сек)
        
        # Состояние уровней
        self.peak_level = [-self.LEVEL_RANGE] * self.input_channels
        self.rms_level = [-self.LEVEL_RANGE] * self.input_channels
        self.smoothed_level = [-self.LEVEL_RANGE] * self.input_channels
        self.last_peak_time = [0] * self.input_channels
        self.peak_hold_counter = [0] * self.input_channels
        
        # Состояние мониторинга
        self.monitoring = False
        self.output_stream = None
        self.audio_buffer = deque(maxlen=10)  # Буфер для аудиоданных
        self.buffer_lock = threading.Lock()
        
        # Состояние записи
        self.recording = False
        self.audio_file = None
        self.recording_start_time = 0
        self.recorded_data = []
        self.bullet_visible = False  # Состояние мигающего буллета
        
        # Шумоподавление
        self.noise_reduction = False
        self.noise_profile = None
        self.noise_profile_captured = False
        self.noise_capture_frames = 0
        self.NOISE_PROFILE_DURATION = 3.0  # Увеличим время захвата профиля
        self.noise_samples = []  # Буфер для накопления samples шума
        
        self.setup_window()
        self.setup_ui()
        self.setup_audio()
        
        self.update_interval = 30  # мс
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
        y = (screen_height - 440) ##self.window_height) // 2
        self.root.geometry(f"+{x}+{y}")

    def setup_ui(self):
        title_font = tkfont.Font(family='Helvetica', size=12, weight='normal')
        title = "Mic Level" if self.input_channels == 1 else "Stereo Mic Level"
        self.title_label = tk.Label(
            self.root, 
            width=self.window_width,
            text=title, 
            bg='black', 
            fg='lightgray', 
            font=title_font
        )
        self.title_label.pack(pady=5)

        self.title_label.bind("<ButtonPress-1>", self.start_move)
        self.title_label.bind("<ButtonRelease-1>", self.stop_move)
        self.title_label.bind("<B1-Motion>", self.do_move)

        self.meter_frame = tk.Frame(self.root, bg='black')
        self.meter_frame.pack()
        
        # Создаем индикаторы в зависимости от количества каналов
        self.canvases = []
        if self.input_channels == 1:
            channel_label = "Mono"
            canvas = self.create_meter(self.meter_frame, channel_label)
            self.canvases.append(canvas)
        else:
            for i in range(self.input_channels):
                channel_label = "L" if i == 0 else "R"
                canvas = self.create_meter(self.meter_frame, channel_label)
                self.canvases.append(canvas)

        # Добавляем кнопки
        self.buttons_frame = tk.Frame(self.root, bg='black')
        self.buttons_frame.pack(pady=5)

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

        # Кнопка шумоподавления
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

    def setup_noise_reduction_button(self):
        """Настраивает кнопку шумоподавления"""
        canvas = self.noise_reduction_button_canvas
        button_width = canvas.winfo_reqwidth() - 10
        button_height = canvas.winfo_reqheight() - 4
        x_center = self.window_width // 2
        x1 = x_center - button_width // 2
        x2 = x_center + button_width // 2

        # Рисуем прямоугольник кнопки
        button_bg = canvas.create_rectangle(
            x1, 0, x2, button_height,
            fill='#000000',
            outline="#333333",
            width=1
        )

        # Индикатор состояния (зеленая точка когда включено)
        indicator_size = 3
        indicator_x = x_center - button_width // 2 + 8
        indicator_y = button_height // 2
        indicator = canvas.create_oval(
            indicator_x - indicator_size, indicator_y - indicator_size,
            indicator_x + indicator_size, indicator_y + indicator_size,
            fill='#333333', outline=''  # Серый когда выключено
        )

        # Текст кнопки
        button_text = canvas.create_text(
            x_center+3, button_height // 2,
            text="NR OFF",
            fill='#555555',
            font=("Helvetica", 9)
        )

        # Сохраняем ссылки на элементы
        canvas.button_bg = button_bg
        canvas.button_text = button_text
        canvas.indicator = indicator
        canvas.command = self.toggle_noise_reduction

        # Привязываем события мыши
        canvas.bind("<Button-1>", self.on_button_click)
        canvas.bind("<Enter>", self.on_noise_button_enter)
        canvas.bind("<Leave>", self.on_noise_button_leave)

    def toggle_noise_reduction(self):
        """Включает/выключает шумоподавление"""
        self.noise_reduction = not self.noise_reduction
        
        if self.noise_reduction:
            # Сбрасываем профиль шума для нового захвата
            self.noise_profile = None
            self.noise_profile_captured = False
            self.noise_capture_frames = 0
            self.noise_samples = []  # Очищаем буфер samples
            
            # Обновляем внешний вид кнопки
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_text, 
                text="listening",
                fill='yellow'
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.indicator,
                fill='yellow'  # Желтый во время захвата
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_bg,
                fill='#333300'  # Темно-желтый фон
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
                fill='#333333'  # Серый когда выключено
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_bg,
                fill='#000000'  # Черный фон
            )
            print("Noise reduction disabled")

    def on_noise_button_enter(self, event):
        """Обработчик наведения на кнопку шумоподавления"""
        canvas = event.widget
        if self.noise_reduction:
            if not self.noise_profile_captured:
                canvas.itemconfig(canvas.button_bg, fill='#444400')  # Более светлый желтый
            else:
                canvas.itemconfig(canvas.button_bg, fill='#004400')  # Более светлый зеленый
        else:
            canvas.itemconfig(canvas.button_bg, fill='#330000')  # Темно-красный
        canvas.itemconfig(canvas.button_text, fill='white')

    def on_noise_button_leave(self, event):
        """Обработчик ухода с кнопки шумоподавления"""
        canvas = event.widget
        if self.noise_reduction:
            if not self.noise_profile_captured:
                canvas.itemconfig(canvas.button_bg, fill='#333300')  # Темно-желтый
                canvas.itemconfig(canvas.button_text, fill='yellow')
            else:
                canvas.itemconfig(canvas.button_bg, fill='#003300')  # Темно-зеленый
                canvas.itemconfig(canvas.button_text, fill='white')
        else:
            canvas.itemconfig(canvas.button_bg, fill='#000000')  # Черный
            canvas.itemconfig(canvas.button_text, fill='#555555')

    def setup_record_button(self):
        """Настраивает кнопку записи с буллетом"""
        canvas = self.record_button_canvas
        button_width = canvas.winfo_reqwidth() - 10
        button_height = canvas.winfo_reqheight() - 4
        x_center = self.window_width // 2
        x1 = x_center - button_width // 2
        x2 = x_center + button_width // 2

        # Рисуем прямоугольник кнопки
        button_bg = canvas.create_rectangle(
            x1, 0, x2, button_height,
            fill='#000000',
            outline="#333333",
            width=1
        )

        # Красный буллет (изначально невидимый)
        bullet_size = 3
        bullet_x = x_center
        bullet_y = button_height // 2
        bullet = canvas.create_oval(
            bullet_x - bullet_size, bullet_y - bullet_size,
            bullet_x + bullet_size, bullet_y + bullet_size,
            fill='red', outline=''
        )
        canvas.itemconfig(bullet, state='hidden')  # Скрываем изначально

        # Текст кнопки
        button_text = canvas.create_text(
            x_center, button_height // 2,
            text="Record",
            fill='#555555',
            font=("Helvetica", 10)
        )

        # Сохраняем ссылки на элементы
        canvas.button_bg = button_bg
        canvas.button_text = button_text
        canvas.bullet = bullet
        canvas.command = self.toggle_record

        # Привязываем события мыши
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

        # Рисуем прямоугольник кнопки
        button_bg = canvas.create_rectangle(
            x1, 0, x2, button_height,
            fill='#000000',
            outline="#333333",
            width=1
        )

        # Текст кнопки
        button_text = canvas.create_text(
            x_center, button_height // 2,
            text=text,
            fill='#555555',
            font=("Helvetica", 10)
        )

        # Сохраняем ссылки на элементы
        canvas.button_bg = button_bg
        canvas.button_text = button_text
        canvas.command = command

        # Привязываем события мыши
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
            color = '#cc0000' if not self.recording else 'red'
        canvas.itemconfig(canvas.button_bg, fill=color)
        canvas.itemconfig(canvas.button_text, fill='white')

    def on_button_leave(self, event):
        canvas = event.widget
        canvas.itemconfig(canvas.button_bg, fill='#000000')
        if canvas == self.record_button_canvas and self.recording:
            canvas.itemconfig(canvas.button_text, text="")
        else:
            canvas.itemconfig(canvas.button_text, fill='#555555')

    def toggle_bullet(self):
        """Переключает видимость красного буллета для создания мигания"""
        if self.recording:
            self.bullet_visible = not self.bullet_visible
            if self.bullet_visible:
                self.record_button_canvas.itemconfig(self.record_button_canvas.bullet, state='normal')
            else:
                self.record_button_canvas.itemconfig(self.record_button_canvas.bullet, state='hidden')
            
            # Запланировать следующее переключение через 500 мс
            self.root.after(500, self.toggle_bullet)

    def capture_noise_profile(self, audio_data):
        """Захватывает профиль шума из первых нескольких секунд аудио"""
        if self.noise_profile_captured:
            return
            
        # Накопление samples для профиля шума
        self.noise_samples.append(audio_data.copy())
        
        # Проверяем, набрали ли достаточно данных
        total_samples = len(self.noise_samples) * audio_data.shape[0]
        required_samples = int(self.NOISE_PROFILE_DURATION * self.sample_rate)
        
        if total_samples >= required_samples:
            # Объединяем все накопленные samples
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
                fill='green'  # Зеленый когда готово
            )
            self.noise_reduction_button_canvas.itemconfig(
                self.noise_reduction_button_canvas.button_bg,
                fill='#003300'  # Темно-зеленый фон
            )
            print("Noise profile captured successfully!")

    def apply_noise_reduction(self, audio_data):
        """Применяет шумоподавление к аудиоданным"""
        if not self.noise_reduction:
            return audio_data
            
        try:
            # Если профиль шума еще не захвачен, продолжаем захват
            if not self.noise_profile_captured:
                self.capture_noise_profile(audio_data)
                return audio_data  # Пока не применяем подавление
            
            # Применяем шумоподавление с захваченным профилем
            # Для многоканального аудио обрабатываем каждый канал отдельно
            if self.input_channels == 1:
                reduced_noise = nr.reduce_noise(
                    y=audio_data.flatten(),
                    sr=self.sample_rate,
                    y_noise=self.noise_profile.flatten(),
                    prop_decrease=0.6,
                    stationary=False ## True для постояного предсказуемого шума
                )
                return reduced_noise.reshape(-1, 1)
            else:
                # Для стерео обрабатываем каждый канал отдельно
                processed_channels = []
                for channel in range(self.input_channels):
                    reduced_channel = nr.reduce_noise(
                        y=audio_data[:, channel],
                        sr=self.sample_rate,
                        y_noise=self.noise_profile[:, channel],
                        prop_decrease=0.8,
                        stationary=True
                    )
                    processed_channels.append(reduced_channel)
                
                return np.column_stack(processed_channels)
            
        except Exception as e:
            print(f"Noise reduction error: {e}")
            return audio_data

    def toggle_record(self):
        """Включает/выключает запись звука"""
        if not self.recording:
            # Начинаем запись
            try:
                timestamp = time.strftime("%H-%M %d%m%Y")
                desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
                filename = os.path.join(desktop_path, f"Record {timestamp}.wav")
                
                # Создаем WAV файл и сразу начинаем писать
                self.audio_file = wave.open(filename, 'wb')
                self.audio_file.setnchannels(self.input_channels)
                self.audio_file.setsampwidth(2)  # 16-bit
                self.audio_file.setframerate(self.sample_rate)
                
                self.recording = True
                self.recording_start_time = time.time()
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, text="")
                
                # Сбрасываем профиль шума при начале записи
                if self.noise_reduction:
                    self.noise_profile = None
                    self.noise_profile_captured = False
                    self.noise_capture_frames = 0
                    self.noise_samples = []
                    # Обновляем кнопку для отображения захвата профиля
                    self.noise_reduction_button_canvas.itemconfig(
                        self.noise_reduction_button_canvas.button_text, 
                        text="listening",
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
                
                # Запускаем мигание буллета
                self.bullet_visible = True
                self.record_button_canvas.itemconfig(self.record_button_canvas.bullet, state='normal')
                self.root.after(500, self.toggle_bullet)
                
                print(f"Recording started: {filename}")

            except Exception as e:
                print(f"Error starting recording: {e}")
                self.recording = False
        else:
            # Останавливаем запись
            try:
                self.recording = False
                # Останавливаем мигание буллета
                self.record_button_canvas.itemconfig(self.record_button_canvas.bullet, state='hidden')
                
                # Закрываем файл
                if self.audio_file:
                    self.audio_file.close()
                    self.audio_file = None
                    print("Recording stopped and file saved")
                
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, text="Record")
                self.record_button_canvas.itemconfig(self.record_button_canvas.button_text, fill='#555555')
            except Exception as e:
                print(f"Error stopping recording: {e}")

    def create_meter(self, parent, channel):
        """Создает VU-метр для указанного канала"""
        channel_frame = tk.Frame(parent, bg='black')
        channel_frame.pack(side=tk.LEFT, padx=7)
                
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
            width=40, 
            height=225, 
            bg='black', 
            highlightthickness=0
        )
        canvas.pack(pady=0)

        canvas.channel_label = channel_label

        db_scale = [-1, -6, -12, -18, -24, -30, -35, -40, -45, -50, -55, -60]
        for db in db_scale:
            y_pos = 220 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            color = "red" if db >= -6 else "orange" if db >= -12 else "green"
            canvas.create_line(33, y_pos, 40, y_pos, fill=color, width=1.5)
            canvas.create_text(
                30, 
                y_pos, 
                text=f"{db}", 
                fill="white", 
                font=("Arial", 8), 
                anchor="e"
            )
        
        canvas.level_bar = canvas.create_rectangle(
            0, 220, 10, 220, 
            fill='green', 
            outline='white', 
            width=1
        )
        
        canvas.peak_bar = canvas.create_line(
            0, 220, 40, 220, 
            fill='red', 
            width=1
        )
        
        return canvas

    def setup_audio(self):
        try:
            # Получаем частоту дискретизации устройства по умолчанию
            device_info = sd.query_devices(sd.default.device[0])
            self.sample_rate = device_info['default_samplerate']
            
            print(f"Using device sample rate: {self.sample_rate} Hz")
            
            self.audio_stream = sd.InputStream(
                samplerate=self.sample_rate,  # Используем "родную" частоту устройства
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

        # Применяем шумоподавление если включено
        processed_data = indata.copy()
        if self.noise_reduction:
            processed_data = self.apply_noise_reduction(indata)

        # Записываем обработанные данные в файл
        if self.recording and self.audio_file:
            try:
                # Используем обработанные данные для записи
                audio_data_int16 = (processed_data * 32767).astype(np.int16)
                self.audio_file.writeframes(audio_data_int16.tobytes())
            except Exception as e:
                print(f"Error writing to audio file: {e}")
        
        # Используем обработанные данные для отображения уровней
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
        # Проверяем превышение уровня и обновляем цвет фона
        level_exceeded_title = any(level > -3 for level in self.peak_level)
        new_color = 'red' if level_exceeded_title else 'black'
        if new_color != self.title_label.cget('bg'):
            self.title_label.configure(bg=new_color)

        for channel in range(self.input_channels):
            canvas = self.canvases[channel]

            # Проверяем превышение уровня для текущего канала и обновляем цвет channel_label
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
            
            canvas.coords(canvas.level_bar, 0, rms_pos, 10, 220)
            canvas.coords(canvas.peak_bar, 0, peak_pos, 40, peak_pos)
            
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
            # Останавливаем запись если активна
            if self.recording:
                self.recording = False
                if self.audio_file:
                    self.audio_file.close()
                    self.audio_file = None
            
            # Останавливаем аудиопотоки
            if hasattr(self, 'audio_stream') and self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
            if hasattr(self, 'output_stream') and self.output_stream:
                self.output_stream.stop()
                self.output_stream.close()
        except Exception as e:
            print(f"Error closing audio streams: {e}")
        
        try:
            # Останавливаем все обновления интерфейса
            self.root.after_cancel(self.update_meter)
        except:
            pass
        
        try:
            # Закрываем окно
            self.root.destroy()
        except:
            pass
        
        try:
            # Принудительно завершаем программу
            sys.exit(0)
        except:
            os._exit(0)  # Аварийный выход если sys.exit не сработал


if __name__ == "__main__":
    try:
        app = AudioLevelMeter()
    except Exception as e:
        print(f"Application error: {e}")
