#!/bin/bash

# Названия файлов
APP_NAME="VU Meter"
SCRIPT_NAME="VUmeter3.py"
ICON_NAME="VUmeter.icns"
VERSION="1.0" # <--- Указывай версию здесь

echo "--- 1. Запуск PyInstaller ---"
python3 -m PyInstaller --noconfirm --windowed \
    --name "$APP_NAME" \
    --icon "$ICON_NAME" \
    "$SCRIPT_NAME"

# Путь к Info.plist
PLIST_PATH="dist/$APP_NAME.app/Contents/Info.plist"

echo "--- 2. Патч Info.plist (Версия и Микрофон) ---"
if [ -f "$PLIST_PATH" ]; then
    # Создаем блок текста, который нужно вставить
    # Мы используем временную переменную, чтобы избежать ошибок экранирования
    NEW_BLOCK="    <key>CFBundleShortVersionString</key>\n    <string>$VERSION</string>\n    <key>CFBundleVersion</key>\n    <string>$VERSION</string>\n    <key>NSMicrophoneUsageDescription</key>\n    <string>This app requires microphone access to display the audio spectrum and level meters.</string>\n</dict>"

    # Используем sed для поиска </dict> и замены его на наш блок
    # Мы меняем ТОЛЬКО последнее вхождение </dict> в файле
    sed -i '' "s|</dict>|$NEW_BLOCK|" "$PLIST_PATH"
    
    echo "Info.plist успешно обновлен (Версия: $VERSION)."
else
    echo "Ошибка: Info.plist не найден!"
    exit 1
fi

echo "--- 3. Переподпись приложения (Ad-hoc) ---"
codesign --force --deep --sign - "dist/$APP_NAME.app"

echo "--- 5. Открытие папки с приложением ---"
touch "dist/$APP_NAME.app"
open -R "dist/$APP_NAME.app"

#hdiutil create -format UDZO -srcfolder "dist/" "DMG/VU_Meter_v${VERSION}.dmg"

echo "--- ГОТОВО! ---"