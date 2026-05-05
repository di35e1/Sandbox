import rumps
import subprocess
import os
import sys
import plistlib
import logging

# ----------------- НАСТРОЙКИ -----------------
# Путь к файлу автозагрузки в системе
PLIST_PATH = os.path.expanduser("~/Library/LaunchAgents/com.proxytoggle.app.plist")

# Настройка логирования
LOG_DIR = os.path.expanduser("~/Library/Logs")
LOG_FILE = os.path.join(LOG_DIR, "Socks5Toggle.log")
os.makedirs(LOG_DIR, exist_ok=True)

# Инициализация логгера
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.info("Приложение Socks5Toggle запущено")


# ----------------- ФУНКЦИИ СЕТИ -----------------
def get_active_network_service():
    """Определяет человеческое название активного интерфейса (Wi-Fi, Ethernet и т.д.).
       Возвращает None, если активного подключения (маршрута по умолчанию) нет."""
    try:
        route_proc = subprocess.run(["route", "get", "default"], capture_output=True, text=True)
        # Если маршрута по умолчанию нет, команда вернет код ошибки
        if route_proc.returncode != 0:
            return None
            
        device = None
        for line in route_proc.stdout.split('\n'):
            if 'interface:' in line:
                device = line.split(':')[1].strip()
                break
        
        if not device:
            return None

        hw_ports = subprocess.run(["networksetup", "-listallhardwareports"], capture_output=True, text=True)
        lines = hw_ports.stdout.split('\n')
        for i, line in enumerate(lines):
            if f"Device: {device}" in line:
                port_line = lines[i-1]
                if "Hardware Port:" in port_line:
                    return port_line.split(':')[1].strip()
        return None
    except Exception as e:
        logging.error(f"Ошибка при определении активного интерфейса: {e}")
        return None


# ----------------- АВТОЗАГРУЗКА -----------------
def is_autostart_enabled():
    """Проверяет, существует ли файл автозагрузки."""
    return os.path.exists(PLIST_PATH)

def toggle_autostart_state(enable):
    """Включает или выключает автозагрузку приложения."""
    try:
        if enable:
            current_exec = os.path.abspath(sys.executable)
            app_path = os.path.dirname(os.path.dirname(os.path.dirname(current_exec)))

            launch_agents_dir = os.path.dirname(PLIST_PATH)
            if not os.path.exists(launch_agents_dir):
                os.makedirs(launch_agents_dir, exist_ok=True)

            plist_content = {
                'Label': 'com.proxytoggle.app',
                'ProgramArguments': ['/usr/bin/open', '-a', app_path],
                'RunAtLoad': True
            }
            with open(PLIST_PATH, 'wb') as f:
                plistlib.dump(plist_content, f)
            logging.info("Автозагрузка включена.")
        else:
            if os.path.exists(PLIST_PATH):
                os.remove(PLIST_PATH)
            logging.info("Автозагрузка выключена.")
    except Exception as e:
        logging.error(f"Ошибка изменения статуса автозагрузки: {e}")


# ----------------- ГЛАВНЫЙ КЛАСС ПРИЛОЖЕНИЯ -----------------
class ProxyToggler(rumps.App):
    def __init__(self):
        super(ProxyToggler, self).__init__("🌐", quit_button=None)
        self.interface = get_active_network_service()
        self.proxy_enabled = self.get_proxy_state()
        self.update_ui()

    def get_proxy_state(self):
        """Проверяет, включен ли SOCKS5 в системных настройках."""
        if not self.interface:
            return False
            
        try:
            result = subprocess.run(
                ["networksetup", "-getsocksfirewallproxy", self.interface],
                capture_output=True,
                text=True
            )
            return "Yes" in result.stdout
        except Exception as e:
            logging.error(f"Ошибка при проверке статуса прокси: {e}")
            return False

    def set_proxy_state(self, state):
        """Включает или выключает прокси."""

        if not self.interface:
            return
            
        command = "on" if state else "off"
        try:
            subprocess.run(["networksetup", "-setsocksfirewallproxystate", self.interface, command], check=True)
            status_str = "включен" if state else "выключен"
            logging.info(f"SOCKS5 прокси успешно {status_str} на интерфейсе: {self.interface}")
        except Exception as e:
            logging.error(f"Ошибка изменения статуса прокси на {self.interface}: {e}")

    def update_ui(self):
        """Перерисовывает меню и иконки в зависимости от наличия сети."""
        self.menu.clear()
        
        if self.interface:
            self.title = "🟢 Proxy" if self.proxy_enabled else "⚪️ Proxy"
            status_text = "Выключить SOCKS5" if self.proxy_enabled else "Включить SOCKS5"
            
            self.menu.add(rumps.MenuItem(title=f"Интерфейс: {self.interface}"))
            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem(title=status_text, callback=self.toggle_proxy))
            
        else:
            self.title = "🔴 No network"
            self.menu.add(rumps.MenuItem(title="No interface", callback=None))
            
            # Делаем кнопку неактивной, передавая callback=None
            inactive_btn = rumps.MenuItem(title="Включить SOCKS5", callback=None)
            self.menu.add(inactive_btn)
            
        self.menu.add(rumps.separator)
        
        # Блок автозагрузки
        autostart_text = "✓ Запускать при старте" if is_autostart_enabled() else "Запускать при старте"
        self.menu.add(rumps.MenuItem(title=autostart_text, callback=self.toggle_autostart_menu))
        self.menu.add(rumps.separator)
        
        # Выход
        self.menu.add(rumps.MenuItem(title="Выход", callback=self.quit_app))

    def toggle_proxy(self, _):
        """Обработка клика 'Включить/Выключить'."""
        if not self.interface:
            return
            
        self.set_proxy_state(not self.proxy_enabled)

        self.proxy_enabled = self.get_proxy_state()
        self.update_ui()

    def toggle_autostart_menu(self, _):
        """Обработка клика 'Запускать при старте'."""
        current_state = is_autostart_enabled()
        toggle_autostart_state(not current_state)
        self.update_ui()

    def quit_app(self, _):
        logging.info("Приложение Socks5Toggle завершило работу")
        rumps.quit_application()

    # Таймер проверки: 300 секунд = 5 минут (как мы обсуждали для десктопа)
    @rumps.timer(300)
    def monitor_status(self, _):
        """Фоновая проверка раз в 5 минут."""
        new_interface = get_active_network_service()
        changed = False
        
        if new_interface != self.interface:
            if self.interface is None and new_interface is not None:
                logging.info(f"Сеть появилась. Активный интерфейс: {new_interface}")
            elif self.interface is not None and new_interface is None:
                logging.warning(f"Соединение с сетью потеряно (интерфейс {self.interface} отключен)")
            else:
                logging.info(f"Обнаружена смена интерфейса: {self.interface} -> {new_interface}")
                
            self.interface = new_interface
            changed = True

        current_status = self.get_proxy_state()
        if current_status != self.proxy_enabled:
            status_str = "включен" if current_status else "выключен"
            logging.info(f"Статус прокси изменен извне (или из-за смены сети): {status_str}")
            self.proxy_enabled = current_status
            changed = True

        if changed:
            self.update_ui()

if __name__ == "__main__":
    ProxyToggler().run()
