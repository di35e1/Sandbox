#!/bin/bash

# Названия файлов
APP_NAME="VU Meter"
SCRIPT_NAME="VUmeter3.py"
ICON_NAME="VUmeter.icns"
BG_IMAGE="background.png" # <--- Имя твоего фонового изображения
VERSION="1.0"
DMG_NAME="${APP_NAME}_${VERSION}.dmg"
VOL_NAME="${APP_NAME} preview"

echo "--- 1. Запуск PyInstaller ---"
python3 -m PyInstaller --noconfirm --windowed \
    --hidden-import "importlib.resources" \
    --name "$APP_NAME" \
    --icon "$ICON_NAME" \
    "$SCRIPT_NAME"



PLIST_PATH="dist/$APP_NAME.app/Contents/Info.plist"

echo "--- 2. Патч Info.plist ---"
if [ -f "$PLIST_PATH" ]; then
    NEW_BLOCK="    <key>CFBundleShortVersionString</key>\n    <string>$VERSION</string>\n    <key>CFBundleVersion</key>\n    <string>$VERSION</string>\n    <key>NSMicrophoneUsageDescription</key>\n    <string>This app requires microphone access to display the audio spectrum and level meters.</string>\n</dict>"
    sed -i '' "s|</dict>|$NEW_BLOCK|" "$PLIST_PATH"
    echo "Info.plist обновлен."
else
    echo "Ошибка: Info.plist не найден!"
    exit 1
fi

echo "--- 3. Переподпись приложения ---"
codesign --force --deep --sign - "dist/$APP_NAME.app"

echo "--- 4. Подготовка DMG ---"
rm -f "dist/$DMG_NAME"
rm -f "dist/tmp.dmg"

# Создаем пустой растущий образ
hdiutil create -size 200m -fs HFS+ -volname "$VOL_NAME" -ov -type SPARSE "dist/tmp.dmg"

# Монтируем его
MOUNT_DIR=$(hdiutil attach -nobrowse "dist/tmp.dmg.sparseimage" | grep -o '/Volumes/.*')
rm -f "$MOUNT_DIR/.DS_Store"

# Копируем приложение и создаем симлинк
cp -R "dist/$APP_NAME.app" "$MOUNT_DIR/"
ln -s /Applications "$MOUNT_DIR/Applications"

# Копируем иконку для тома (опционально)
cp "$ICON_NAME" "$MOUNT_DIR/.VolumeIcon.icns"
setfile -a C "$MOUNT_DIR"

echo "--- 5. Настройка фона и иконок через AppleScript ---"
# Создаем скрытую папку для фона и копируем туда картинку
mkdir "$MOUNT_DIR/.background"
cp "$BG_IMAGE" "$MOUNT_DIR/.background/"

# Выполняем AppleScript для настройки окна Finder
echo "
tell application \"Finder\"
    tell disk \"$VOL_NAME\"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        
        -- Настройка размеров окна (x1, y1, x2, y2)
        -- Подгони под размер твоей картинки (например, 600x400)
        set the bounds of container window to {400, 100, 1000, 500}
        
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 128
        
        -- Установка фона
        set background picture of viewOptions to file \".background:$BG_IMAGE\"
        
        -- Расстановка иконок (x, y)
        -- Подгони координаты под пустые места на картинке
        set position of item \"$APP_NAME.app\" of container window to {165, 205}
        set position of item \"Applications\" of container window to {440, 205}
        
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
" | osascript

echo "--------------------------------------------------------"
echo "ПАУЗА: Окно DMG настроено автоматически."
echo "Проверь, ровно ли встали иконки в пустые слоты на фоне."
echo "При необходимости поправь их руками."
echo "Нажми ЛЮБУЮ КЛАВИШУ в терминале для финальной сборки."
echo "--------------------------------------------------------"

read -n 1 -s

# Размонтируем
hdiutil detach "$MOUNT_DIR"

echo "--- 6. Финализация DMG ---"
hdiutil convert "dist/tmp.dmg.sparseimage" -format UDZO -o "dist/$DMG_NAME"
rm "dist/tmp.dmg.sparseimage"

echo "--- ГОТОВО! Образ создан: dist/$DMG_NAME ---"
open -R "dist/$DMG_NAME"