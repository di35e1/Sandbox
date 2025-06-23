import tkinter as tk
from tkinter import filedialog, messagebox
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
from pyftpdlib.log import config_logging
import threading
import os
import time

# config_logging(level='ERROR')

class FTPGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FTP Server")
        self.server = None
        self.server_thread = None
        self.shutdown_flag = threading.Event()
        
        # GUI elements
        tk.Label(root, text="Port:").grid(row=0, column=0, padx=5, pady=5)
        self.port_entry = tk.Entry(root)
        self.port_entry.insert(0, "2121")
        self.port_entry.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(root, text="Directory:").grid(row=1, column=0, padx=5, pady=5)
        self.dir_entry = tk.Entry(root)
        self.dir_entry.insert(0, "/Users/Shared/") #os.path.expanduser("~")
        self.dir_entry.grid(row=1, column=1, padx=5, pady=5)
        tk.Button(root, text="Browse...", command=self.select_directory).grid(row=1, column=2, padx=5, pady=5)
        
        tk.Label(root, text="Login:").grid(row=2, column=0, padx=5, pady=5)
        self.login_entry = tk.Entry(root)
        self.login_entry.insert(0, "user")
        self.login_entry.grid(row=2, column=1, padx=5, pady=5)
        
        tk.Label(root, text="Password:").grid(row=3, column=0, padx=5, pady=5)
        self.password_entry = tk.Entry(root, show="*")
        self.password_entry.insert(0, "password")
        self.password_entry.grid(row=3, column=1, padx=5, pady=5)
        
        self.anonymous_var = tk.BooleanVar(value=False)
        tk.Checkbutton(root, text="Allow anonymous access", variable=self.anonymous_var).grid(row=4, column=0, columnspan=2, pady=5)
        
        self.start_btn = tk.Button(root, text="Start", command=self.start_server)
        self.start_btn.grid(row=5, column=0, padx=5, pady=5)
        
        self.stop_btn = tk.Button(root, text="Stop", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.grid(row=5, column=1, padx=5, pady=5)
        
        self.status_label = tk.Label(root, text="Server: Stopped", fg="red")
        self.status_label.grid(row=6, column=0, columnspan=3, pady=5)
    
    def select_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, directory)
    
    def start_server(self):
        port = self.port_entry.get()
        directory = self.dir_entry.get()
        login = self.login_entry.get()
        password = self.password_entry.get()
        allow_anonymous = self.anonymous_var.get()
        
        if not port.isdigit():
            messagebox.showerror("Error", "Port must be a number!")
            return
        
        if not os.path.isdir(directory):
            messagebox.showerror("Error", "Directory doesn't exist!")
            return
        
        if not login and not allow_anonymous:
            messagebox.showerror("Error", "Login cannot be empty when anonymous access is disabled!")
            return
        
        try:
            self.shutdown_flag.clear()
            
            authorizer = DummyAuthorizer()
            if login:
                authorizer.add_user(login, password, directory, perm="elradfmw")
            if allow_anonymous:
                authorizer.add_anonymous(directory, perm="elr")

            class SafeHandler(FTPHandler):
                def on_connect(self):
                    if self.server.shutdown_flag.is_set():
                        self.close_when_done()
            
            handler = SafeHandler
            handler.authorizer = authorizer
            
            self.server = FTPServer(("0.0.0.0", int(port)), handler)
            self.server.shutdown_flag = self.shutdown_flag
            
            self.server_thread = threading.Thread(
                target=self._run_server_safe,
                daemon=True
            )
            self.server_thread.start()
            
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            
            status_text = f"Server: Running on port {port}"
            if login:
                status_text += f", login: {login}"
            if allow_anonymous:
                status_text += ", anonymous access: YES"
            
            self.status_label.config(text=status_text, fg="green")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start server:\n{str(e)}")
    
    def _run_server_safe(self):
        try:
            with self.server:
                self.server.serve_forever()
        except Exception as e:
            if not self.shutdown_flag.is_set():
                self._show_error(f"Server crashed:\n{str(e)}")
    
    def _show_error(self, message):
        """Thread-safe error display"""
        self.root.after(0, lambda: messagebox.showerror("Error", message))
    
    def _show_warning(self, message):
        """Thread-safe warning display"""
        self.root.after(0, lambda: messagebox.showwarning("Warning", message))
    
    def stop_server(self):
        """Safely stops FTP server"""
        if not self.server:
            return

        try:
            self.shutdown_flag.set()
            
            # Close connections and server
            if hasattr(self.server, 'close_all'):
                self.server.close_all()
            
            if hasattr(self.server, 'ioloop') and hasattr(self.server.ioloop, 'close'):
                self.server.ioloop.close()
            
            if hasattr(self.server, 'close'):
                self.server.close()
            
            # Wait for thread
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=2.0)
                
        except Exception as e:
            self._show_warning(f"Server shutdown warning:\n{str(e)}")
        finally:
            # Cleanup
            self.server = None
            self.server_thread = None
            
            # Update UI
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_label.config(text="Server: Stopped", fg="red")

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPGUI(root)
    root.mainloop()
