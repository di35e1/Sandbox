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
        self.window_width = 550  # Increased width to accommodate RMS meter
        self.window_height = 280
        
        # Analysis parameters
        self.SAMPLE_RATE = 44100
        self.BLOCK_SIZE = 2048
        self.NUM_BANDS = 32
        self.LEVEL_RANGE = 60
        self.DECAY_RATE = 25
        self.PEAK_HOLD_TIME = 1
        self.MIN_FREQ = 200
        self.MAX_FREQ = 16000
        self.input_channels = 1  # Default to mono

        # RMS meter parameters
        self.rms_level = -self.LEVEL_RANGE
        self.smoothed_rms = -self.LEVEL_RANGE
        self.peak_rms = -self.LEVEL_RANGE
        self.peak_rms_hold_counter = 0

        # Center frequencies
        self.band_centers = np.logspace(
            np.log10(self.MIN_FREQ),
            np.log10(self.MAX_FREQ),
            self.NUM_BANDS
        )
        
        # Level states
        self.band_levels = np.zeros(self.NUM_BANDS)
        self.smoothed_levels = np.zeros(self.NUM_BANDS)
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
            # Узкие полосы - 1/3 октавы
            low = center_freq / (2**(1/6))
            high = center_freq * (2**(1/6))

            # Широкие полосы - 1 октава
            # low = center_freq / (2**0.5)
            # high = center_freq * (2**0.5)
            
            if i == 0:
                low = self.MIN_FREQ
            if i == self.NUM_BANDS - 1:
                high = self.MAX_FREQ
                
            try:
                b, a = signal.butter(4, [low, high], btype='bandpass', fs=self.SAMPLE_RATE)
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

        # Create menu
        self.menu_bar = tk.Menu(self.root)
        self.settings_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.settings_menu.add_command(label="20 Hz", command=lambda: self.set_min_freq(20))
        self.settings_menu.add_command(label="50 Hz", command=lambda: self.set_min_freq(50))
        self.settings_menu.add_command(label="100 Hz", command=lambda: self.set_min_freq(100))
        self.settings_menu.add_command(label="150 Hz", command=lambda: self.set_min_freq(150))
        self.settings_menu.add_command(label="200 Hz", command=lambda: self.set_min_freq(200))
        self.menu_bar.add_cascade(label="Min Frequency", menu=self.settings_menu)

        # Custom gear button using Canvas
        self.gear_canvas = tk.Canvas(
            self.root,
            width=30,
            height=30,
            bg='black',
            highlightthickness=0,
            bd=0
        )
        self.gear_canvas.place(x=10, y=10)
        
        # Draw gear icon
        self.gear_icon = self.gear_canvas.create_text(
            15, 12,
            text="⚙",
            font=("Arial", 20),
            fill="gray"
        )
        
        # Event handlers
        self.gear_canvas.bind("<Button-1>", self.show_menu_button)
        self.gear_canvas.bind("<Enter>", lambda e: self.gear_canvas.itemconfig(self.gear_icon, fill="white"))
        self.gear_canvas.bind("<Leave>", lambda e: self.gear_canvas.itemconfig(self.gear_icon, fill="gray"))

        title_font = tkfont.Font(family='Helvetica', size=12, weight='bold')
        self.title_label = tk.Label(
            self.root, 
            text="Input Spectrum Analyzer", 
            bg='black', 
            fg='gray', 
            font=title_font
        )
        self.title_label.pack(pady=10, padx=20, anchor="e")
        
        self.canvas = tk.Canvas(
            self.root, 
            width=self.window_width-20, 
            height=230, 
            bg='black', 
            highlightthickness=0
        )
        self.canvas.pack()

        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<ButtonRelease-1>", self.stop_move)
        self.canvas.bind("<B1-Motion>", self.do_move)        
        
        # Create spectrum bars
        self.band_bars = []
        self.peak_indicators = []
        band_width = 10
        band_gap = 3
        bands_start_x = 10
        
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
                self.canvas.create_text(
                    (x1+x2)/2, 
                    215, 
                    text=text, 
                    fill="white", 
                    font=("Arial", 8), 
                    anchor="n"
                )

        # Level scale
        scale_start_x = 450
        db_scale = [-1, -6, -12, -18, -24, -30, -35, -40, -45, -50, -55, -60]
        
        for db in db_scale:
            y_pos = 200 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            color = "red" if db >= -6 else "orange" if db >= -12 else "green"
            
            self.canvas.create_line(
                scale_start_x, y_pos, 
                scale_start_x + 15, y_pos,
                fill=color, 
                width=2
            )
            
            self.canvas.create_text(
                scale_start_x - 5, 
                y_pos, 
                text=f"{db}", 
                fill="white", 
                font=("Arial", 10), 
                anchor="e"
            )

        # RMS meter
        rms_meter_x = scale_start_x + 40
        self.rms_meter = self.canvas.create_rectangle(
            rms_meter_x, 200, rms_meter_x + 20, 200,
            fill='green',
            outline='white',
            width=1
        )
        
        self.rms_peak_indicator = self.canvas.create_line(
            rms_meter_x, 200, rms_meter_x + 20, 200,
            fill='red',
            width=1
        )
        
        self.canvas.create_text(
            rms_meter_x + 10,
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
        """Show menu when gear button is clicked"""
        try:
            x = self.root.winfo_rootx() + 10
            y = self.root.winfo_rooty() + 40
            self.menu_bar.tk_popup(x, y)
        finally:
            self.menu_bar.grab_release()

    def set_min_freq(self, freq):
        """Set minimum frequency and recreate filters"""
        self.MIN_FREQ = freq
        self.band_centers = np.logspace(
            np.log10(self.MIN_FREQ),
            np.log10(self.MAX_FREQ),
            self.NUM_BANDS
        )
        self.filters = self.create_filters()
        
        # Remove all text elements
        for item in self.canvas.find_all():
            if self.canvas.type(item) == "text":
                self.canvas.delete(item)
        
        # Redraw dB scale
        scale_start_x = 450
        db_scale = [-1, -6, -12, -18, -24, -30, -35, -40, -45, -50, -55, -60]
        
        for db in db_scale:
            y_pos = 200 * (1 - (db + self.LEVEL_RANGE)/self.LEVEL_RANGE)
            color = "red" if db >= -6 else "orange" if db >= -12 else "green"
            
            self.canvas.create_text(
                scale_start_x - 5, 
                y_pos, 
                text=f"{db}", 
                fill="white", 
                font=("Arial", 10), 
                anchor="e"
            )
        
        # Update frequency labels
        band_width = 10
        band_gap = 3
        bands_start_x = 10
        
        for i in range(self.NUM_BANDS):
            if i % 2 == 0:
                x1 = bands_start_x + i * (band_width + band_gap)
                x2 = x1 + band_width
                freq = int(self.band_centers[i])
                text = f"{freq/1000:.1f}K" if freq >= 1000 else f"{freq}"
                self.canvas.create_text(
                    (x1+x2)/2, 
                    215, 
                    text=text, 
                    fill="white", 
                    font=("Arial", 8), 
                    anchor="n"
                )

    def setup_audio(self):
        try:
            # Get input device info
            device_info = sd.query_devices(kind='input')
            device_name = device_info['name']
            self.input_channels = device_info['max_input_channels']
            
            # Update channel mode label
            mode_text = "Stereo - " if self.input_channels >= 2 else "Mono - "
            self.channel_label.config(text=mode_text + device_name)

            self.audio_stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=min(self.input_channels, 2),  # Use max 2 channels
                blocksize=self.BLOCK_SIZE,
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
        
        # For stereo input - average channels
        if indata.shape[1] >= 2:
            mono_signal = np.mean(indata, axis=1)
        else:
            mono_signal = indata[:, 0]
        
        # Calculate RMS of the entire signal
        rms = np.sqrt(np.mean(mono_signal**2))
        self.rms_level = 20 * np.log10(max(rms, 1e-6))
        
        if self.rms_level > self.peak_rms:
            self.peak_rms = self.rms_level
            self.peak_rms_hold_counter = int(self.PEAK_HOLD_TIME * 1000 / self.update_interval)
        
        # Process band filters
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
        # Update RMS meter
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
        
        rms_y = db_to_y(self.smoothed_rms)
        peak_y = db_to_y(self.peak_rms)
        
        # Update RMS meter display
        rms_meter_x = 450 + 40  # Position right of dB scale
        self.canvas.coords(
            self.rms_meter,
            rms_meter_x, rms_y,
            rms_meter_x + 20, 200
        )
        
        color = 'red' if self.smoothed_rms > -6 else \
                'orange' if self.smoothed_rms > -15 else 'green'
        self.canvas.itemconfig(self.rms_meter, fill=color)
        
        # Update peak indicator
        self.canvas.coords(
            self.rms_peak_indicator,
            rms_meter_x, peak_y,
            rms_meter_x + 20, peak_y
        )

        # Update spectrum bands
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

    # Window movement methods
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