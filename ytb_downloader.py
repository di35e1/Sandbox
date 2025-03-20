import tkinter as tk
from tkinter import ttk
from pytubefix import YouTube
import os
import re
import threading
import queue

# Директория для загрузки
download_directory = os.path.expanduser("~") + '/Downloads'
streams = []

# Функция для проверки корректности URL
def is_valid_youtube_url(url):
    regex = r"(?:watch\?v=|shorts\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match is not None

# Функция для вывода прогресса загрузки
def on_progress(stream, chunk, bytes_remaining):
    output_text.insert(tk.END, ".")
    if bytes_remaining == 0:
        output_text.insert(tk.END, "\nЗагружено 100%\n")
    output_text.see(tk.END)

# Функция для получения списка доступных потоков MP4 (streams)
def get_available_streams(url):
    global streams
    try:
        yt = YouTube(url, on_progress_callback=on_progress)
        streams = yt.streams.filter(progressive=False, file_extension='mp4').order_by('resolution').desc()
        return [f"{stream.resolution} (Codec: {stream.video_codec}) ~ {round(stream.filesize/(1024*1024))}MB" for stream in streams]
    except Exception as e:
        return f"Ошибка: {str(e)}"

# Функция для выполнения загрузки
def download_video():
    try:
        selected_index = quality_combobox.current()
        if selected_index == -1:
            output_text.insert(tk.END, "Ошибка: Выберите качество видео.\n")
            return

        selected_stream = streams[selected_index]
        msg = f"Загрузка: {selected_stream.resolution} ({selected_stream.mime_type}, {selected_stream.video_codec})\n"
        output_text.insert(tk.END, msg)

        # Загружаем видео в отдельном потоке
        threading.Thread(
            target=selected_stream.download,
            kwargs={"output_path": download_directory},
            daemon=True
        ).start()

    except Exception as e:
        output_text.insert(tk.END, f"Ошибка: {str(e)}\n")

# Функция для отображения информации и списка доступных потоков
def show_quality_options():
    output_text.pack(padx=10, pady=10)
    output_text.delete(1.0, tk.END)
    url = entry.get()

    if not is_valid_youtube_url(url):
        output_text.insert(tk.END, "Ошибка: Неверный URL YouTube.\n")
        return

    # Очищаем текстовое поле
    output_text.delete(1.0, tk.END)
    output_text.insert(tk.END, "Получаем информацию о видео ...")

    # Создаем очередь для получения результата из потока
    result_queue = queue.Queue()

    # Запускаем функцию в отдельном потоке
    threading.Thread(
        target=lambda q, u: q.put(get_available_streams(u)),
        args=(result_queue, url),
        daemon=True
    ).start()

    # Проверяем результат через 100 мс
    root.after(100, lambda: check_result(result_queue, url))

# Функция для проверки результата из потока
def check_result(result_queue, url):
    try:
        # Пытаемся получить результат из очереди
        result = result_queue.get_nowait()
    except queue.Empty:
        # Если результат еще не готов, проверяем снова через 100 мс
        output_text.insert(tk.END, ".")
        output_text.see(tk.END)
        root.after(100, lambda: check_result(result_queue, url))
        return

    # Обрабатываем результат
    if isinstance(result, list):
        # Обновляем выпадающий список
        quality_combobox['values'] = result
        quality_combobox.current(0)  # Выбираем первый элемент по умолчанию

        # Показываем выпадающий список и кнопку "Скачать"
        quality_label.pack(padx=10, pady=10)
        quality_combobox.pack()
        download_button.pack(padx=10, pady=10)

        # Выводим информацию о видео
        output_text.delete(1.0, tk.END)
        yt = YouTube(url)  # Передаем on_progress
        output_text.insert(tk.END, f"Название видео: {yt.title}\n")
        output_text.insert(tk.END, f"Автор: {yt.author}\n")
        output_text.insert(tk.END, f"Длительность: {yt.length // 60} мин. {yt.length % 60} сек.\n")
    else:
        # Если произошла ошибка, выводим её
        output_text.delete(1.0, tk.END)
        output_text.insert(tk.END, result + "\n")

def close_combobox(event):
    # Генерируем событие Escape, чтобы закрыть выпадающий при перетаскивании окна
    output_text.event_generate('<Escape>')

# Создаем графическое окно
root = tk.Tk()
root.title("Загрузка видео с YouTube")
root.bind('<Configure>', close_combobox)

# Вычисляем координаты центра экрана
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
window_width = 600  # Ширина основного окна
window_height = 380  # Высота основного окна
x = (screen_width // 2) - (window_width // 2)
y = (screen_height // 2) - (window_height // 2)

# Устанавливаем положение и размер основного окна
root.geometry(f"{window_width}x{window_height}+{x}+{y}")
root.resizable(False, False)
root.lift()
root.focus_force()

# Поле для ввода URL
label = tk.Label(root, text="Введите URL YouTube видео:")
label.pack(pady=10)
entry = tk.Entry(root, width=55)
entry.pack(padx=40)

# Кнопка "Проверить URL"
select_quality_button = tk.Button(root, text="Проверить адрес", command=show_quality_options)
select_quality_button.pack(padx=5, pady=5)

# Выпадающий список для выбора качества
quality_label = tk.Label(root, text="Выберите качество:")
quality_combobox = ttk.Combobox(root, state="readonly", width=30)

# Кнопка "Скачать"
download_button = tk.Button(root, text="Скачать", command=download_video)

# Текстовое поле для вывода результата
output_text = tk.Text(root, height=7, width=60, padx=5, pady=5, wrap="word", font=("TkTextFont"),
                      highlightthickness=0, borderwidth=2)

# Запуск основного цикла
root.mainloop()
