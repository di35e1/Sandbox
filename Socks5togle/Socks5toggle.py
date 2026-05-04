import rumps
import subprocess
import os
import sys
import plistlib

# ----------------- НАСТРОЙКИ -----------------
# Путь к файлу автозагрузки в системе
PLIST_PATH = os.path.expanduser("~/Library/LaunchAgents/com.proxytoggle.app.plist")


# ----------------- ФУНКЦИИ СЕТИ -----------------
def get_active_network_service():
    """Определяет человеческое название активного интерфейса (Wi-Fi, Ethernet и т.д.)."""
    try:
        route_out = subprocess.check_output(["route", "get", "default"], text=True)
        device = None
        for line in route_out.split('\n'):
            if 'interface:' in line:
                device = line.split(':')[1].strip()
                break
        
        if not device:
            return "Wi-Fi"

        hw_ports = subprocess.check_output(["networksetup", "-listallhardwareports"], text=True)
        lines = hw_ports.split('\n')
        for i, line in enumerate(lines):
            if f"Device: {device}" in line:
                port_line = lines[i-1]
                if "Hardware Port:" in port_line:
                    return port_line.split(':')[1].strip()
        return "Wi-Fi"
    except Exception:
        return "Wi-Fi"


# ----------------- АВТОЗАГРУЗКА -----------------
def is_autostart_enabled():
    """Проверяет, существует ли файл автозагрузки."""
    return os.path.exists(PLIST_PATH)

def toggle_autostart_state(enable):
    """Включает или выключает автозагрузку приложения."""
    if enable:
        # Вычисляем путь к корню нашего .app (поднимаемся на 3 папки вверх от sys.executable)
        current_exec = os.path.abspath(sys.executable)
        app_path = os.path.dirname(os.path.dirname(os.path.dirname(current_exec)))

        plist_content = {
            'Label': 'com.proxytoggle.app',
            'ProgramArguments': ['/usr/bin/open', '-a', app_path],
            'RunAtLoad': True
        }
        with open(PLIST_PATH, 'wb') as f:
            plistlib.dump(plist_content, f)
    else:
        # Выключаем автозагрузку (удаляем файл)
        if os.path.exists(PLIST_PATH):
            os.remove(PLIST_PATH)


# ----------------- ГЛАВНЫЙ КЛАСС ПРИЛОЖЕНИЯ -----------------
class ProxyToggler(rumps.App):
    def __init__(self):
        super(ProxyToggler, self).__init__("🌐", quit_button=None)
        self.interface = get_active_network_service()
        self.proxy_enabled = self.get_proxy_state()
        self.update_ui()

    def get_proxy_state(self):
        """Проверяет, включен ли SOCKS5 в системных настройках."""
        try:
            result = subprocess.run(
                ["networksetup", "-getsocksfirewallproxy", self.interface],
                capture_output=True,
                text=True
            )
            return "Yes" in result.stdout
        except Exception:
            return False

    def set_proxy_state(self, state):
        """Включает или выключает прокси."""
        command = "on" if state else "off"
        try:
            subprocess.run(["networksetup", "-setsocksfirewallproxystate", self.interface, command])
        except Exception as e:
            print(f"Ошибка изменения: {e}")

    def update_ui(self):
        """Перерисовывает меню и иконки."""
        status_text = "Выключить SOCKS5" if self.proxy_enabled else "Включить SOCKS5"
        autostart_text = "✓ Запускать при старте" if is_autostart_enabled() else "Запускать при старте"
        
        self.menu.clear()
        # Блок статуса сети
        self.menu.add(rumps.MenuItem(title=f"Интерфейс: {self.interface}"))
        self.menu.add(rumps.separator)
        
        # Блок управления прокси
        self.menu.add(rumps.MenuItem(title=status_text, callback=self.toggle_proxy))
        self.menu.add(rumps.separator)
        
        # Блок автозагрузки
        self.menu.add(rumps.MenuItem(title=autostart_text, callback=self.toggle_autostart_menu))
        self.menu.add(rumps.separator)
        
        # Выход
        self.menu.add(rumps.MenuItem(title="Выход", callback=rumps.quit_application))
        
        # Смена индикатора в строке меню
        self.title = "🟢 Proxy" if self.proxy_enabled else "⚪️ Proxy"

    def toggle_proxy(self, _):
        """Обработка клика 'Включить/Выключить'."""
        self.proxy_enabled = not self.proxy_enabled
        self.set_proxy_state(self.proxy_enabled)
        self.proxy_enabled = self.get_proxy_state()
        self.update_ui()

    def toggle_autostart_menu(self, _):
        """Обработка клика 'Запускать при старте'."""
        current_state = is_autostart_enabled()
        toggle_autostart_state(not current_state)
        self.update_ui()

    # Таймер проверки: 300 секунд = 5 минут (как мы обсуждали для десктопа)
    @rumps.timer(300)
    def monitor_status(self, _):
        """Фоновая проверка раз в 5 минут."""
        new_interface = get_active_network_service()
        changed = False
        
        if new_interface != self.interface:
            self.interface = new_interface
            changed = True

        current_status = self.get_proxy_state()
        if current_status != self.proxy_enabled:
            self.proxy_enabled = current_status
            changed = True

        if changed:
            self.update_ui()

if __name__ == "__main__":
    ProxyToggler().run()
