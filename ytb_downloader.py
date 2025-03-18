import tkinter as tk
from tkinter import ttk
from pytubefix import YouTube
import os
import re
import threading


# Директория для загрузки
download_directory = os.path.expanduser("~") + '/Downloads'

# Глобальные переменные
progress_line_index = None
streams = []  # Список доступных потоков

# Функция для проверки корректности URL
def is_valid_youtube_url(url):
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match is not None

# Функция для вывода прогресса загрузки
def on_progress(stream, chunk, bytes_remaining):
    # global progress_line_index
    total_size = stream.filesize
    bytes_downloaded = total_size - bytes_remaining
    # percentage = (bytes_downloaded / total_size) * 100

    # if progress_line_index is None:
    #     progress_line_index = output_text.index(tk.END)
    #     output_text.insert(progress_line_index, f"Загружено: {int(percentage)}%\n")
    # else:
    #     output_text.delete(progress_line_index, tk.END)
    #     output_text.insert(progress_line_index, f"Загружено: {int(percentage)}%\n")

    output_text.insert(tk.END, ".")
    if bytes_downloaded == total_size:
        output_text.insert(tk.END, "\nЗагружено 100%\n")
    output_text.see(tk.END)  # Прокрутка текстового поля вниз

# Функция для получения списка доступных потоков
def get_available_streams(url):
    global streams
    try:
        yt = YouTube(url, on_progress_callback=on_progress)  # Передаем on_progress
        streams = yt.streams.filter(progressive=False, file_extension='mp4').order_by('resolution').desc()
        return [f"{stream.resolution} ({stream.mime_type}) - {round(stream.filesize/(1024*1024))}MB" for stream in streams]
    except Exception as e:
        output_text.insert(tk.END, f"Ошибка: {str(e)}\n")
        return []

# Функция для выполнения загрузки
def download_video():
    global progress_line_index

    try:
        # Получаем выбранный поток
        selected_index = quality_combobox.current()
        if selected_index == -1:
            output_text.insert(tk.END, "Ошибка: Выберите качество видео.\n")
            return

        selected_stream = streams[selected_index]

        # Выводим информацию о выбранном потоке
        output_text.insert(tk.END, f"Загрузка: {selected_stream.resolution} ({selected_stream.mime_type})\n")

        # Загружаем видео в отдельном потоке
        threading.Thread(
            target=selected_stream.download,
            kwargs={"output_path": download_directory},
            daemon=True
        ).start()

    except Exception as e:
        output_text.insert(tk.END, f"Ошибка: {str(e)}\n")
    finally:
        progress_line_index = None

# Функция для отображения списка доступных потоков
def show_quality_options():
    output_text.pack(padx=10, pady=10)
    url = entry.get()  # Получаем URL из поля ввода
    output_text.delete(1.0, tk.END)  # Очищаем текстовое поле

    # Проверяем корректность URL
    if not is_valid_youtube_url(url):
        output_text.insert(tk.END, "Ошибка: Неверный URL YouTube.\n")
        return

    # Получаем список доступных потоков
    available_streams = get_available_streams(url)
    if not available_streams:
        output_text.insert(tk.END, "Ошибка: Не удалось получить список потоков.\n")
        return

    # Обновляем выпадающий список
    quality_combobox['values'] = available_streams
    quality_combobox.current(0)  # Выбираем первый элемент по умолчанию

    # Показываем выпадающий список и кнопку "Скачать"
    quality_label.pack(padx=10, pady=10)
    quality_combobox.pack(padx=10, ipady=5)
    download_button.pack(padx=10, pady=10)

    # Выводим информацию о видео
    yt = YouTube(url, on_progress_callback=on_progress)  # Передаем on_progress
    output_text.insert(tk.END, f"Название видео: {yt.title}\n")
    output_text.insert(tk.END, f"Автор: {yt.author}\n")
    output_text.insert(tk.END, f"Длительность: {yt.length} секунд\n")

# Создаем графическое окно
root = tk.Tk()
# Вычисляем координаты центра экрана
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
window_width = 600 # Ширина основного окна
window_height = 400  # Высота основного окна
x = (screen_width // 2) - (window_width // 2)
y = (screen_height // 2) - (window_height // 2)

# Устанавливаем положение и размер основного окна
root.geometry(f"{window_width}x{window_height}+{x}+{y}")
root.minsize(600, 400)
root.resizable(False, False)
root.lift()  # Поднимаем окно на передний план
root.focus_force()  # Принудительно устанавливаем фокус

root.title("Загрузка видео с YouTube")

# Поле для ввода URL
label = tk.Label(root, text="Введите URL YouTube видео:")
label.pack(pady=10)
entry = tk.Entry(root, width=55)
entry.pack(padx=40)

# Кнопка "Выбрать качество"
select_quality_button = tk.Button(root, text="Проверить адрес", command=show_quality_options)
select_quality_button.pack(padx=5, pady=5)

# Выпадающий список для выбора качества (изначально скрыт)
quality_label = tk.Label(root, text="Выберите качество:")
quality_combobox = ttk.Combobox(root, state="readonly")

# Кнопка "Скачать" (изначально скрыта)
download_button = tk.Button(root, text="Скачать", command=download_video)

# Текстовое поле для вывода результата
output_text = tk.Text(root, height=7, width=60, padx=5, pady=5, wrap="word", font=("TkTextFont"), 
                      highlightthickness=0, borderwidth=2)

# Запуск основного цикла
root.mainloop()