import os
import sys
import subprocess

# Monkey-patch subprocess.Popen on Windows to globally suppress cmd console windows
if sys.platform == 'win32':
    original_popen = subprocess.Popen
    class PatchedPopen(original_popen):
        def __init__(self, *args, **kwargs):
            creationflags = kwargs.get('creationflags', 0)
            creationflags |= subprocess.CREATE_NO_WINDOW
            kwargs['creationflags'] = creationflags
            super().__init__(*args, **kwargs)
    subprocess.Popen = PatchedPopen

# Check if we are running as a CLI proxy for the subprocesses
if len(sys.argv) > 1 and sys.argv[1] == "--run-spotdl":
    from spotdl.console.entry_point import entry_point
    sys.argv = ["spotdl"] + sys.argv[2:]
    try:
        entry_point()
    except SystemExit as e:
        sys.exit(e.code)
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] == "--run-ytdlp":
    import yt_dlp
    sys.argv = ["yt_dlp"] + sys.argv[2:]
    try:
        yt_dlp.main()
    except SystemExit as e:
        sys.exit(e.code)
    sys.exit(0)

import json
import shutil
import threading
import subprocess
import re
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

def get_sys_cmd(proxy_arg):
    if getattr(sys, 'frozen', False):
        return [sys.executable, proxy_arg]
    else:
        return [sys.executable, os.path.abspath(sys.argv[0]), proxy_arg]

# Set initial window styling configuration
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

CONFIG_FILE = "downloader_config.json"

class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Spotify & YouTube Downloader - Premium Edition")
        self.geometry("820x600")
        self.resizable(False, False)
        
        # Load user configuration
        self.config = self.load_config()
        self.current_process = None
        self.is_downloading = False
        
        # Setup UI layout
        self.setup_ui()
        
        # Initial check for FFmpeg status
        self.update_ffmpeg_status()

    def load_config(self):
        default_dir = os.path.join(os.path.expanduser('~'), 'Music')
        if not os.path.exists(default_dir):
            default_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
            
        defaults = {
            "spotify_client_id": "",
            "spotify_client_secret": "",
            "save_directory": default_dir,
            "format": "mp3",
            "bitrate": "320k"
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                    # Merge keys to support updates
                    for k, v in defaults.items():
                        if k not in user_data:
                            user_data[k] = v
                    return user_data
            except Exception:
                return defaults
        return defaults

    def save_config(self):
        self.config["spotify_client_id"] = self.spotify_id_entry.get().strip()
        self.config["spotify_client_secret"] = self.spotify_secret_entry.get().strip()
        self.config["save_directory"] = self.path_entry.get().strip()
        self.config["format"] = self.format_option.get()
        
        bitrate_map = {
            "320kbps (Máxima)": "320k",
            "256kbps (Alta)": "256k",
            "192kbps (Estándar)": "192k",
            "Original (Sin Re-codificar)": "disable"
        }
        self.config["bitrate"] = bitrate_map.get(self.bitrate_option.get(), "320k")
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
            self.log("Configuración guardada correctamente.\n")
        except Exception as e:
            self.log(f"Error al guardar la configuración: {e}\n")

    def get_ffmpeg_path(self):
        # 1. Check system path
        path = shutil.which("ffmpeg")
        if path:
            return path
        
        # 2. Check spotdl download path (~/.spotdl/ffmpeg.exe)
        user_home = os.path.expanduser("~")
        spotdl_ffmpeg = os.path.join(user_home, ".spotdl", "ffmpeg.exe")
        if os.path.exists(spotdl_ffmpeg):
            return spotdl_ffmpeg
        
        # 3. Check local execution folder
        local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
            
        return None

    def update_ffmpeg_status(self):
        ffmpeg_path = self.get_ffmpeg_path()
        if ffmpeg_path:
            self.ffmpeg_status_label.configure(text="FFmpeg: Listo (Detectado)", text_color="#1DB954")
            self.ffmpeg_btn.configure(text="Reinstalar FFmpeg", fg_color="gray")
        else:
            self.ffmpeg_status_label.configure(text="FFmpeg: No detectado", text_color="#E74C3C")
            self.ffmpeg_btn.configure(text="Instalar FFmpeg", fg_color="#E67E22")

    def setup_ui(self):
        # Configure Grid Layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ------------------ SIDEBAR (LEFT) ------------------
        self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(14, weight=1)

        # Sidebar Title
        self.sidebar_title = ctk.CTkLabel(
            self.sidebar_frame, 
            text="CONFIGURACIÓN", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.sidebar_title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        # Audio Format
        self.format_label = ctk.CTkLabel(self.sidebar_frame, text="Formato de salida:", font=ctk.CTkFont(size=12))
        self.format_label.grid(row=1, column=0, padx=20, pady=(10, 2), sticky="w")
        self.format_option = ctk.CTkOptionMenu(
            self.sidebar_frame, 
            values=["mp3", "m4a", "flac", "wav"],
            fg_color="#2C2C2C",
            button_color="#1DB954",
            button_hover_color="#1AA34A"
        )
        self.format_option.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.format_option.set(self.config.get("format", "mp3"))

        # Audio Quality
        self.bitrate_label = ctk.CTkLabel(self.sidebar_frame, text="Calidad / Bitrate:", font=ctk.CTkFont(size=12))
        self.bitrate_label.grid(row=3, column=0, padx=20, pady=(10, 2), sticky="w")
        
        bitrate_rev_map = {
            "320k": "320kbps (Máxima)",
            "256k": "256kbps (Alta)",
            "192k": "192kbps (Estándar)",
            "disable": "Original (Sin Re-codificar)"
        }
        self.bitrate_option = ctk.CTkOptionMenu(
            self.sidebar_frame, 
            values=["320kbps (Máxima)", "256kbps (Alta)", "192kbps (Estándar)", "Original (Sin Re-codificar)"],
            fg_color="#2C2C2C",
            button_color="#1DB954",
            button_hover_color="#1AA34A"
        )
        self.bitrate_option.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.bitrate_option.set(bitrate_rev_map.get(self.config.get("bitrate", "320k"), "320kbps (Máxima)"))

        # Spotify Credentials (Important for Playlist downloads)
        self.spotify_title = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Spotify API (Opcional - Para Listas)", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#1DB954"
        )
        self.spotify_title.grid(row=5, column=0, padx=20, pady=(15, 5), sticky="w")

        self.spotify_id_label = ctk.CTkLabel(self.sidebar_frame, text="Spotify Client ID:", font=ctk.CTkFont(size=11))
        self.spotify_id_label.grid(row=6, column=0, padx=20, pady=0, sticky="w")
        self.spotify_id_entry = ctk.CTkEntry(
            self.sidebar_frame, 
            placeholder_text="Client ID", 
            show="*", 
            fg_color="#2C2C2C"
        )
        self.spotify_id_entry.grid(row=7, column=0, padx=20, pady=(2, 8), sticky="ew")
        self.spotify_id_entry.insert(0, self.config.get("spotify_client_id", ""))

        self.spotify_secret_label = ctk.CTkLabel(self.sidebar_frame, text="Spotify Client Secret:", font=ctk.CTkFont(size=11))
        self.spotify_secret_label.grid(row=8, column=0, padx=20, pady=0, sticky="w")
        self.spotify_secret_entry = ctk.CTkEntry(
            self.sidebar_frame, 
            placeholder_text="Client Secret", 
            show="*", 
            fg_color="#2C2C2C"
        )
        self.spotify_secret_entry.grid(row=9, column=0, padx=20, pady=(2, 10), sticky="ew")
        self.spotify_secret_entry.insert(0, self.config.get("spotify_client_secret", ""))

        self.save_settings_btn = ctk.CTkButton(
            self.sidebar_frame, 
            text="Guardar Configuración", 
            command=self.save_config,
            fg_color="#2C2C2C",
            hover_color="#3C3C3C",
            border_width=1,
            border_color="#1DB954"
        )
        self.save_settings_btn.grid(row=10, column=0, padx=20, pady=10, sticky="ew")

        # FFmpeg Installer section
        self.ffmpeg_title = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Conversión de Audio", 
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.ffmpeg_title.grid(row=11, column=0, padx=20, pady=(15, 2), sticky="w")
        
        self.ffmpeg_status_label = ctk.CTkLabel(self.sidebar_frame, text="FFmpeg: Cargando...", font=ctk.CTkFont(size=11))
        self.ffmpeg_status_label.grid(row=12, column=0, padx=20, pady=0, sticky="w")
        
        self.ffmpeg_btn = ctk.CTkButton(
            self.sidebar_frame, 
            text="Instalar FFmpeg", 
            command=self.trigger_ffmpeg_install,
            height=26,
            font=ctk.CTkFont(size=11)
        )
        self.ffmpeg_btn.grid(row=13, column=0, padx=20, pady=(5, 20), sticky="ew")

        # ------------------ MAIN CONTAINER (RIGHT) ------------------
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=25, pady=20)
        self.main_frame.grid_rowconfigure(7, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Title/Banner
        self.main_title = ctk.CTkLabel(
            self.main_frame, 
            text="Spotify & YouTube Playlist Downloader", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.main_title.grid(row=0, column=0, pady=(5, 2), sticky="w")
        
        self.main_subtitle = ctk.CTkLabel(
            self.main_frame, 
            text="Descarga música y listas de reproducción en la máxima calidad disponible de forma automática.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.main_subtitle.grid(row=1, column=0, pady=(0, 15), sticky="w")

        # URL Input Frame
        self.url_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.url_frame.grid(row=2, column=0, sticky="ew", pady=5)
        self.url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            self.url_frame, 
            placeholder_text="Pegue el enlace del video, canción o playlist aquí...", 
            height=45,
            fg_color="#1E1E1E",
            border_width=1,
            border_color="#333333"
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.url_entry.bind("<KeyRelease>", self.on_url_input_change)

        self.paste_btn = ctk.CTkButton(
            self.url_frame, 
            text="Pegar", 
            command=self.paste_clipboard,
            width=80,
            height=45,
            fg_color="#2A2A2A",
            hover_color="#3A3A3A"
        )
        self.paste_btn.grid(row=0, column=1)

        # Output folder Selection
        self.path_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.path_frame.grid(row=3, column=0, sticky="ew", pady=10)
        self.path_frame.grid_columnconfigure(0, weight=1)
        
        self.path_entry = ctk.CTkEntry(self.path_frame, height=35, fg_color="#1E1E1E", border_width=1)
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.path_entry.insert(0, self.config.get("save_directory", ""))
        
        self.browse_btn = ctk.CTkButton(
            self.path_frame, 
            text="Seleccionar Carpeta", 
            command=self.browse_folder,
            width=140,
            height=35,
            fg_color="#2A2A2A",
            hover_color="#3A3A3A"
        )
        self.browse_btn.grid(row=0, column=1)

        # Progress elements
        self.progress_label = ctk.CTkLabel(
            self.main_frame, 
            text="Estado: Inactivo", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.progress_label.grid(row=4, column=0, pady=(15, 2), sticky="w")
        
        self.progress_bar = ctk.CTkProgressBar(self.main_frame)
        self.progress_bar.grid(row=5, column=0, sticky="ew", pady=(2, 15))
        self.progress_bar.set(0.0)

        # Download / Action buttons
        self.actions_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.actions_frame.grid(row=6, column=0, sticky="ew", pady=5)
        self.actions_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(
            self.actions_frame, 
            text="INICIAR DESCARGA", 
            command=self.start_download,
            height=45,
            fg_color="#1DB954",
            hover_color="#1AA34A",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.download_btn.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            self.actions_frame, 
            text="CANCELAR", 
            command=self.cancel_download,
            height=45,
            width=120,
            fg_color="#333333",
            hover_color="#E74C3C",
            state="disabled",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.cancel_btn.grid(row=0, column=1)

        # Scrollable console logging area
        self.console_textbox = ctk.CTkTextbox(
            self.main_frame, 
            fg_color="#0F0F0F",
            border_width=1,
            border_color="#222222",
            font=ctk.CTkFont(family="Courier", size=11),
            text_color="#BBBBBB"
        )
        self.console_textbox.grid(row=7, column=0, sticky="nsew", pady=(15, 5))

    def on_url_input_change(self, event=None):
        url = self.url_entry.get().strip().lower()
        if "spotify.com" in url:
            # Change download button style to Spotify green
            self.download_btn.configure(fg_color="#1DB954", hover_color="#1AA34A", text="DESCARGAR DE SPOTIFY")
        elif "youtube.com" in url or "youtu.be" in url:
            # Change download button style to YouTube red
            self.download_btn.configure(fg_color="#FF0000", hover_color="#CC0000", text="DESCARGAR DE YOUTUBE")
        else:
            # Generic button style
            self.download_btn.configure(fg_color="#1DB954", hover_color="#1AA34A", text="INICIAR DESCARGA")

    def paste_clipboard(self):
        try:
            clipboard = self.clipboard_get()
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, clipboard.strip())
            self.on_url_input_change()
        except Exception:
            pass

    def browse_folder(self):
        selected_folder = filedialog.askdirectory(initialdir=self.path_entry.get())
        if selected_folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, os.path.normpath(selected_folder))

    def log(self, message):
        self.console_textbox.insert(tk.END, message)
        self.console_textbox.see(tk.END)

    def trigger_ffmpeg_install(self):
        self.ffmpeg_btn.configure(state="disabled")
        self.ffmpeg_status_label.configure(text="Descargando FFmpeg...", text_color="#E67E22")
        threading.Thread(target=self.install_ffmpeg_thread, daemon=True).start()

    def install_ffmpeg_thread(self):
        try:
            self.log("Iniciando descarga automatizada de FFmpeg mediante spotDL...\n")
            cmd = get_sys_cmd("--run-spotdl") + ["--download-ffmpeg"]
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                self.log(f"[FFmpeg] {line}")
            
            process.wait()
            self.update_ffmpeg_status()
            if self.get_ffmpeg_path():
                self.log("FFmpeg instalado con éxito!\n")
            else:
                self.log("Error: No se pudo verificar la instalación de FFmpeg.\n")
        except Exception as e:
            self.log(f"Error al descargar FFmpeg: {e}\n")
            self.update_ffmpeg_status()

    def start_download(self):
        if self.is_downloading:
            return
            
        url = self.url_entry.get().strip()
        if not url:
            self.log("Error: Por favor introduzca un enlace válido de Spotify o YouTube.\n")
            return
            
        # Clean localized Spotify URLs (e.g. open.spotify.com/intl-es/... -> open.spotify.com/...)
        if "open.spotify.com" in url.lower():
            url = re.sub(r'open\.spotify\.com/intl-[^/]+/', 'open.spotify.com/', url)
            self.log(f"[Sistema] URL internacional de Spotify adaptada a: {url}\n")
            
        save_dir = self.path_entry.get().strip()
        if not os.path.exists(save_dir):
            self.log(f"Creando directorio de salida: {save_dir}\n")
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception as e:
                self.log(f"Error al crear el directorio: {e}\n")
                return

        # Prepare GUI for Downloading state
        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="DESCARGANDO...")
        self.cancel_btn.configure(state="normal")
        self.url_entry.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.progress_label.configure(text="Estado: Iniciando descarga...")
        self.console_textbox.delete("1.0", tk.END)
        
        # Run process in a thread to keep GUI responsive
        threading.Thread(target=self.download_thread, args=(url, save_dir), daemon=True).start()

    def cancel_download(self):
        if self.current_process:
            self.log("\n[Sistema] Cancelando la descarga... Por favor espere.\n")
            self.progress_label.configure(text="Estado: Cancelando...")
            try:
                # Terminate subprocess tree
                self.current_process.terminate()
                self.current_process.wait(timeout=3)
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass
            self.current_process = None
            
        self.finish_download_state("Descarga cancelada por el usuario.")

    def finish_download_state(self, message):
        self.is_downloading = False
        self.download_btn.configure(state="normal")
        self.on_url_input_change()
        self.cancel_btn.configure(state="disabled")
        self.url_entry.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self.progress_label.configure(text=f"Estado: {message}")
        self.current_process = None

    def download_thread(self, url, save_dir):
        # Identify platform and launch corresponding downloader
        is_spotify = "spotify.com" in url.lower()
        
        # Auto check environment credentials if it is Spotify
        client_id = self.spotify_id_entry.get().strip()
        client_secret = self.spotify_secret_entry.get().strip()
        
        # Regex parsers
        ytdl_progress_pat = re.compile(r'\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+(\S+)\s+at\s+(\S+)\s+ETA\s+(\S+)')
        ytdl_dest_pat = re.compile(r'\[download\] Destination:\s+(.*)')
        
        spotdl_progress_pat = re.compile(r'(\d+)/(\d+)\s+complete')
        spotdl_status_pat = re.compile(r'(.*):\s+(Downloading|Embedding metadata|Done|Searching|Converting)')

        try:
            env = os.environ.copy()
            if client_id and client_secret:
                env["SPOTIPY_CLIENT_ID"] = client_id
                env["SPOTIPY_CLIENT_SECRET"] = client_secret
                self.log("[Sistema] Utilizando credenciales de Spotify configuradas.\n")
            elif is_spotify:
                # Warning for playlist downloads if credentials are missing
                if "playlist" in url.lower() or "album" in url.lower() or "artist" in url.lower():
                    self.log("[ADVERTENCIA] Ha pegado una lista de Spotify sin credenciales API.\n")
                    self.log("[ADVERTENCIA] La API pública sin credenciales de spotDL puede fallar.\n")
                    self.log("[ADVERTENCIA] Se recomienda registrar sus credenciales en la barra lateral.\n\n")

            ffmpeg_path = self.get_ffmpeg_path()
            if not ffmpeg_path:
                self.log("[Sistema] ALERTA: FFmpeg no fue detectado en el sistema.\n")
                self.log("[Sistema] La conversión de audio a la máxima calidad podría fallar.\n")
                self.log("[Sistema] Por favor, haga clic en 'Instalar FFmpeg' en el panel lateral antes de continuar.\n\n")

            format_val = self.format_option.get()
            bitrate_rev_map = {
                "320kbps (Máxima)": "320k",
                "256kbps (Alta)": "256k",
                "192kbps (Estándar)": "192k",
                "Original (Sin Re-codificar)": "disable"
            }
            bitrate_val = bitrate_rev_map.get(self.bitrate_option.get(), "320k")

            if is_spotify:
                self.log("[Descarga] Iniciando motor spotDL...\n")
                cmd = get_sys_cmd("--run-spotdl") + [
                    "download", url,
                    "--format", format_val,
                    "--bitrate", bitrate_val,
                    "--simple-tui"
                ]
            else:
                self.log("[Descarga] Iniciando motor yt-dlp...\n")
                cmd = get_sys_cmd("--run-ytdlp") + [
                    url,
                    "-x", "--audio-format", format_val,
                    "--audio-quality", "320K" if bitrate_val == "320k" else "0" if bitrate_val == "disable" else bitrate_val,
                    "--yes-playlist",
                    "--embed-metadata",
                    "--embed-thumbnail",
                    "--newline",
                    "-o", os.path.join(save_dir, "%(title)s.%(ext)s")
                ]
                if ffmpeg_path:
                    cmd.extend(["--ffmpeg-location", ffmpeg_path])

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=save_dir,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Read stdout line by line and update GUI
            while True:
                if not self.current_process:
                    break
                line = self.current_process.stdout.readline()
                if not line:
                    break
                
                # Print raw log to textbox
                self.log(line)
                
                # Parse progress data
                if is_spotify:
                    # Parse spotdl logs
                    status_match = spotdl_status_pat.search(line)
                    if status_match:
                        song, status = status_match.groups()
                        self.progress_label.configure(text=f"Estado: {status} -> {song.strip()}")
                        
                    prog_match = spotdl_progress_pat.search(line)
                    if prog_match:
                        current, total = prog_match.groups()
                        try:
                            ratio = float(current) / float(total)
                            self.progress_bar.set(ratio)
                            self.progress_label.configure(text=f"Estado: Procesando playlist ({current}/{total} completado)")
                        except ValueError:
                            pass
                else:
                    # Parse yt-dlp logs
                    dest_match = ytdl_dest_pat.search(line)
                    if dest_match:
                        filepath = dest_match.group(1)
                        filename = os.path.basename(filepath)
                        self.progress_label.configure(text=f"Descargando: {filename}")
                        
                    prog_match = ytdl_progress_pat.search(line)
                    if prog_match:
                        pct, size, speed, eta = prog_match.groups()
                        try:
                            ratio = float(pct) / 100.0
                            self.progress_bar.set(ratio)
                            self.progress_label.configure(
                                text=f"Descargando... {pct}% de {size} | Vel: {speed} | Restante: {eta}"
                            )
                        except ValueError:
                            pass

            if self.current_process:
                exit_code = self.current_process.wait()
                if exit_code == 0:
                    self.progress_bar.set(1.0)
                    self.finish_download_state("Descarga completada con éxito!")
                else:
                    self.finish_download_state(f"Error durante la descarga (código de salida {exit_code}).")
            
        except Exception as e:
            self.log(f"\n[Error] Ocurrió una excepción en el hilo de descarga: {e}\n")
            self.finish_download_state("Descarga finalizada con errores.")

if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
