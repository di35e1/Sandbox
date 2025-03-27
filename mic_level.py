import sounddevice as sd
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw

class MicrophoneLevelApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mic Level")
        
        # Параметры окна
        self.window_width = 80
        self.window_height = 250  # Оригинальная высота
        
        # Параметры анимации
        self.smooth_level = 0
        self.decay_rate = 0.9  # Скорость затухания (меньше = медленнее)
        self.peak_hold = 0
        self.peak_hold_time = 10  # Количество циклов удержания пика
        
        self.create_mic_icon()
        self.setup_window()
        self.setup_ui()
        self.setup_audio()
        
        self.update_interval = 30  # Частота обновления (мс)
        self.root.after(self.update_interval, self.update_level)
        self.root.mainloop()

    def create_mic_icon(self):
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((16, 32, 48, 64), fill=(50, 150, 250, 200))
        draw.rectangle((28, 20, 36, 50), fill=(100, 100, 100, 200))
        draw.polygon([(16, 20), (48, 20), (40, 0), (24, 0)], fill=(150, 150, 150, 200))
        self.mic_icon = ImageTk.PhotoImage(img.resize((32, 32), Image.LANCZOS))

    def setup_window(self):
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='white')
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - 100
        y = (screen_height - self.window_height) // 2
        self.root.geometry(f"+{x}+{y}")

    def setup_ui(self):
        # Иконка микрофона
        self.icon_label = tk.Label(self.root, image=self.mic_icon, bg='white')
        self.icon_label.pack(pady=10)
        
        # Холст для индикатора
        self.canvas = tk.Canvas(self.root, width=40, height=180, bg='white', highlightthickness=0)
        self.canvas.pack()
        
        # Шкала
        for i in range(0, 101, 10):
            y_pos = 180 - i * 1.8
            self.canvas.create_text(20, y_pos, text=f"{i}%", font=("Arial", 7))
            self.canvas.create_line(30, y_pos, 38, y_pos, fill="gray")
        
        # Индикатор уровня
        self.level_indicator = self.canvas.create_rectangle(5, 180, 35, 180, fill='#4CAF50', outline='')
        
        # Пиковый индикатор
        self.peak_indicator = self.canvas.create_line(5, 180, 35, 180, fill='red', width=2)
        
        # Перемещение окна
        self.icon_label.bind("<ButtonPress-1>", self.start_move)
        self.icon_label.bind("<ButtonRelease-1>", self.stop_move)
        self.icon_label.bind("<B1-Motion>", self.do_move)

    def setup_audio(self):
        self.sample_rate = 44100
        self.current_level = 0
        try:
            self.audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
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
        self.current_level = np.sqrt(np.mean(indata**2)) * 100

    def update_level(self):
        raw_level = min(self.current_level, 100)
        
        # Быстрое реагирование на повышение уровня
        if raw_level > self.smooth_level:
            self.smooth_level = raw_level
            self.peak_hold = self.peak_hold_time  # Сброс счетчика удержания пика
        else:
            # Плавное затухание с задержкой пика
            if self.peak_hold > 0:
                self.peak_hold -= 1
            else:
                self.smooth_level = max(self.smooth_level - self.decay_rate, 0)
        
        # Обновляем основной индикатор
        height = self.smooth_level * 1.8
        self.canvas.coords(self.level_indicator, 5, 180-height, 35, 180)
        
        # Обновляем пиковый индикатор
        peak_height = raw_level * 1.8
        self.canvas.coords(self.peak_indicator, 5, 180-peak_height, 35, 180-peak_height)
        
        # Цветовая индикация
        red = int(min(255, raw_level*2.55))
        green = int(max(0, 255 - raw_level*1.5))
        color = f'#{red:02x}{green:02x}00'
        self.canvas.itemconfig(self.level_indicator, fill=color)
        
        # Прозрачность окна
        self.root.attributes('-alpha', 0.7 + (raw_level/100)*0.3)
        
        self.root.after(self.update_interval, self.update_level)

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
        app = MicrophoneLevelApp()
    except Exception as e:
        print(f"Application error: {e}")
