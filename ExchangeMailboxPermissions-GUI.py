#!/usr/bin/env python3
"""
Exchange Online - Postfachberechtigungen GUI v2.1
Erstellt für Kaulich IT Systems GmbH

Features:
- Modernes farbiges Design
- Filterung nach Postfach-Typ (User/Shared/Beide)
- Anzeige des Postfach-Typs in der Liste
- Sichere Session-Verwaltung (kein dauerhaftes Login)
- Automatische Prüfung & Installation von ExchangeOnlineManagement

Voraussetzungen:
- Windows mit PowerShell
- ExchangeOnlineManagement Modul wird automatisch installiert falls fehlend
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import json
import queue
from datetime import datetime


# ============================================================
# FARBSCHEMA
# ============================================================
COLORS = {
    'bg_dark': '#1a1a2e',           # Dunkler Hintergrund
    'bg_medium': '#16213e',          # Mittlerer Hintergrund
    'bg_light': '#0f3460',           # Heller Hintergrund (Frames)
    'accent': '#e94560',             # Akzentfarbe (Rot/Pink)
    'accent_hover': '#ff6b6b',       # Hover-Farbe
    'success': '#00bf63',            # Erfolg (Grün)
    'warning': '#ffc107',            # Warnung (Gelb)
    'error': '#dc3545',              # Fehler (Rot)
    'text_primary': '#ffffff',       # Primärer Text (Weiß)
    'text_secondary': '#a0a0a0',     # Sekundärer Text (Grau)
    'text_muted': '#6c757d',         # Gedämpfter Text
    'entry_bg': '#2d2d44',           # Eingabefeld Hintergrund
    'entry_fg': '#ffffff',           # Eingabefeld Text
    'button_bg': '#e94560',          # Button Hintergrund
    'button_fg': '#ffffff',          # Button Text
    'shared_badge': '#9b59b6',       # Shared Mailbox Badge (Lila)
    'user_badge': '#3498db',         # User Mailbox Badge (Blau)
}


class PowerShellSession:
    """Persistente PowerShell-Session für Exchange Online"""
    
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.connected = False
    
    def start(self):
        """PowerShell-Prozess starten"""
        if self.process is not None:
            return
        
        self.process = subprocess.Popen(
            ["powershell", "-NoLogo", "-NoExit", "-Command", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )
        
        # Output-Reader Thread starten
        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()
        
        # UTF-8 Output setzen
        self._send_command('[Console]::OutputEncoding = [System.Text.Encoding]::UTF8')
    
    def _read_output(self):
        """Liest kontinuierlich Output vom PowerShell-Prozess"""
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if line:
                    self.output_queue.put(line)
            except:
                break
    
    def _send_command(self, command):
        """Sendet Befehl an PowerShell"""
        if self.process and self.process.poll() is None:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
    
    def execute(self, command, timeout=120):
        """Führt Befehl aus und wartet auf Ergebnis."""
        if not self.process or self.process.poll() is not None:
            return False, "", "PowerShell-Session nicht aktiv"
        
        # Queue leeren
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except:
                break
        
        # Eindeutiger End-Marker
        import time
        end_marker = f"###END_{int(time.time() * 1000)}###"
        error_marker = f"###ERROR_{int(time.time() * 1000)}###"
        
        # Befehl mit Error-Handling und End-Marker
        # Fehler werden separat markiert, damit wir sie sauber erkennen
        wrapped_command = f"""
try {{
    {command}
}} catch {{
    Write-Output "{error_marker}$($_.Exception.Message)"
}}
Write-Output "{end_marker}"
"""
        self._send_command(wrapped_command)
        
        # Auf Ausgabe warten
        output_lines = []
        error_lines = []
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                return False, "", "Timeout - Befehl hat zu lange gedauert"
            
            try:
                line = self.output_queue.get(timeout=0.5)
                stripped = line.rstrip()
                
                if end_marker in stripped:
                    break
                elif error_marker in stripped:
                    # Fehlermeldung extrahieren (nach dem Marker)
                    error_msg = stripped.split(error_marker, 1)[1] if error_marker in stripped else stripped
                    error_lines.append(error_msg)
                else:
                    output_lines.append(stripped)
            except queue.Empty:
                continue
        
        output = "\n".join(output_lines)
        errors = "\n".join(error_lines)
        
        if error_lines:
            return False, output, errors
        
        return True, output, ""
    
    def stop(self):
        """PowerShell-Session beenden"""
        if self.process:
            try:
                self._send_command("exit")
                self.process.terminate()
            except:
                pass
            self.process = None


class ModernButton(tk.Canvas):
    """Moderner farbiger Button mit Hover-Effekt"""
    
    def __init__(self, parent, text, command=None, bg=COLORS['button_bg'], 
                 fg=COLORS['button_fg'], width=180, height=36, **kwargs):
        super().__init__(parent, width=width, height=height, 
                        bg=parent.cget('bg'), highlightthickness=0, **kwargs)
        
        self.command = command
        self.bg_color = bg
        self.fg_color = fg
        self.hover_color = self._lighten_color(bg)
        self.text = text
        self.width = width
        self.height = height
        self.enabled = True
        
        self._draw_button(self.bg_color)
        
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<Button-1>', self._on_click)
    
    def _lighten_color(self, color):
        """Farbe aufhellen für Hover-Effekt"""
        try:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            r = min(255, r + 30)
            g = min(255, g + 30)
            b = min(255, b + 30)
            return f'#{r:02x}{g:02x}{b:02x}'
        except:
            return color
    
    def _draw_button(self, color):
        """Button zeichnen"""
        self.delete('all')
        radius = 8
        self.create_arc(0, 0, radius*2, radius*2, start=90, extent=90, 
                       fill=color, outline=color)
        self.create_arc(self.width-radius*2, 0, self.width, radius*2, 
                       start=0, extent=90, fill=color, outline=color)
        self.create_arc(0, self.height-radius*2, radius*2, self.height, 
                       start=180, extent=90, fill=color, outline=color)
        self.create_arc(self.width-radius*2, self.height-radius*2, 
                       self.width, self.height, start=270, extent=90, 
                       fill=color, outline=color)
        self.create_rectangle(radius, 0, self.width-radius, self.height, 
                             fill=color, outline=color)
        self.create_rectangle(0, radius, self.width, self.height-radius, 
                             fill=color, outline=color)
        text_color = self.fg_color if self.enabled else COLORS['text_muted']
        self.create_text(self.width/2, self.height/2, text=self.text, 
                        fill=text_color, font=('Segoe UI', 10, 'bold'))
    
    def _on_enter(self, event):
        if self.enabled:
            self._draw_button(self.hover_color)
    
    def _on_leave(self, event):
        self._draw_button(self.bg_color if self.enabled else '#555555')
    
    def _on_click(self, event):
        if self.enabled and self.command:
            self.command()
    
    def configure(self, **kwargs):
        if 'state' in kwargs:
            self.enabled = kwargs['state'] != tk.DISABLED
            self._draw_button(self.bg_color if self.enabled else '#555555')
        if 'text' in kwargs:
            self.text = kwargs['text']
            self._draw_button(self.bg_color if self.enabled else '#555555')
        if 'bg' in kwargs:
            self.bg_color = kwargs['bg']
            self.hover_color = self._lighten_color(kwargs['bg'])
            self._draw_button(self.bg_color)


class ExchangePermissionsGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Exchange Online - Postfachberechtigungen v2.1")
        self.root.geometry("620x750")
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS['bg_dark'])
        
        # PowerShell Session
        self.ps = PowerShellSession()
        self.ps.start()
        
        # Verbindungsstatus
        self.connected = False
        self.all_mailboxes = []
        self.filtered_mailboxes = []
        
        # Filter-Einstellung
        self.mailbox_filter = tk.StringVar(value="all")
        
        self.create_widgets()
        self.log("🚀 GUI gestartet - prüfe Voraussetzungen...", COLORS['success'])
        
        # Automatisch Modul prüfen beim Start
        self.root.after(500, self.check_and_install_module)
    
    def create_widgets(self):
        # Hauptframe
        main_frame = tk.Frame(self.root, bg=COLORS['bg_dark'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # === HEADER ===
        header_frame = tk.Frame(main_frame, bg=COLORS['bg_dark'])
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        title_label = tk.Label(header_frame, text="📧 Exchange Online", 
                              font=('Segoe UI', 20, 'bold'),
                              fg=COLORS['accent'], bg=COLORS['bg_dark'])
        title_label.pack()
        
        subtitle_label = tk.Label(header_frame, text="Postfachberechtigungen verwalten",
                                 font=('Segoe UI', 11),
                                 fg=COLORS['text_secondary'], bg=COLORS['bg_dark'])
        subtitle_label.pack()
        
        # === VERBINDUNG ===
        conn_frame = self.create_section_frame(main_frame, "🔐 Verbindung")
        
        conn_inner = tk.Frame(conn_frame, bg=COLORS['bg_light'])
        conn_inner.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(conn_inner, text="Admin-UPN:", font=('Segoe UI', 10),
                fg=COLORS['text_primary'], bg=COLORS['bg_light']).grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        self.admin_entry = tk.Entry(conn_inner, width=35, font=('Segoe UI', 10),
                                   bg=COLORS['entry_bg'], fg=COLORS['entry_fg'],
                                   insertbackground=COLORS['text_primary'],
                                   relief=tk.FLAT, highlightthickness=1,
                                   highlightbackground=COLORS['bg_medium'],
                                   highlightcolor=COLORS['accent'])
        self.admin_entry.grid(row=0, column=1, padx=(0, 10), ipady=5)
        
        self.connect_btn = ModernButton(conn_inner, "🔌 Verbinden", 
                                        command=self.connect, width=130)
        self.connect_btn.grid(row=0, column=2)
        
        # Status-Label für Modulprüfung
        self.module_status_label = tk.Label(conn_frame, text="⏳ Prüfe ExchangeOnlineManagement Modul...",
                font=('Segoe UI', 9), fg=COLORS['warning'], bg=COLORS['bg_light'])
        self.module_status_label.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # Hinweis: Kein dauerhaftes Login
        hint_frame = tk.Frame(conn_frame, bg=COLORS['bg_light'])
        hint_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(hint_frame, text="⚠️ Session wird beim Beenden automatisch getrennt (kein dauerhaftes Login)",
                font=('Segoe UI', 9), fg=COLORS['warning'], bg=COLORS['bg_light']).pack(anchor=tk.W)
        
        # === POSTFÄCHER ===
        mailbox_frame = self.create_section_frame(main_frame, "📬 Postfächer")
        
        # Filter-Optionen
        filter_frame = tk.Frame(mailbox_frame, bg=COLORS['bg_light'])
        filter_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        tk.Label(filter_frame, text="Filter:", font=('Segoe UI', 10, 'bold'),
                fg=COLORS['text_primary'], bg=COLORS['bg_light']).pack(side=tk.LEFT, padx=(0, 10))
        
        filter_options = [
            ("Alle", "all"),
            ("👤 Nur Benutzer", "user"),
            ("👥 Nur Freigegebene", "shared")
        ]
        
        for text, value in filter_options:
            rb = tk.Radiobutton(filter_frame, text=text, variable=self.mailbox_filter,
                               value=value, font=('Segoe UI', 9),
                               fg=COLORS['text_primary'], bg=COLORS['bg_light'],
                               selectcolor=COLORS['bg_medium'],
                               activebackground=COLORS['bg_light'],
                               activeforeground=COLORS['accent'],
                               command=self.apply_filter)
            rb.pack(side=tk.LEFT, padx=(0, 15))
        
        # Ziel-Postfach
        mailbox_inner = tk.Frame(mailbox_frame, bg=COLORS['bg_light'])
        mailbox_inner.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(mailbox_inner, text="Ziel-Postfach:", font=('Segoe UI', 10),
                fg=COLORS['text_primary'], bg=COLORS['bg_light']).grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        self.mailbox_combo = ttk.Combobox(mailbox_inner, width=48, state="disabled",
                                          font=('Segoe UI', 9))
        self.mailbox_combo.grid(row=0, column=1, padx=(0, 5))
        self.mailbox_combo.set("-- Erst verbinden --")
        
        self.refresh_btn = ModernButton(mailbox_inner, "🔄", command=self.load_mailboxes,
                                        width=40, height=30, bg=COLORS['bg_medium'])
        self.refresh_btn.grid(row=0, column=2)
        self.refresh_btn.configure(state=tk.DISABLED)
        
        tk.Label(mailbox_inner, text="(Das Postfach, auf das zugegriffen werden soll)",
                font=('Segoe UI', 9), fg=COLORS['text_muted'], 
                bg=COLORS['bg_light']).grid(row=1, column=1, sticky=tk.W, pady=(2, 0))
        
        # Benutzer
        tk.Label(mailbox_inner, text="Benutzer:", font=('Segoe UI', 10),
                fg=COLORS['text_primary'], bg=COLORS['bg_light']).grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        
        self.user_combo = ttk.Combobox(mailbox_inner, width=48, state="disabled",
                                       font=('Segoe UI', 9))
        self.user_combo.grid(row=2, column=1, pady=(10, 0), padx=(0, 5))
        self.user_combo.set("-- Erst verbinden --")
        
        tk.Label(mailbox_inner, text="(Der Benutzer, der Zugriff erhalten/verlieren soll)",
                font=('Segoe UI', 9), fg=COLORS['text_muted'],
                bg=COLORS['bg_light']).grid(row=3, column=1, sticky=tk.W, pady=(2, 0))
        
        # Suche
        search_frame = tk.Frame(mailbox_frame, bg=COLORS['bg_light'])
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 10))
        
        tk.Label(search_frame, text="🔍 Suche:", font=('Segoe UI', 10),
                fg=COLORS['text_primary'], bg=COLORS['bg_light']).pack(side=tk.LEFT, padx=(0, 10))
        
        self.search_entry = tk.Entry(search_frame, width=50, font=('Segoe UI', 10),
                                    bg=COLORS['entry_bg'], fg=COLORS['entry_fg'],
                                    insertbackground=COLORS['text_primary'],
                                    relief=tk.FLAT, highlightthickness=1,
                                    highlightbackground=COLORS['bg_medium'],
                                    highlightcolor=COLORS['accent'])
        self.search_entry.pack(side=tk.LEFT, ipady=5)
        self.search_entry.bind('<KeyRelease>', self.filter_mailboxes)
        
        # === BERECHTIGUNGEN ===
        perm_frame = self.create_section_frame(main_frame, "🔑 Berechtigungen")
        
        perm_inner = tk.Frame(perm_frame, bg=COLORS['bg_light'])
        perm_inner.pack(fill=tk.X, padx=10, pady=10)
        
        # Vollzugriff
        self.fullaccess_var = tk.BooleanVar(value=True)
        self.fullaccess_cb = tk.Checkbutton(perm_inner, text="📂 Vollzugriff (FullAccess)",
                                            variable=self.fullaccess_var,
                                            font=('Segoe UI', 10),
                                            fg=COLORS['text_primary'], bg=COLORS['bg_light'],
                                            selectcolor=COLORS['bg_medium'],
                                            activebackground=COLORS['bg_light'],
                                            activeforeground=COLORS['accent'],
                                            command=self.toggle_automapping)
        self.fullaccess_cb.grid(row=0, column=0, sticky=tk.W)
        
        # AutoMapping
        self.automapping_var = tk.BooleanVar(value=True)
        self.automapping_cb = tk.Checkbutton(perm_inner, text="🔗 AutoMapping aktivieren",
                                             variable=self.automapping_var,
                                             font=('Segoe UI', 10),
                                             fg=COLORS['text_primary'], bg=COLORS['bg_light'],
                                             selectcolor=COLORS['bg_medium'],
                                             activebackground=COLORS['bg_light'],
                                             activeforeground=COLORS['accent'])
        self.automapping_cb.grid(row=0, column=1, sticky=tk.W, padx=(30, 0))
        
        # Senden als
        self.sendas_var = tk.BooleanVar(value=True)
        self.sendas_cb = tk.Checkbutton(perm_inner, text="✉️ Senden als (SendAs)",
                                        variable=self.sendas_var,
                                        font=('Segoe UI', 10),
                                        fg=COLORS['text_primary'], bg=COLORS['bg_light'],
                                        selectcolor=COLORS['bg_medium'],
                                        activebackground=COLORS['bg_light'],
                                        activeforeground=COLORS['accent'])
        self.sendas_cb.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        # === AKTIONEN ===
        action_frame = self.create_section_frame(main_frame, "⚡ Aktionen")
        
        action_inner = tk.Frame(action_frame, bg=COLORS['bg_light'])
        action_inner.pack(fill=tk.X, padx=10, pady=10)
        
        self.add_btn = ModernButton(action_inner, "✅ Hinzufügen",
                                    command=self.add_permissions,
                                    bg=COLORS['success'], width=150)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.remove_btn = ModernButton(action_inner, "❌ Entfernen",
                                       command=self.remove_permissions,
                                       bg=COLORS['error'], width=150)
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.disconnect_btn = ModernButton(action_inner, "🔌 Trennen",
                                           command=self.disconnect,
                                           bg=COLORS['bg_medium'], width=120)
        self.disconnect_btn.pack(side=tk.RIGHT)
        
        # === PROTOKOLL ===
        log_frame = self.create_section_frame(main_frame, "📋 Protokoll")
        
        log_inner = tk.Frame(log_frame, bg=COLORS['bg_light'])
        log_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = tk.Text(log_inner, height=8, font=('Consolas', 9),
                               bg=COLORS['entry_bg'], fg=COLORS['text_primary'],
                               relief=tk.FLAT, wrap=tk.WORD,
                               highlightthickness=1,
                               highlightbackground=COLORS['bg_medium'])
        
        scrollbar = tk.Scrollbar(log_inner, orient=tk.VERTICAL, 
                                command=self.log_text.yview,
                                bg=COLORS['bg_medium'], troughcolor=COLORS['bg_dark'])
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tags für farbige Log-Einträge
        self.log_text.tag_configure('success', foreground=COLORS['success'])
        self.log_text.tag_configure('error', foreground=COLORS['error'])
        self.log_text.tag_configure('warning', foreground=COLORS['warning'])
        self.log_text.tag_configure('info', foreground=COLORS['text_primary'])
        self.log_text.tag_configure('accent', foreground=COLORS['accent'])
        
        # Combobox Styling
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TCombobox',
                       fieldbackground=COLORS['entry_bg'],
                       background=COLORS['bg_medium'],
                       foreground=COLORS['entry_fg'],
                       arrowcolor=COLORS['text_primary'])
    
    def create_section_frame(self, parent, title):
        """Erstellt einen gestylten Abschnitts-Frame"""
        container = tk.Frame(parent, bg=COLORS['bg_dark'])
        container.pack(fill=tk.X, pady=(0, 10))
        
        title_label = tk.Label(container, text=title, font=('Segoe UI', 11, 'bold'),
                              fg=COLORS['accent'], bg=COLORS['bg_dark'])
        title_label.pack(anchor=tk.W, pady=(0, 5))
        
        frame = tk.Frame(container, bg=COLORS['bg_light'],
                        highlightbackground=COLORS['bg_medium'],
                        highlightthickness=1)
        frame.pack(fill=tk.X)
        
        return frame
    
    def log(self, message, color=None):
        """Nachricht ins Protokoll schreiben"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if color == COLORS['success']:
            tag = 'success'
        elif color == COLORS['error']:
            tag = 'error'
        elif color == COLORS['warning']:
            tag = 'warning'
        elif color == COLORS['accent']:
            tag = 'accent'
        else:
            tag = 'info'
        
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] ", 'info')
        self.log_text.insert(tk.END, f"{message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    # ============================================================
    # MODUL-PRÜFUNG & INSTALLATION
    # ============================================================
    
    def check_and_install_module(self):
        """Prüft ob ExchangeOnlineManagement installiert ist und installiert es bei Bedarf"""
        self.connect_btn.configure(state=tk.DISABLED)
        self.log("🔍 Prüfe ExchangeOnlineManagement Modul...", COLORS['warning'])
        
        def do_check():
            # Prüfen ob Modul vorhanden
            check_cmd = '$m = Get-Module -ListAvailable -Name ExchangeOnlineManagement; if ($m) { Write-Output "INSTALLED:$($m.Version)" } else { Write-Output "NOT_INSTALLED" }'
            success, stdout, stderr = self.ps.execute(check_cmd, timeout=30)
            
            output = stdout.strip()
            
            if "INSTALLED:" in output:
                version = output.split("INSTALLED:")[1].strip().split("\n")[0]
                self.root.after(0, lambda: self._module_found(version))
            else:
                self.root.after(0, self._module_not_found)
        
        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()
    
    def _module_found(self, version):
        """Modul wurde gefunden"""
        self.module_status_label.configure(
            text=f"✅ ExchangeOnlineManagement v{version} installiert",
            fg=COLORS['success']
        )
        self.connect_btn.configure(state=tk.NORMAL)
        self.log(f"✅ ExchangeOnlineManagement v{version} gefunden", COLORS['success'])
        self.log("🚀 Bereit für Verbindung!", COLORS['success'])
    
    def _module_not_found(self):
        """Modul nicht gefunden - Installation anbieten"""
        self.module_status_label.configure(
            text="❌ ExchangeOnlineManagement fehlt!",
            fg=COLORS['error']
        )
        self.log("❌ ExchangeOnlineManagement Modul nicht gefunden!", COLORS['error'])
        
        install = messagebox.askyesno(
            "Modul fehlt",
            "Das PowerShell-Modul 'ExchangeOnlineManagement' ist nicht installiert.\n\n"
            "Dieses Modul wird für die Verbindung zu Exchange Online benötigt.\n\n"
            "Soll es jetzt automatisch installiert werden?\n"
            "(Benötigt ggf. Admin-Rechte)",
            icon="warning"
        )
        
        if install:
            self._install_module()
        else:
            self.log("⚠️ Installation abgebrochen. Bitte manuell installieren:", COLORS['warning'])
            self.log("   Install-Module -Name ExchangeOnlineManagement -Scope CurrentUser", COLORS['accent'])
            self.module_status_label.configure(
                text="⚠️ Modul fehlt - bitte manuell installieren",
                fg=COLORS['warning']
            )
    
    def _install_module(self):
        """ExchangeOnlineManagement Modul installieren"""
        self.log("📦 Installiere ExchangeOnlineManagement...", COLORS['warning'])
        self.log("   (Das kann 1-2 Minuten dauern)", COLORS['text_muted'])
        self.module_status_label.configure(
            text="⏳ Installiere ExchangeOnlineManagement... bitte warten",
            fg=COLORS['warning']
        )
        self.root.update()
        
        def do_install():
            # Erst NuGet Provider sicherstellen, dann Modul installieren
            install_cmd = """
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction SilentlyContinue
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser -ErrorAction SilentlyContinue | Out-Null
Install-Module -Name ExchangeOnlineManagement -Scope CurrentUser -Force -AllowClobber
$m = Get-Module -ListAvailable -Name ExchangeOnlineManagement
if ($m) { Write-Output "INSTALL_OK:$($m.Version)" } else { Write-Output "INSTALL_FAILED" }
"""
            success, stdout, stderr = self.ps.execute(install_cmd, timeout=300)
            
            output = stdout.strip()
            
            if "INSTALL_OK:" in output:
                version = output.split("INSTALL_OK:")[1].strip().split("\n")[0]
                self.root.after(0, lambda: self._install_success(version))
            else:
                error_msg = stderr if stderr else "Unbekannter Fehler bei der Installation"
                self.root.after(0, lambda: self._install_failed(error_msg))
        
        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()
    
    def _install_success(self, version):
        """Installation erfolgreich"""
        self.module_status_label.configure(
            text=f"✅ ExchangeOnlineManagement v{version} erfolgreich installiert!",
            fg=COLORS['success']
        )
        self.connect_btn.configure(state=tk.NORMAL)
        self.log(f"✅ ExchangeOnlineManagement v{version} erfolgreich installiert!", COLORS['success'])
        self.log("🚀 Bereit für Verbindung!", COLORS['success'])
        messagebox.showinfo("Erfolg", 
                           f"ExchangeOnlineManagement v{version} wurde erfolgreich installiert!\n\n"
                           "Sie können jetzt eine Verbindung herstellen.")
    
    def _install_failed(self, error):
        """Installation fehlgeschlagen"""
        self.module_status_label.configure(
            text="❌ Installation fehlgeschlagen!",
            fg=COLORS['error']
        )
        self.log(f"❌ Installation fehlgeschlagen: {error}", COLORS['error'])
        self.log("💡 Bitte manuell als Admin installieren:", COLORS['warning'])
        self.log("   Install-Module -Name ExchangeOnlineManagement -Force", COLORS['accent'])
        
        messagebox.showerror("Installation fehlgeschlagen", 
                            f"Die Installation ist fehlgeschlagen.\n\n"
                            f"Fehler: {error}\n\n"
                            "Bitte öffnen Sie PowerShell als Administrator und führen Sie aus:\n"
                            "Install-Module -Name ExchangeOnlineManagement -Force")
    
    # ============================================================
    # VERBINDUNG
    # ============================================================
    
    def toggle_automapping(self):
        """AutoMapping Checkbox aktivieren/deaktivieren"""
        if self.fullaccess_var.get():
            self.automapping_cb.configure(state=tk.NORMAL)
        else:
            self.automapping_cb.configure(state=tk.DISABLED)
    
    def validate_inputs(self):
        """Eingabefelder validieren"""
        mailbox = self.mailbox_combo.get().strip()
        user = self.user_combo.get().strip()
        
        if not mailbox or mailbox.startswith("--"):
            messagebox.showwarning("Eingabe fehlt", "Bitte Ziel-Postfach auswählen!")
            return False
        if not user or user.startswith("--"):
            messagebox.showwarning("Eingabe fehlt", "Bitte Benutzer auswählen!")
            return False
        if not self.fullaccess_var.get() and not self.sendas_var.get():
            messagebox.showwarning("Eingabe fehlt", "Bitte mindestens eine Berechtigung auswählen!")
            return False
        return True
    
    def get_email_from_selection(self, selection):
        """E-Mail-Adresse aus Dropdown-Auswahl extrahieren"""
        if '<' in selection and '>' in selection:
            return selection.split('<')[1].split('>')[0]
        return selection
    
    def connect(self):
        """Verbindung zu Exchange Online herstellen"""
        admin = self.admin_entry.get().strip()
        if not admin:
            messagebox.showwarning("Eingabe fehlt", "Bitte Admin-UPN eingeben!")
            return
        
        self.log("🔄 Verbinde zu Exchange Online...", COLORS['warning'])
        self.log("   (Browser-Fenster für Anmeldung öffnet sich...)", COLORS['text_muted'])
        self.connect_btn.configure(state=tk.DISABLED)
        self.root.update()
        
        def do_connect():
            cmd = f'Connect-ExchangeOnline -UserPrincipalName "{admin}" -ShowBanner:$false'
            success, stdout, stderr = self.ps.execute(cmd, timeout=180)
            
            # Zusätzliche Prüfung: Versuche einen einfachen Befehl auszuführen
            if success:
                verify_cmd = 'Get-OrganizationConfig | Select-Object -ExpandProperty Name'
                v_success, v_stdout, v_stderr = self.ps.execute(verify_cmd, timeout=30)
                if v_success and v_stdout.strip():
                    org_name = v_stdout.strip().split("\n")[0]
                    self.root.after(0, lambda: self.connect_callback(True, "", org_name))
                else:
                    self.root.after(0, lambda: self.connect_callback(True, "", ""))
            else:
                self.root.after(0, lambda: self.connect_callback(False, stderr, ""))
        
        thread = threading.Thread(target=do_connect)
        thread.start()
    
    def connect_callback(self, success, error, org_name=""):
        """Callback nach Verbindungsversuch"""
        self.connect_btn.configure(state=tk.NORMAL)
        
        if success:
            self.connected = True
            self.connect_btn.configure(text="✅ Verbunden", bg=COLORS['success'])
            self.refresh_btn.configure(state=tk.NORMAL)
            
            if org_name:
                self.log(f"✅ Verbunden mit: {org_name}", COLORS['success'])
            else:
                self.log("✅ Verbindung hergestellt!", COLORS['success'])
            
            messagebox.showinfo("Verbunden", 
                              "Erfolgreich mit Exchange Online verbunden!\n\n"
                              "Postfächer werden jetzt geladen...")
            self.load_mailboxes()
        else:
            self.log(f"❌ Verbindung fehlgeschlagen: {error}", COLORS['error'])
            messagebox.showerror("Fehler", f"Verbindung fehlgeschlagen:\n\n{error}")
    
    def load_mailboxes(self):
        """Alle Postfächer von Exchange Online laden"""
        self.log("📥 Lade Postfächer...", COLORS['warning'])
        self.refresh_btn.configure(state=tk.DISABLED)
        self.mailbox_combo.set("⏳ Lade...")
        self.user_combo.set("⏳ Lade...")
        
        def do_load():
            cmd = 'Get-Mailbox -ResultSize Unlimited | Select-Object DisplayName, PrimarySmtpAddress, RecipientTypeDetails | ConvertTo-Json -Compress'
            success, stdout, stderr = self.ps.execute(cmd, timeout=180)
            self.root.after(0, lambda: self.load_mailboxes_callback(success, stdout, stderr))
        
        thread = threading.Thread(target=do_load)
        thread.start()
    
    def load_mailboxes_callback(self, success, stdout, stderr):
        """Callback nach Laden der Postfächer"""
        self.refresh_btn.configure(state=tk.NORMAL)
        
        if success and stdout.strip():
            try:
                json_start = stdout.find('[')
                json_start_obj = stdout.find('{')
                
                if json_start == -1 and json_start_obj == -1:
                    raise ValueError("Kein JSON in der Ausgabe gefunden")
                
                if json_start == -1 or (json_start_obj != -1 and json_start_obj < json_start):
                    json_start = json_start_obj
                
                json_str = stdout[json_start:]
                data = json.loads(json_str)
                
                if isinstance(data, dict):
                    data = [data]
                
                self.all_mailboxes = []
                user_count = 0
                shared_count = 0
                
                for mb in data:
                    display = mb.get('DisplayName', '')
                    email = mb.get('PrimarySmtpAddress', '')
                    mb_type = mb.get('RecipientTypeDetails', 'UserMailbox')
                    
                    if email:
                        is_shared = 'Shared' in mb_type
                        
                        if is_shared:
                            prefix = "👥 [Shared]"
                            shared_count += 1
                        else:
                            prefix = "👤 [User]"
                            user_count += 1
                        
                        self.all_mailboxes.append({
                            'display': f"{prefix} {display} <{email}>",
                            'email': email,
                            'name': display,
                            'type': 'shared' if is_shared else 'user'
                        })
                
                self.all_mailboxes.sort(key=lambda x: x['display'])
                self.apply_filter()
                
                self.log(f"✅ {len(self.all_mailboxes)} Postfächer geladen "
                        f"(👤 {user_count} Benutzer, 👥 {shared_count} Freigegebene)", 
                        COLORS['success'])
                
            except (json.JSONDecodeError, ValueError) as e:
                self.log(f"❌ Fehler beim Parsen der Postfächer: {e}", COLORS['error'])
                self.mailbox_combo.set("-- Fehler --")
                self.user_combo.set("-- Fehler --")
        else:
            error_msg = stderr if stderr else "Keine Daten empfangen"
            self.log(f"❌ Fehler beim Laden: {error_msg}", COLORS['error'])
            self.mailbox_combo.set("-- Fehler --")
            self.user_combo.set("-- Fehler --")
    
    def apply_filter(self):
        """Filter auf Postfächer anwenden"""
        filter_type = self.mailbox_filter.get()
        
        if filter_type == "all":
            self.filtered_mailboxes = self.all_mailboxes
        elif filter_type == "user":
            self.filtered_mailboxes = [mb for mb in self.all_mailboxes if mb['type'] == 'user']
        elif filter_type == "shared":
            self.filtered_mailboxes = [mb for mb in self.all_mailboxes if mb['type'] == 'shared']
        
        display_list = [mb['display'] for mb in self.filtered_mailboxes]
        
        self.mailbox_combo.configure(values=display_list, state="normal")
        self.user_combo.configure(values=display_list, state="normal")
        self.mailbox_combo.set("")
        self.user_combo.set("")
        
        self.log(f"🔍 Filter: {len(self.filtered_mailboxes)} Postfächer angezeigt", COLORS['accent'])
    
    def filter_mailboxes(self, event=None):
        """Postfächer nach Suchbegriff filtern"""
        search_term = self.search_entry.get().lower()
        filter_type = self.mailbox_filter.get()
        
        if filter_type == "all":
            type_filtered = self.all_mailboxes
        elif filter_type == "user":
            type_filtered = [mb for mb in self.all_mailboxes if mb['type'] == 'user']
        else:
            type_filtered = [mb for mb in self.all_mailboxes if mb['type'] == 'shared']
        
        if search_term:
            filtered = [mb for mb in type_filtered if search_term in mb['display'].lower()]
        else:
            filtered = type_filtered
        
        display_list = [mb['display'] for mb in filtered]
        self.mailbox_combo.configure(values=display_list)
        self.user_combo.configure(values=display_list)
    
    def add_permissions(self):
        """Berechtigungen hinzufügen"""
        if not self.validate_inputs():
            return
        
        mailbox = self.get_email_from_selection(self.mailbox_combo.get())
        user = self.get_email_from_selection(self.user_combo.get())
        
        msg = f"Folgende Berechtigungen hinzufügen?\n\n"
        msg += f"📬 Postfach: {mailbox}\n👤 Benutzer: {user}\n\n"
        msg += f"📂 Vollzugriff: {'✅ Ja' if self.fullaccess_var.get() else '❌ Nein'}\n"
        if self.fullaccess_var.get():
            msg += f"🔗 AutoMapping: {'✅ Ja' if self.automapping_var.get() else '❌ Nein'}\n"
        msg += f"✉️ Senden als: {'✅ Ja' if self.sendas_var.get() else '❌ Nein'}"
        
        if not messagebox.askyesno("Bestätigung", msg):
            return
        
        self.set_buttons_state(tk.DISABLED)
        
        def do_add():
            errors = []
            
            if self.fullaccess_var.get():
                self.root.after(0, lambda: self.log("📂 Füge Vollzugriff hinzu...", COLORS['warning']))
                automapping = "$true" if self.automapping_var.get() else "$false"
                cmd = f'Add-MailboxPermission -Identity "{mailbox}" -User "{user}" -AccessRights FullAccess -AutoMapping {automapping}'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("✅ Vollzugriff erfolgreich hinzugefügt!", COLORS['success']))
                else:
                    errors.append(f"Vollzugriff: {stderr}")
            
            if self.sendas_var.get():
                self.root.after(0, lambda: self.log("✉️ Füge 'Senden als' hinzu...", COLORS['warning']))
                cmd = f'Add-RecipientPermission -Identity "{mailbox}" -Trustee "{user}" -AccessRights SendAs -Confirm:$false'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("✅ 'Senden als' erfolgreich hinzugefügt!", COLORS['success']))
                else:
                    errors.append(f"Senden als: {stderr}")
            
            self.root.after(0, lambda: self.add_callback(errors))
        
        thread = threading.Thread(target=do_add)
        thread.start()
    
    def add_callback(self, errors):
        """Callback nach Hinzufügen"""
        self.set_buttons_state(tk.NORMAL)
        
        if errors:
            for error in errors:
                self.log(f"❌ {error}", COLORS['error'])
            messagebox.showerror("Fehler", 
                               "Einige Berechtigungen konnten nicht hinzugefügt werden.\n"
                               "Siehe Protokoll für Details.")
        else:
            messagebox.showinfo("Erfolg", "✅ Berechtigungen wurden erfolgreich hinzugefügt!")
    
    def remove_permissions(self):
        """Berechtigungen entfernen"""
        if not self.validate_inputs():
            return
        
        mailbox = self.get_email_from_selection(self.mailbox_combo.get())
        user = self.get_email_from_selection(self.user_combo.get())
        
        msg = f"⚠️ Folgende Berechtigungen ENTFERNEN?\n\n"
        msg += f"📬 Postfach: {mailbox}\n👤 Benutzer: {user}\n\n"
        msg += f"📂 Vollzugriff: {'✅ Ja' if self.fullaccess_var.get() else '❌ Nein'}\n"
        msg += f"✉️ Senden als: {'✅ Ja' if self.sendas_var.get() else '❌ Nein'}\n\n"
        msg += "⚠️ Diese Aktion kann nicht rückgängig gemacht werden!"
        
        if not messagebox.askyesno("Warnung", msg, icon="warning"):
            return
        
        self.set_buttons_state(tk.DISABLED)
        
        def do_remove():
            errors = []
            
            if self.fullaccess_var.get():
                self.root.after(0, lambda: self.log("📂 Entferne Vollzugriff...", COLORS['warning']))
                cmd = f'Remove-MailboxPermission -Identity "{mailbox}" -User "{user}" -AccessRights FullAccess -Confirm:$false'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("✅ Vollzugriff erfolgreich entfernt!", COLORS['success']))
                else:
                    errors.append(f"Vollzugriff: {stderr}")
            
            if self.sendas_var.get():
                self.root.after(0, lambda: self.log("✉️ Entferne 'Senden als'...", COLORS['warning']))
                cmd = f'Remove-RecipientPermission -Identity "{mailbox}" -Trustee "{user}" -AccessRights SendAs -Confirm:$false'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("✅ 'Senden als' erfolgreich entfernt!", COLORS['success']))
                else:
                    errors.append(f"Senden als: {stderr}")
            
            self.root.after(0, lambda: self.remove_callback(errors))
        
        thread = threading.Thread(target=do_remove)
        thread.start()
    
    def remove_callback(self, errors):
        """Callback nach Entfernen"""
        self.set_buttons_state(tk.NORMAL)
        
        if errors:
            for error in errors:
                self.log(f"❌ {error}", COLORS['error'])
            messagebox.showerror("Fehler", 
                               "Einige Berechtigungen konnten nicht entfernt werden.\n"
                               "Siehe Protokoll für Details.")
        else:
            messagebox.showinfo("Erfolg", "✅ Berechtigungen wurden erfolgreich entfernt!")
    
    def disconnect(self):
        """Verbindung trennen"""
        self.log("🔌 Trenne Verbindung...", COLORS['warning'])
        self.ps.execute("Disconnect-ExchangeOnline -Confirm:$false", timeout=30)
        self.connected = False
        self.all_mailboxes = []
        self.filtered_mailboxes = []
        self.connect_btn.configure(text="🔌 Verbinden", bg=COLORS['button_bg'])
        self.mailbox_combo.configure(values=[], state="disabled")
        self.user_combo.configure(values=[], state="disabled")
        self.mailbox_combo.set("-- Erst verbinden --")
        self.user_combo.set("-- Erst verbinden --")
        self.refresh_btn.configure(state=tk.DISABLED)
        self.search_entry.delete(0, tk.END)
        self.log("✅ Verbindung getrennt.", COLORS['success'])
    
    def set_buttons_state(self, state):
        """Alle Aktions-Buttons aktivieren/deaktivieren"""
        self.add_btn.configure(state=state)
        self.remove_btn.configure(state=state)
        self.connect_btn.configure(state=state)
        self.disconnect_btn.configure(state=state)
    
    def cleanup(self):
        """Aufräumen beim Beenden - Session wird IMMER getrennt"""
        self.log("🧹 Räume auf und trenne Session...", COLORS['warning'])
        try:
            self.ps.execute("Disconnect-ExchangeOnline -Confirm:$false", timeout=10)
        except:
            pass
        self.ps.stop()


def main():
    root = tk.Tk()
    
    try:
        root.iconbitmap('exchange.ico')
    except:
        pass
    
    app = ExchangePermissionsGUI(root)
    
    def on_closing():
        if messagebox.askokcancel("Beenden", 
                                  "Programm beenden?\n\n"
                                  "Die Exchange Online Session wird automatisch getrennt."):
            app.cleanup()
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()