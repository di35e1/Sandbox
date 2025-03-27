import sounddevice as sd
import numpy as np
import tkinter as tk
from tkinter import font as tkfont

class AudioLevelMeter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Audio Level Meter")
        
        # Параметры окна
        self.window_width = 100
        self.window_height = 300
        
        # Калибровка уровней
        self.LEVEL_RANGE = 60  # Диапазон 60 dB
        self.PEAK_HOLD_TIME = .3  # Удержание пика 1.5 сек
        self.DECAY_RATE = 25  # Скорость затухания 25 dB/сек
        
        # Состояние уровней
        self.peak_level = -self.LEVEL_RANGE
        self.rms_level = -self.LEVEL_RANGE
        self.smoothed_level = -self.LEVEL_RANGE
        self.last_peak_time = 0
        self.peak_hold_counter = 0
        
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
        x = screen_width - 120
        y = (screen_height - self.window_height) // 2
        self.root.geometry(f"+{x}+{y}")

    def setup_ui(self):
        title_font = tkfont.Font(family='Helvetica', size=12, weight='bold')
        self.title_label = tk.Label(
            self.root, 
            text="Mic Level", 
            bg='black', 
            fg='white', 
            font=title_font
        )
        self.title_label.pack(pady=10)
        
        self.canvas = tk.Canvas(
            self.root, 
            width=60, 
            height=220, 
            bg='black', 
            highlightthickness=0
        )
        self.canvas.pack()
        
        db_scale = [0, -6, -12, -18, -24, -30, -40, -50, -60]
        for db in db_scale:
            y_pos = 220 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            color = "red" if db >= -6 else "orange" if db >= -12 else "green"
            self.canvas.create_line(45, y_pos, 55, y_pos, fill=color, width=2)
            self.canvas.create_text(
                40, 
                y_pos, 
                text=f"{db}", 
                fill="white", 
                font=("Arial", 8), 
                anchor="e"
            )
        
        self.level_bar = self.canvas.create_rectangle(
            10, 220, 40, 220, 
            fill='green', 
            outline='white', 
            width=1
        )
        
        self.peak_bar = self.canvas.create_line(
            10, 220, 40, 220, 
            fill='red', 
            width=2
        )
        
        self.title_label.bind("<ButtonPress-1>", self.start_move)
        self.title_label.bind("<ButtonRelease-1>", self.stop_move)
        self.title_label.bind("<B1-Motion>", self.do_move)

    def setup_audio(self):
        self.sample_rate = 44100
        try:
            self.audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
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
        
        rms = np.sqrt(np.mean(indata**2))
        self.rms_level = 20 * np.log10(max(rms, 1e-6))
        
        peak = np.max(np.abs(indata))
        peak_db = 20 * np.log10(max(peak, 1e-6))
        
        if peak_db > self.peak_level:
            self.peak_level = peak_db
            self.last_peak_time = time.currentTime  # Фиксируем время последнего пика
            self.peak_hold_counter = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)

    def update_meter(self):
        # Обновление RMS уровня (зеленый индикатор)
        if self.rms_level > self.smoothed_level:
            self.smoothed_level = self.rms_level
        else:
            decay_amount = self.DECAY_RATE * (self.update_interval/1000)
            self.smoothed_level = max(
                self.smoothed_level - decay_amount, 
                -self.LEVEL_RANGE
            )
        
        # Обновление пикового уровня (красный индикатор)
        if self.peak_hold_counter > 0:
            self.peak_hold_counter -= 1
        else:
            decay_amount = self.DECAY_RATE * 2 * (self.update_interval/1000)
            self.peak_level = max(
                self.peak_level - decay_amount, 
                -self.LEVEL_RANGE
            )
        
        # Преобразование dB в координаты
        def db_to_pos(db):
            return 220 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
        
        rms_pos = db_to_pos(self.smoothed_level)
        peak_pos = db_to_pos(self.peak_level)
        
        self.canvas.coords(self.level_bar, 10, rms_pos, 40, 220)
        self.canvas.coords(self.peak_bar, 10, peak_pos, 40, peak_pos)
        
        if self.smoothed_level > -6:
            color = 'red'
        elif self.smoothed_level > -12:
            color = 'orange'
        else:
            color = 'green'
        self.canvas.itemconfig(self.level_bar, fill=color)
        
        self.root.after(self.update_interval, self.update_meter)

    def start_move(self, event):
        self.drag_data = {"x": event.x, "y": event.y}

    def stop_move(self, event):
        self.drag_data = None

    def do_move(self, event):
        x = self.root.winfo_x() + (event.x - self.drag_data["x"])
        y = self.root.winfo_y() + (event.y - self.drag_data["y"])
        self.root.geometry(f"+{x}+{y}")

if __name__ == "__main__":
    try:
        app = AudioLevelMeter()
    except Exception as e:
        print(f"Application error: {e}")