import sounddevice as sd
import subprocess
import numpy as np
import tkinter as tk
from tkinter import font as tkfont
import sys
import os

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
        self.window_height = 300  # Увеличили высоту для кнопки
        
        # Калибровка уровней
        self.LEVEL_RANGE = 60  # Диапазон 60 dB
        self.PEAK_HOLD_TIME = .5 # Удержание пика (сек)
        self.DECAY_RATE = 25  # Скорость затухания (dB/сек)
        
        # Состояние уровней
        self.peak_level = [-self.LEVEL_RANGE] * self.input_channels
        self.rms_level = [-self.LEVEL_RANGE] * self.input_channels
        self.smoothed_level = [-self.LEVEL_RANGE] * self.input_channels
        self.last_peak_time = [0] * self.input_channels
        self.peak_hold_counter = [0] * self.input_channels
        
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
        y = (screen_height - self.window_height) // 2
        self.root.geometry(f"+{x}+{y}")

    def setup_ui(self):
        title_font = tkfont.Font(family='Helvetica', size=12, weight='bold')
        title = "Mic Level" if self.input_channels == 1 else "Stereo Mic Level"
        self.title_label = tk.Label(
            self.root, 
            text=title, 
            bg='black', 
            fg='lightgray', 
            font=title_font
        )
        self.title_label.pack(pady=5)
        
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
        
        # Добавляем кнопку перезапуска
        # Создаем canvas для кнопки
        self.button_canvas = tk.Canvas(
            self.root,
            width=self.window_width,
            height=22,
            bg='black',
            highlightthickness=0
        )
        self.button_canvas.pack(pady=6)

        # Рисуем прямоугольник кнопки
        button_width = self.window_width - 10
        button_height = 16
        x_center = self.window_width // 2
        x1 = x_center - button_width // 2
        x2 = x_center + button_width // 2

        self.button_bg = self.button_canvas.create_rectangle(
            x1, 0, x2, button_height,
            fill='#000000',
            outline="#333333",
            width=1
        )

        # Текст кнопки
        self.button_text = self.button_canvas.create_text(
            x_center, button_height // 2,
            text="Close",
            fill='#555555',
            font=("Helvetica", 10)
        )

        # Привязываем события мыши
        self.button_canvas.bind("<Button-1>", self.on_button_click)
        self.button_canvas.bind("<Enter>", self.on_button_enter)
        self.button_canvas.bind("<Leave>", self.on_button_leave)

    # Методы для обработки событий кнопки
    def on_button_click(self, event):
        self.button_canvas.itemconfig(self.button_bg, fill="#555555")
        self.close_program()

    def on_button_enter(self, event):
        self.button_canvas.itemconfig(self.button_bg, fill='red')
        self.button_canvas.itemconfig(self.button_text, fill='white')

    def on_button_leave(self, event):
        self.button_canvas.itemconfig(self.button_bg, fill='#000000')
        self.button_canvas.itemconfig(self.button_text, fill='#555555')        

    def create_meter(self, parent, channel):
        """Создает VU-метр для указанного канала"""
        channel_frame = tk.Frame(parent, bg='black')
        channel_frame.pack(side=tk.LEFT, padx=7)
        
        tk.Label(
            channel_frame, 
            text=channel, 
            bg='black', 
            fg='yellow', 
            font=("Arial", 8)
        ).pack(pady=0)
        
        canvas = tk.Canvas(
            channel_frame, 
            width=40, 
            height=225, 
            bg='black', 
            highlightthickness=0
        )
        canvas.pack(pady=0)

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
        self.sample_rate = 44100
        try:
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
        
        for channel in range(self.input_channels):
            channel_data = indata[:, channel]
            rms = np.sqrt(np.mean(channel_data**2))
            self.rms_level[channel] = 20 * np.log10(max(rms, 1e-6))
            
            peak = np.max(np.abs(channel_data))
            peak_db = 20 * np.log10(max(peak, 1e-6))
            
            if peak_db > self.peak_level[channel]:
                self.peak_level[channel] = peak_db
                self.last_peak_time[channel] = time.currentTime
                self.peak_hold_counter[channel] = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)

    def update_meter(self):
        for channel in range(self.input_channels):
            canvas = self.canvases[channel]
            
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

    def restart_program(self):
        """Перезапускает программу"""
        try:
            if hasattr(self, 'audio_stream'):
                self.audio_stream.stop()
                self.audio_stream.close()
        except:
            pass

        self.root.destroy()
        subprocess.Popen([sys.executable, __file__])
        sys.exit(0)

    def close_program(self):
        """Корректно закрывает программу"""
        try:
            # Останавливаем аудиопоток
            if hasattr(self, 'audio_stream') and self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
        except Exception as e:
            print(f"Error closing audio stream: {e}")
        
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
