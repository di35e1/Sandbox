import sounddevice as sd
import numpy as np
import tkinter as tk
from tkinter import font as tkfont
from scipy import signal

class SpectrumAnalyzer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Spectrum Analyzer")

        # Window parameters
        self.window_width = 515
        self.window_height = 280

        # Analysis parameters
        self.SAMPLE_RATE = 44100
        self.BLOCK_SIZE = 2048
        self.NUM_BANDS = 31
        self.LEVEL_RANGE = 60
        self.DECAY_RATE = 25
        self.PEAK_HOLD_TIME = 1.5
        self.MIN_FREQ = 20
        self.MAX_FREQ = 16000
        self.input_channels = 1

        # Available frequency settings
        self.available_min_freqs = [20, 50, 100, 150, 200]
        self.available_max_freqs = [10000, 16000, 20000]
        self.current_min_freq = self.MIN_FREQ
        self.current_max_freq = self.MAX_FREQ

        # RMS meter parameters
        self.rms_level = -self.LEVEL_RANGE
        self.smoothed_rms = -self.LEVEL_RANGE
        self.peak_rms = -self.LEVEL_RANGE
        self.peak_rms_hold_counter = 0

        # UI elements storage
        self.freq_labels = []
        self.db_labels = []
        self.db_lines = []
        self.rms_label = None
        self.rms_meter = None
        self.rms_peak_indicator = None

        # Initialize frequency bands
        self.band_centers = np.logspace(
            np.log10(self.MIN_FREQ),
            np.log10(self.MAX_FREQ),
            self.NUM_BANDS
        )

        # Level states
        self.band_levels = [-self.LEVEL_RANGE] * self.NUM_BANDS
        self.smoothed_levels = [-self.LEVEL_RANGE] * self.NUM_BANDS
        self.peak_levels = np.zeros(self.NUM_BANDS)
        self.peak_hold_counters = np.zeros(self.NUM_BANDS)

        self.filters = self.create_filters()
        self.setup_window()
        self.setup_ui()
        self.setup_audio()

        self.update_interval = 30
        self.root.after(self.update_interval, self.update_meter)
        self.root.mainloop()

    def create_filters(self):
        filters = []
        for i, center_freq in enumerate(self.band_centers):
            low = center_freq / (2**(1/6))
            high = center_freq * (2**(1/6))
            
            # if i == 0 and self.MAX_FREQ == 20:
            #     low = self.MIN_FREQ
            if i == self.NUM_BANDS - 1 and self.MAX_FREQ == 20000:
                high = self.MAX_FREQ

            try:
                if center_freq < 200:
                    b, a = signal.butter(2, [low, high], btype='bandpass', fs=self.SAMPLE_RATE)
                else:
                    b, a = signal.butter(4, [low, high], btype='bandpass', fs=self.SAMPLE_RATE)
                # b, a = signal.butter(4, [low, high], btype='bandpass', fs=self.SAMPLE_RATE)
                filters.append((b, a))
            except:
                filters.append(([1], [1]))
                print(f"Warning: Could not create filter for {center_freq:.0f} Hz")
        return filters

    def setup_window(self):
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.7)
        self.root.configure(bg='black')
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - self.window_width - 20
        y = (screen_height - self.window_height) - 20
        self.root.geometry(f"+{x}+{y}")

    def setup_ui(self):
        # Channel mode indicator
        self.channel_label = tk.Label(
            self.root,
            text="Mono",
            font=("Arial", 10),
            bg='black',
            fg='yellow'
        )
        self.channel_label.place(x=40, y=15)

        # Create menu bar with frequency settings
        self.menu_bar = tk.Menu(self.root)

        # Min Frequency menu
        self.min_freq_menu = tk.Menu(self.menu_bar, tearoff=0)
        for freq in self.available_min_freqs:
            self.min_freq_menu.add_command(
                label=f"{freq} Hz {'✓' if freq == self.current_min_freq else ''}",
                command=lambda f=freq: self.set_frequency('min', f)
            )
        self.menu_bar.add_cascade(label="Min Frequency", menu=self.min_freq_menu)

        # Max Frequency menu
        self.max_freq_menu = tk.Menu(self.menu_bar, tearoff=0)
        for freq in self.available_max_freqs:
            self.max_freq_menu.add_command(
                label=f"{freq} Hz {'✓' if freq == self.current_max_freq else ''}",
                command=lambda f=freq: self.set_frequency('max', f)
            )
        self.menu_bar.add_cascade(label="Max Frequency", menu=self.max_freq_menu)

        # Gear icon button
        self.gear_canvas = tk.Canvas(
            self.root,
            width=30,
            height=30,
            bg='black',
            highlightthickness=0,
            bd=0
        )
        self.gear_canvas.place(x=10, y=10)
        
        self.gear_icon = self.gear_canvas.create_text(
            15, 12,
            text="⚙",
            font=("Arial", 20),
            fill="gray"
        )
        
        self.gear_canvas.bind("<Button-1>", self.show_menu_button)
        self.gear_canvas.bind("<Enter>", lambda e: self.gear_canvas.itemconfig(self.gear_icon, fill="white"))
        self.gear_canvas.bind("<Leave>", lambda e: self.gear_canvas.itemconfig(self.gear_icon, fill="gray"))

        # Title
        title_font = tkfont.Font(family='Helvetica', size=12, weight='bold')
        self.title_label = tk.Label(
            self.root,
            text="Input Spectrum Analyzer",
            bg='black',
            fg='gray',
            font=title_font
        )
        self.title_label.pack(pady=15, padx=90, anchor="e")
        
        # Main canvas
        self.canvas = tk.Canvas(
            self.root, 
            width=self.window_width-20, 
            height=230, 
            bg='black', 
            highlightthickness=0
        )
        self.canvas.pack()

        # Window movement handlers
        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<ButtonRelease-1>", self.stop_move)
        self.canvas.bind("<B1-Motion>", self.do_move)        
        
        # Create spectrum bars
        self.band_bars = []
        self.peak_indicators = []
        band_width = 10
        band_gap = 3
        bands_start_x = 10
        
        self.freq_labels = []
        
        for i in range(self.NUM_BANDS):
            x1 = bands_start_x + i * (band_width + band_gap)
            x2 = x1 + band_width
            
            bar = self.canvas.create_rectangle(
                x1, 200, x2, 200, 
                fill='green',
                outline='white',
                width=1
            )
            self.band_bars.append(bar)
            
            peak = self.canvas.create_line(
                x1, 200, x2, 200,
                fill='red',
                width=1
            )
            self.peak_indicators.append(peak)
            
            if i % 2 == 0:
                freq = int(self.band_centers[i])
                text = f"{freq/1000:.1f}K" if freq >= 1000 else f"{freq}"
                label = self.canvas.create_text(
                    (x1+x2)/2, 
                    215, 
                    text=text, 
                    fill="white", 
                    font=("Arial", 8), 
                    anchor="n"
                )
                self.freq_labels.append(label)

        # dB scale
        scale_start_x = 450
        db_scale = [-1, -6, -12, -18, -24, -30, -35, -40, -45, -50, -55, -60]
        
        self.db_labels = []
        self.db_lines = []
        
        for db in db_scale:
            y_pos = 200 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            color = "red" if db >= -6 else "orange" if db >= -12 else "green"
            
            line = self.canvas.create_line(
                scale_start_x, y_pos, 
                scale_start_x + 10, y_pos,
                fill=color, 
                width=2
            )
            self.db_lines.append(line)
            
            label = self.canvas.create_text(
                scale_start_x - 5, 
                y_pos, 
                text=f"{db}", 
                fill="white", 
                font=("Arial", 10), 
                anchor="e"
            )
            self.db_labels.append(label)

        # RMS meter
        rms_meter_x = scale_start_x + 15
        self.rms_meter = self.canvas.create_rectangle(
            rms_meter_x, 200, rms_meter_x + 15, 200,
            fill='green',
            outline='white',
            width=1
        )

        self.rms_peak_indicator = self.canvas.create_line(
            rms_meter_x - 20, 200, rms_meter_x + 15, 200,
            fill='red',
            width=1
        )

        self.rms_label = self.canvas.create_text(
            rms_meter_x + 14,
            215,
            text="RMS",
            fill="white",
            font=("Arial", 8),
            anchor="n"
        )

        self.title_label.bind("<ButtonPress-1>", self.start_move)
        self.title_label.bind("<ButtonRelease-1>", self.stop_move)
        self.title_label.bind("<B1-Motion>", self.do_move)

    def show_menu_button(self, event=None):
        try:
            x = self.root.winfo_rootx() + 10
            y = self.root.winfo_rooty() + 40
            self.menu_bar.tk_popup(x, y)
        finally:
            self.menu_bar.grab_release()

    def set_frequency(self, freq_type, freq):
        if freq_type == 'min':
            self.MIN_FREQ = freq
            self.current_min_freq = freq
        else:
            self.MAX_FREQ = freq
            self.current_max_freq = freq
        
        self.update_frequency_settings()

    def update_frequency_settings(self):
        self.band_centers = np.logspace(
            np.log10(self.MIN_FREQ),
            np.log10(self.MAX_FREQ),
            self.NUM_BANDS
        )
        self.filters = self.create_filters()
        
        self.min_freq_menu.delete(0, tk.END)
        for f in self.available_min_freqs:
            self.min_freq_menu.add_command(
                label=f"{f} Hz {'✓' if f == self.current_min_freq else ''}",
                command=lambda freq=f: self.set_frequency('min', freq))
        
        self.max_freq_menu.delete(0, tk.END)
        for f in self.available_max_freqs:
            self.max_freq_menu.add_command(
                label=f"{f} Hz {'✓' if f == self.current_max_freq else ''}",
                command=lambda freq=f: self.set_frequency('max', freq))
        
        band_width = 10
        band_gap = 3
        bands_start_x = 10
        
        label_index = 0
        for i in range(self.NUM_BANDS):
            if i % 2 == 0:
                x1 = bands_start_x + i * (band_width + band_gap)
                x2 = x1 + band_width
                freq = int(self.band_centers[i])
                text = f"{freq/1000:.1f}K" if freq >= 1000 else f"{freq}"
                
                if label_index < len(self.freq_labels):
                    self.canvas.itemconfig(self.freq_labels[label_index], text=text)
                else:
                    label = self.canvas.create_text(
                        (x1+x2)/2, 
                        215, 
                        text=text, 
                        fill="white", 
                        font=("Arial", 8), 
                        anchor="n"
                    )
                    self.freq_labels.append(label)
                
                label_index += 1

        while len(self.freq_labels) > label_index:
            self.canvas.delete(self.freq_labels.pop())

    def setup_audio(self):
        try:
            device_info = sd.query_devices(kind='input')
            device_name = device_info['name']
            self.input_channels = device_info['max_input_channels']
            
            mode_text = "Stereo - " if self.input_channels >= 2 else "Mono - "
            self.channel_label.config(text=mode_text + device_name)

            self.audio_stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=min(self.input_channels, 2),
                blocksize=self.BLOCK_SIZE,
                latency='high',
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
        
        indata = np.clip(indata, -1, 1)
        
        # Расчет общего RMS
        if indata.shape[1] >= 2:
            mono_signal = np.mean(indata, axis=1)
        else:
            mono_signal = indata[:, 0]
        
        # Общий уровень без фильтрации
        rms = np.sqrt(np.mean(mono_signal**2))
        self.rms_level = 20 * np.log10(max(rms, 1e-6))
        
        peak = np.max(np.abs(mono_signal))
        peak_db = 20 * np.log10(max(peak, 1e-6))
        
        if peak_db > self.peak_rms:
            self.peak_rms = peak_db
            self.peak_rms_hold_counter = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)
        
        # Обработка полос частот (для спектра)
        for i in range(self.NUM_BANDS):
            b, a = self.filters[i]
            try:
                filtered = signal.lfilter(b, a, mono_signal)
                rms = np.sqrt(np.mean(filtered**2))
                db_level = 20 * np.log10(max(rms, 1e-6))
                self.band_levels[i] = max(min(db_level, 0), -self.LEVEL_RANGE)
                
                if db_level > self.peak_levels[i]:
                    self.peak_levels[i] = db_level
                    self.peak_hold_counters[i] = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)
            except:
                self.band_levels[i] = -self.LEVEL_RANGE

    def update_meter(self):
        # Обновление общего уровня
        if self.rms_level > self.smoothed_rms:
            self.smoothed_rms = self.rms_level
        else:
            decay_amount = self.DECAY_RATE * (self.update_interval/1000)
            self.smoothed_rms = max(
                self.smoothed_rms - decay_amount, 
                -self.LEVEL_RANGE
            )
        
        if self.peak_rms_hold_counter > 0:
            self.peak_rms_hold_counter -= 1
        else:
            decay_amount = self.DECAY_RATE * 2 * (self.update_interval/1000)
            self.peak_rms = max(
                self.peak_rms - decay_amount, 
                -self.LEVEL_RANGE
            )
        
        def db_to_y(db):
            return 200 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
        
        # Обновление RMS
        rms_y = db_to_y(self.smoothed_rms)
        peak_y = db_to_y(self.peak_rms)
        
        rms_meter_x = 450 + 20
        self.canvas.coords(
            self.rms_meter,
            rms_meter_x, rms_y,
            rms_meter_x + 15, 200
        )
        
        color = 'red' if self.smoothed_rms > -6 else \
                'orange' if self.smoothed_rms > -15 else 'green'
        self.canvas.itemconfig(self.rms_meter, fill=color)
        
        self.canvas.coords(
            self.rms_peak_indicator,
            rms_meter_x -20, peak_y,
            rms_meter_x + 15, peak_y
        )

        # Обновление полос спектра
        for i in range(self.NUM_BANDS):
            if self.band_levels[i] > self.smoothed_levels[i]:
                self.smoothed_levels[i] = self.band_levels[i]
            else:
                decay_amount = self.DECAY_RATE * (self.update_interval/1000)
                self.smoothed_levels[i] = max(
                    self.smoothed_levels[i] - decay_amount, 
                    -self.LEVEL_RANGE
                )
            
            if self.peak_hold_counters[i] > 0:
                self.peak_hold_counters[i] -= 1
            else:
                decay_amount = self.DECAY_RATE * 2 * (self.update_interval/1000)
                self.peak_levels[i] = max(
                    self.peak_levels[i] - decay_amount, 
                    -self.LEVEL_RANGE
                )
            
            rms_y = db_to_y(self.smoothed_levels[i])
            peak_y = db_to_y(self.peak_levels[i])
            
            coords = self.canvas.coords(self.band_bars[i])
            self.canvas.coords(self.band_bars[i], coords[0], rms_y, coords[2], 200)
            
            color = 'red' if self.smoothed_levels[i] > -6 else \
                    'orange' if self.smoothed_levels[i] > -15 else 'green'
            self.canvas.itemconfig(self.band_bars[i], fill=color)
            
            peak_coords = self.canvas.coords(self.peak_indicators[i])
            self.canvas.coords(
                self.peak_indicators[i],
                peak_coords[0], peak_y,
                peak_coords[2], peak_y
            )
        
        self.root.after(self.update_interval, self.update_meter)

    def start_move(self, event):
        self.drag_data = {"x": event.x, "y": event.y}

    def stop_move(self, event):
        self.drag_data = None

    def do_move(self, event):
        if hasattr(self, 'drag_data') and self.drag_data:
            x = self.root.winfo_x() + (event.x - self.drag_data["x"])
            y = self.root.winfo_y() + (event.y - self.drag_data["y"])
            self.root.geometry(f"+{x}+{y}")

if __name__ == "__main__":
    try:
        app = SpectrumAnalyzer()
    except Exception as e:
        print(f"Application error: {e}")
