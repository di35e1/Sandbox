import tkinter as tk
from tkinter import filedialog, messagebox
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
from pyftpdlib.log import config_logging
import threading
import os

#config_logging(level='ERROR')

class FTPGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FTP Server")
        self.server = None
        self.server_thread = None
        self.shutdown_flag = threading.Event()
        
        # Directory with Browse button
        tk.Label(root, text="Directory:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.dir_entry = tk.Entry(root, width=20)
        self.dir_entry.insert(0, "/Users/Shared/")
        self.dir_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Button(root, text="Browse...", command=self.select_directory).grid(row=0, column=2, padx=5, pady=5)
        
        # Login
        tk.Label(root, text="Login:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.login_entry = tk.Entry(root)
        self.login_entry.insert(0, "user")
        self.login_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        # Password
        tk.Label(root, text="Password:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.password_entry = tk.Entry(root, show="*")
        self.password_entry.insert(0, "password")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        
        # Anonymous access
        self.anonymous_var = tk.BooleanVar(value=False)
        tk.Checkbutton(root, 
                      text="Allow anonymous access",
                      variable=self.anonymous_var,
                      ).grid(row=4, column=0, columnspan=3, pady=10)
        
        # Port (now before start button)
        tk.Label(root, text="Port:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.port_entry = tk.Entry(root, width=10)
        self.port_entry.insert(0, "2121")
        self.port_entry.grid(row=3, column=1, padx=5, pady=5, sticky='w')
        
        # Single toggle button
        self.toggle_btn = tk.Button(root, 
                                  text="Start Server", 
                                  command=self.toggle_server,
                                  fg="black",
                                  pady=10,
                                  font=('Arial', 12, 'bold'))
        self.toggle_btn.grid(row=5, column=0, columnspan=3, padx=10, pady=10, sticky='ew')
        
        # Status
        self.status_label = tk.Label(root, 
                                   text="● Server: Stopped", 
                                   fg="red",
                                   font=('Arial', 10))
        self.status_label.grid(row=6, column=0, columnspan=3, pady=5)
        
        # Center the window
        root.update_idletasks()
        width = 400
        height = 300
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
    
    def select_directory(self):
        """Open directory selection dialog"""
        directory = filedialog.askdirectory()
        if directory:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, directory)
    
    def toggle_server(self):
        """Toggle server state"""
        if self.server and not self.shutdown_flag.is_set():
            self.stop_server()
        else:
            self.start_server()
    
    def start_server(self):
        """Start FTP server"""
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

            handler = FTPHandler
            handler.authorizer = authorizer
            
            self.server = FTPServer(("0.0.0.0", int(port)), handler)
            self.server.shutdown_flag = self.shutdown_flag
            
            self.server_thread = threading.Thread(
                target=self._run_server_safe,
                daemon=True
            )
            self.server_thread.start()
            
            self.toggle_btn.config(text="Stop Server", bg="#f44336")
            self.status_label.config(text=f"● Server: Running on port {port}", fg="green")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start server:\n{str(e)}")
    
    def _run_server_safe(self):
        """Run server in thread"""
        try:
            with self.server:
                self.server.serve_forever()
        except Exception as e:
            if not self.shutdown_flag.is_set():
                self.root.after(0, lambda: messagebox.showerror("Error", f"Server crashed:\n{str(e)}"))
    
    def stop_server(self):
        """Stop FTP server"""
        if not self.server:
            return

        try:
            self.shutdown_flag.set()
            
            if hasattr(self.server, 'close_all'):
                self.server.close_all()
            
            if hasattr(self.server, 'ioloop') and hasattr(self.server.ioloop, 'close'):
                self.server.ioloop.close()
            
            if hasattr(self.server, 'close'):
                self.server.close()
            
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=2.0)
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showwarning("Warning", f"Server shutdown warning:\n{str(e)}"))
        finally:
            self.server = None
            self.server_thread = None
            self.toggle_btn.config(text="Start Server")
            self.status_label.config(text="● Server: Stopped", fg="red")

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPGUI(root)
    root.mainloop()