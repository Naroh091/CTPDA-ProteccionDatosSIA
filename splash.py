# Aplicación para la protección de datos en Sistemas IA
# Copyright (C) 2025-2026 Consejo de Transparencia y Protección de Datos de Andalucía
#
# Este programa se distribuye bajo la Licencia Pública de la Unión Europea,
# versión 1.2 (EUPL v1.2), disponible en:
# https://eupl.eu/1.2/es/

"""
Módulo de Splash Screen para SupervisionSIA.

Proporciona feedback visual inmediato al usuario mientras la aplicación
carga en segundo plano. Incluye:
- Ventana splash con animación de carga
- Sistema de bloqueo para evitar múltiples instancias
- Actualización dinámica de mensajes de estado
"""

import os
import sys
import threading
import time
import tempfile
try:
    import psutil
except ImportError:
    psutil = None

# Archivo de bloqueo para evitar múltiples instancias
LOCK_FILE = os.path.join(os.environ.get('TEMP', '/tmp'), 'supervisionsia.lock')

# Nombre de la aplicación (se configura desde app.py)
_APP_NAME = "SupervisionSIA"  # Valor por defecto


def set_app_name(name):
    """Configura el nombre de la aplicación para mostrar en el splash y mensajes."""
    global _APP_NAME
    _APP_NAME = name


def get_app_name():
    """Obtiene el nombre de la aplicación configurado."""
    return _APP_NAME


def get_lock_file_path():
    """Obtiene la ruta del archivo de bloqueo según el sistema operativo."""
    return os.path.join(tempfile.gettempdir(), 'supervisionsia.lock')


def is_another_instance_running():
    """
    Verifica si ya hay otra instancia de la aplicación en ejecución.
    
    Returns:
        bool: True si hay otra instancia, False en caso contrario.
    """
    lock_path = get_lock_file_path()
    
    try:
        if os.path.exists(lock_path):
            # Verificar si el archivo de bloqueo es reciente (menos de 60 segundos)
            # Si es muy antiguo, probablemente sea un residuo de un cierre forzado
            file_age = time.time() - os.path.getmtime(lock_path)
            if file_age < 60:
                # Verificar si el proceso sigue activo leyendo el PID
                try:
                    with open(lock_path, 'r') as f:
                        pid = int(f.read().strip())
                    
                    # Verificar si el proceso existe
                    if psutil:
                        if psutil.pid_exists(pid):
                            return True
                    else:
                        try:
                            os.kill(pid, 0)  # No mata el proceso, solo verifica si existe
                            return True
                        except (OSError, ProcessLookupError):
                            pass
                except (ValueError, OSError, PermissionError):
                    # El proceso no existe o no se puede verificar
                    pass
            
            # El archivo de bloqueo es antiguo o el proceso no existe, eliminarlo
            try:
                os.remove(lock_path)
            except OSError:
                pass
                
        return False
    except Exception:
        return False


def create_lock_file():
    """Crea el archivo de bloqueo con el PID actual."""
    lock_path = get_lock_file_path()
    try:
        with open(lock_path, 'w') as f:
            f.write(str(os.getpid()))
    except Exception:
        pass  # No se pudo crear archivo de bloqueo, continuar sin él


def remove_lock_file():
    """Elimina el archivo de bloqueo."""
    lock_path = get_lock_file_path()
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


class SplashScreen:
    """
    Splash screen con tkinter para mostrar durante el arranque.
    
    Muestra una ventana centrada con:
    - Logo/título de la aplicación
    - Barra de progreso animada
    - Mensaje de estado actualizable
    """
    
    def __init__(self):
        self.root = None
        self.status_label = None
        self.progress_canvas = None
        self.progress_position = 0
        self.is_running = False
        self._animation_id = None
        
    def show(self):
        """Muestra la ventana splash en un hilo separado."""
        self.is_running = True
        self.splash_thread = threading.Thread(target=self._create_window, daemon=True)
        self.splash_thread.start()
        # Pequeña pausa para asegurar que la ventana se crea
        time.sleep(0.1)
        
    def _create_window(self):
        """Crea y muestra la ventana splash."""
        try:
            import tkinter as tk
            from tkinter import font as tkfont
        except ImportError:
            # tkinter no disponible, continuar sin splash screen
            return
            
        try:
            self.root = tk.Tk()
            self.root.overrideredirect(True)  # Sin bordes de ventana
            
            # Dimensiones
            width = 450
            height = 200
            
            # Centrar en pantalla
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            
            # Fondo con gradiente simulado (color sólido elegante)
            bg_color = "#2c3e50"  # Azul oscuro elegante
            accent_color = "#3498db"  # Azul claro
            text_color = "#ecf0f1"  # Blanco suave
            
            self.root.configure(bg=bg_color)
            
            # Frame principal con borde
            main_frame = tk.Frame(self.root, bg=bg_color, highlightbackground=accent_color, 
                                  highlightthickness=2)
            main_frame.pack(fill='both', expand=True, padx=2, pady=2)
            
            # Título
            try:
                title_font = tkfont.Font(family="Segoe UI", size=18, weight="bold")
            except:
                title_font = ("Arial", 18, "bold")
            
            title_label = tk.Label(main_frame, text=_APP_NAME, 
                                   font=title_font, fg=text_color, bg=bg_color)
            title_label.pack(pady=(30, 5))
            
            # Subtítulo
            try:
                subtitle_font = tkfont.Font(family="Segoe UI", size=10)
            except:
                subtitle_font = ("Arial", 10)
            
            subtitle_label = tk.Label(main_frame, 
                                      text="Protección de Datos en Sistemas de IA",
                                      font=subtitle_font, fg="#bdc3c7", bg=bg_color)
            subtitle_label.pack(pady=(0, 20))
            
            # Canvas para barra de progreso animada
            self.progress_canvas = tk.Canvas(main_frame, width=350, height=6, 
                                             bg="#34495e", highlightthickness=0)
            self.progress_canvas.pack(pady=(10, 15))
            
            # Mensaje de estado
            try:
                status_font = tkfont.Font(family="Segoe UI", size=9)
            except:
                status_font = ("Arial", 9)
            
            self.status_label = tk.Label(main_frame, text="Iniciando aplicación...",
                                         font=status_font, fg="#95a5a6", bg=bg_color)
            self.status_label.pack(pady=(5, 20))
            
            # Hacer la ventana siempre visible
            self.root.attributes('-topmost', True)
            self.root.lift()
            
            # Iniciar animación de progreso
            self._animate_progress()
            
            # Bucle principal
            self.root.mainloop()
            
        except Exception:
            # Error creando splash screen, continuar sin él
            self.is_running = False
    
    def _animate_progress(self):
        """Anima la barra de progreso con efecto de onda."""
        if not self.is_running or not self.progress_canvas:
            return
            
        try:
            # Limpiar canvas
            self.progress_canvas.delete("progress")
            
            # Dibujar barra de progreso animada (efecto de onda)
            bar_width = 80
            canvas_width = 350
            
            # Calcular posición con efecto de rebote suave
            self.progress_position = (self.progress_position + 4) % (canvas_width + bar_width)
            x1 = self.progress_position - bar_width
            x2 = self.progress_position
            
            # Dibujar con gradiente simulado
            self.progress_canvas.create_rectangle(
                max(0, x1), 0, min(canvas_width, x2), 6,
                fill="#3498db", outline="", tags="progress"
            )
            
            # Programar siguiente frame
            if self.is_running:
                self._animation_id = self.root.after(30, self._animate_progress)
                
        except Exception:
            pass
    
    def update_status(self, message):
        """
        Actualiza el mensaje de estado en la ventana splash.
        
        Args:
            message (str): Nuevo mensaje a mostrar.
        """
        if self.root and self.status_label and self.is_running:
            try:
                self.root.after(0, lambda: self.status_label.configure(text=message))
            except Exception:
                pass
    
    def close(self):
        """Cierra la ventana splash de forma segura."""
        self.is_running = False
        if self.root:
            try:
                if self._animation_id:
                    self.root.after_cancel(self._animation_id)
                self.root.after(0, self.root.destroy)
            except Exception:
                pass


def show_duplicate_instance_warning():
    """
    Muestra un mensaje de advertencia cuando ya hay otra instancia en ejecución.
    """
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        # Crear ventana oculta para el diálogo
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        messagebox.showwarning(
            f"{_APP_NAME} - Instancia Activa",
            f"Ya hay una instancia de {_APP_NAME} en ejecución.\n\n"
            "Por favor, use la ventana del navegador existente o cierre "
            "la aplicación antes de iniciar una nueva instancia."
        )
        
        root.destroy()
        
    except ImportError:
        # tkinter no disponible, pausa breve como fallback silencioso
        time.sleep(3)


# Instancia global del splash (para uso desde app.py)
_splash_instance = None


def get_splash():
    """Obtiene la instancia global del splash screen."""
    global _splash_instance
    if _splash_instance is None:
        _splash_instance = SplashScreen()
    return _splash_instance


def show_splash():
    """Muestra el splash screen."""
    splash = get_splash()
    splash.show()
    return splash


def update_splash_status(message):
    """Actualiza el mensaje del splash screen."""
    global _splash_instance
    if _splash_instance:
        _splash_instance.update_status(message)


def close_splash():
    """Cierra el splash screen."""
    global _splash_instance
    if _splash_instance:
        _splash_instance.close()
        _splash_instance = None
