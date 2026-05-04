#!/bin/bash

# Очистка старых билдов
rm -rf build dist

# Сборка приложения
# Замените icon.icns на имя вашего файла иконки (или удалите флаг --icon, если её нет)
python3 -m PyInstaller --noconsole --windowed --target-architecture universal2 --name "Socks5Toggle" Socks5toggle.py

# Скрываем иконку из Дока
# Эта команда добавляет параметр LSUIElement = true в Info.plist собранного приложения
echo "Настройка скрытия из Dock..."
plutil -insert LSUIElement -bool true "dist/Socks5Toggle.app/Contents/Info.plist"

echo "Сборка завершена! Ищите приложение в папке dist/"

echo "Упаковка в DMG образ..."

# 1. Создаем временную папку для сборки образа
mkdir -p dist/dmg_tmp

# 2. Копируем туда наше готовое приложение
cp -R "dist/Socks5Toggle.app" "dist/dmg_tmp/"

# 3. Создаем системный ярлык папки "Программы" (чтобы пользователь мог перетащить иконку)
ln -s /Applications "dist/dmg_tmp/Applications"

# 4. Собираем сжатый образ (UDZO) с именем Socks5Toggle.dmg
hdiutil create -volname "Socks5Toggle" -srcfolder "dist/dmg_tmp" -ov -format UDZO "dist/Socks5Toggle.dmg"

# 5. Удаляем временную папку
rm -rf dist/dmg_tmp

# Открываем папку dist в Finder
open "dist/"

echo "Готово! Установочный образ: dist/Socks5Toggle.dmg"