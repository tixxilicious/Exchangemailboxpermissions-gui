#!/usr/bin/env python3
"""
Exchange Online - Postfachberechtigungen GUI
Erstellt für Kaulich IT Systems GmbH

Ermöglicht das Hinzufügen und Entfernen von Vollzugriff und "Senden als" Berechtigungen
über eine persistente PowerShell-Session.

Voraussetzungen:
- Windows mit PowerShell
- ExchangeOnlineManagement Modul installiert
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import json
import queue
from datetime import datetime


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
        """
        Führt Befehl aus und wartet auf Ergebnis.
        Verwendet einen Marker um das Ende der Ausgabe zu erkennen.
        """
        if not self.process or self.process.poll() is not None:
            return False, "", "PowerShell-Session nicht aktiv"
        
        # Queue leeren
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except:
                break
        
        # Eindeutiger End-Marker
        end_marker = f"###END_{id(command)}###"
        
        # Befehl mit Error-Handling und End-Marker
        wrapped_command = f"""
try {{
    {command}
}} catch {{
    Write-Error $_.Exception.Message
}}
Write-Output "{end_marker}"
"""
        self._send_command(wrapped_command)
        
        # Auf Ausgabe warten
        output_lines = []
        import time
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                return False, "", "Timeout"
            
            try:
                line = self.output_queue.get(timeout=0.5)
                if end_marker in line:
                    break
                output_lines.append(line.rstrip())
            except queue.Empty:
                continue
        
        output = "\n".join(output_lines)
        
        # Prüfen ob Fehler aufgetreten
        has_error = any("Error" in line or "Fehler" in line or "Exception" in line 
                       for line in output_lines if line.strip())
        
        return not has_error, output, output if has_error else ""
    
    def stop(self):
        """PowerShell-Session beenden"""
        if self.process:
            try:
                self._send_command("exit")
                self.process.terminate()
            except:
                pass
            self.process = None


class ExchangePermissionsGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Exchange Online - Postfachberechtigungen")
        self.root.geometry("550x580")
        self.root.resizable(False, False)
        
        # PowerShell Session
        self.ps = PowerShellSession()
        self.ps.start()
        
        # Verbindungsstatus
        self.connected = False
        self.mailboxes = []
        
        self.create_widgets()
        self.log("GUI gestartet - bereit für Verbindung")
    
    def create_widgets(self):
        # Hauptframe mit Padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === Verbindung ===
        conn_frame = ttk.LabelFrame(main_frame, text="Exchange Online Verbindung", padding="10")
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(conn_frame, text="Admin-UPN:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.admin_entry = ttk.Entry(conn_frame, width=35)
        self.admin_entry.grid(row=0, column=1, padx=(0, 10))
        
        self.connect_btn = ttk.Button(conn_frame, text="Verbinden", command=self.connect)
        self.connect_btn.grid(row=0, column=2)
        
        # === Postfächer ===
        mailbox_frame = ttk.LabelFrame(main_frame, text="Postfächer", padding="10")
        mailbox_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(mailbox_frame, text="Ziel-Postfach:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.mailbox_combo = ttk.Combobox(mailbox_frame, width=42, state="disabled")
        self.mailbox_combo.grid(row=0, column=1, sticky=tk.W)
        self.mailbox_combo.set("-- Erst verbinden --")
        
        hint_label = ttk.Label(mailbox_frame, text="(Das Postfach, auf das zugegriffen werden soll)", 
                               foreground="gray")
        hint_label.grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(mailbox_frame, text="Benutzer:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        self.user_combo = ttk.Combobox(mailbox_frame, width=42, state="disabled")
        self.user_combo.grid(row=2, column=1, sticky=tk.W, pady=(10, 0))
        self.user_combo.set("-- Erst verbinden --")
        
        # Refresh Button
        self.refresh_btn = ttk.Button(mailbox_frame, text="↻", width=3, command=self.load_mailboxes, state=tk.DISABLED)
        self.refresh_btn.grid(row=0, column=2, padx=(5, 0))
        
        # Suchfeld für schnelles Filtern
        ttk.Label(mailbox_frame, text="Suche:").grid(row=3, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        self.search_entry = ttk.Entry(mailbox_frame, width=45)
        self.search_entry.grid(row=3, column=1, sticky=tk.W, pady=(10, 0), columnspan=2)
        self.search_entry.bind('<KeyRelease>', self.filter_mailboxes)
        
        # === Berechtigungen ===
        perm_frame = ttk.LabelFrame(main_frame, text="Berechtigungen", padding="10")
        perm_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.fullaccess_var = tk.BooleanVar(value=True)
        self.fullaccess_cb = ttk.Checkbutton(perm_frame, text="Vollzugriff (FullAccess)", 
                                              variable=self.fullaccess_var,
                                              command=self.toggle_automapping)
        self.fullaccess_cb.grid(row=0, column=0, sticky=tk.W)
        
        self.automapping_var = tk.BooleanVar(value=True)
        self.automapping_cb = ttk.Checkbutton(perm_frame, text="AutoMapping aktivieren", 
                                               variable=self.automapping_var)
        self.automapping_cb.grid(row=0, column=1, sticky=tk.W, padx=(30, 0))
        
        self.sendas_var = tk.BooleanVar(value=True)
        self.sendas_cb = ttk.Checkbutton(perm_frame, text="Senden als (SendAs)", 
                                          variable=self.sendas_var)
        self.sendas_cb.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        # === Aktionen ===
        action_frame = ttk.LabelFrame(main_frame, text="Aktionen", padding="10")
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_frame = ttk.Frame(action_frame)
        btn_frame.pack(fill=tk.X)
        
        self.add_btn = ttk.Button(btn_frame, text="✓ Berechtigungen hinzufügen", 
                                   command=self.add_permissions)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.remove_btn = ttk.Button(btn_frame, text="✗ Berechtigungen entfernen", 
                                      command=self.remove_permissions)
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.disconnect_btn = ttk.Button(btn_frame, text="Trennen", command=self.disconnect)
        self.disconnect_btn.pack(side=tk.RIGHT)
        
        # === Protokoll ===
        log_frame = ttk.LabelFrame(main_frame, text="Protokoll", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, height=8, state=tk.DISABLED, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def log(self, message):
        """Nachricht ins Protokoll schreiben"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def toggle_automapping(self):
        """AutoMapping Checkbox aktivieren/deaktivieren basierend auf FullAccess"""
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
        
        self.log("Verbinde zu Exchange Online...")
        self.connect_btn.configure(state=tk.DISABLED)
        self.root.update()
        
        def do_connect():
            cmd = f'Connect-ExchangeOnline -UserPrincipalName "{admin}" -ShowBanner:$false'
            success, stdout, stderr = self.ps.execute(cmd, timeout=180)
            self.root.after(0, lambda: self.connect_callback(success, stderr))
        
        thread = threading.Thread(target=do_connect)
        thread.start()
    
    def connect_callback(self, success, error):
        """Callback nach Verbindungsversuch"""
        self.connect_btn.configure(state=tk.NORMAL)
        
        if success:
            self.connected = True
            self.connect_btn.configure(text="✓ Verbunden")
            self.refresh_btn.configure(state=tk.NORMAL)
            self.log("Verbindung hergestellt!")
            messagebox.showinfo("Verbunden", "Erfolgreich mit Exchange Online verbunden!\n\nPostfächer werden jetzt geladen...")
            self.load_mailboxes()
        else:
            self.log(f"FEHLER: {error}")
            messagebox.showerror("Fehler", f"Verbindung fehlgeschlagen:\n{error}")
    
    def load_mailboxes(self):
        """Alle Postfächer von Exchange Online laden"""
        self.log("Lade Postfächer...")
        self.refresh_btn.configure(state=tk.DISABLED)
        self.mailbox_combo.set("Lade...")
        self.user_combo.set("Lade...")
        
        def do_load():
            cmd = 'Get-Mailbox -ResultSize Unlimited | Select-Object DisplayName, PrimarySmtpAddress | ConvertTo-Json -Compress'
            success, stdout, stderr = self.ps.execute(cmd, timeout=120)
            self.root.after(0, lambda: self.load_mailboxes_callback(success, stdout, stderr))
        
        thread = threading.Thread(target=do_load)
        thread.start()
    
    def load_mailboxes_callback(self, success, stdout, stderr):
        """Callback nach Laden der Postfächer"""
        self.refresh_btn.configure(state=tk.NORMAL)
        
        if success and stdout.strip():
            try:
                # JSON aus Output extrahieren (kann mehrzeilig sein)
                json_start = stdout.find('[')
                json_start_obj = stdout.find('{')
                
                if json_start == -1 and json_start_obj == -1:
                    raise ValueError("Kein JSON gefunden")
                
                if json_start == -1 or (json_start_obj != -1 and json_start_obj < json_start):
                    json_start = json_start_obj
                
                json_str = stdout[json_start:]
                data = json.loads(json_str)
                
                if isinstance(data, dict):
                    data = [data]
                
                self.mailboxes = []
                for mb in data:
                    display = mb.get('DisplayName', '')
                    email = mb.get('PrimarySmtpAddress', '')
                    if email:
                        self.mailboxes.append(f"{display} <{email}>")
                
                self.mailboxes.sort()
                
                self.mailbox_combo.configure(values=self.mailboxes, state="normal")
                self.user_combo.configure(values=self.mailboxes, state="normal")
                self.mailbox_combo.set("")
                self.user_combo.set("")
                
                self.log(f"{len(self.mailboxes)} Postfächer geladen")
                
            except (json.JSONDecodeError, ValueError) as e:
                self.log(f"FEHLER beim Parsen: {e}")
                self.log(f"Output war: {stdout[:200]}...")
                self.mailbox_combo.set("-- Fehler --")
                self.user_combo.set("-- Fehler --")
        else:
            self.log(f"FEHLER: {stderr}")
            self.mailbox_combo.set("-- Fehler --")
            self.user_combo.set("-- Fehler --")
    
    def filter_mailboxes(self, event=None):
        """Postfächer nach Suchbegriff filtern"""
        search_term = self.search_entry.get().lower()
        
        if not search_term:
            filtered = self.mailboxes
        else:
            filtered = [mb for mb in self.mailboxes if search_term in mb.lower()]
        
        self.mailbox_combo.configure(values=filtered)
        self.user_combo.configure(values=filtered)
    
    def add_permissions(self):
        """Berechtigungen hinzufügen"""
        if not self.validate_inputs():
            return
        
        mailbox = self.get_email_from_selection(self.mailbox_combo.get())
        user = self.get_email_from_selection(self.user_combo.get())
        
        msg = f"Folgende Berechtigungen hinzufügen?\n\n"
        msg += f"Postfach: {mailbox}\nBenutzer: {user}\n\n"
        msg += f"Vollzugriff: {'Ja' if self.fullaccess_var.get() else 'Nein'}\n"
        msg += f"Senden als: {'Ja' if self.sendas_var.get() else 'Nein'}"
        
        if not messagebox.askyesno("Bestätigung", msg):
            return
        
        self.set_buttons_state(tk.DISABLED)
        
        def do_add():
            errors = []
            
            if self.fullaccess_var.get():
                self.root.after(0, lambda: self.log("Füge Vollzugriff hinzu..."))
                automapping = "$true" if self.automapping_var.get() else "$false"
                cmd = f'Add-MailboxPermission -Identity "{mailbox}" -User "{user}" -AccessRights FullAccess -AutoMapping {automapping}'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("Vollzugriff erfolgreich hinzugefügt!"))
                else:
                    errors.append(f"Vollzugriff: {stderr}")
            
            if self.sendas_var.get():
                self.root.after(0, lambda: self.log("Füge 'Senden als' hinzu..."))
                cmd = f'Add-RecipientPermission -Identity "{mailbox}" -Trustee "{user}" -AccessRights SendAs -Confirm:$false'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("'Senden als' erfolgreich hinzugefügt!"))
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
                self.log(f"FEHLER: {error}")
            messagebox.showerror("Fehler", "Einige Berechtigungen konnten nicht hinzugefügt werden.\nSiehe Protokoll für Details.")
        else:
            messagebox.showinfo("Erfolg", "Berechtigungen wurden erfolgreich hinzugefügt!")
    
    def remove_permissions(self):
        """Berechtigungen entfernen"""
        if not self.validate_inputs():
            return
        
        mailbox = self.get_email_from_selection(self.mailbox_combo.get())
        user = self.get_email_from_selection(self.user_combo.get())
        
        msg = f"Folgende Berechtigungen ENTFERNEN?\n\n"
        msg += f"Postfach: {mailbox}\nBenutzer: {user}\n\n"
        msg += f"Vollzugriff: {'Ja' if self.fullaccess_var.get() else 'Nein'}\n"
        msg += f"Senden als: {'Ja' if self.sendas_var.get() else 'Nein'}\n\n"
        msg += "Diese Aktion kann nicht rückgängig gemacht werden!"
        
        if not messagebox.askyesno("Warnung", msg, icon="warning"):
            return
        
        self.set_buttons_state(tk.DISABLED)
        
        def do_remove():
            errors = []
            
            if self.fullaccess_var.get():
                self.root.after(0, lambda: self.log("Entferne Vollzugriff..."))
                cmd = f'Remove-MailboxPermission -Identity "{mailbox}" -User "{user}" -AccessRights FullAccess -Confirm:$false'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("Vollzugriff erfolgreich entfernt!"))
                else:
                    errors.append(f"Vollzugriff: {stderr}")
            
            if self.sendas_var.get():
                self.root.after(0, lambda: self.log("Entferne 'Senden als'..."))
                cmd = f'Remove-RecipientPermission -Identity "{mailbox}" -Trustee "{user}" -AccessRights SendAs -Confirm:$false'
                success, _, stderr = self.ps.execute(cmd)
                if success:
                    self.root.after(0, lambda: self.log("'Senden als' erfolgreich entfernt!"))
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
                self.log(f"FEHLER: {error}")
            messagebox.showerror("Fehler", "Einige Berechtigungen konnten nicht entfernt werden.\nSiehe Protokoll für Details.")
        else:
            messagebox.showinfo("Erfolg", "Berechtigungen wurden erfolgreich entfernt!")
    
    def disconnect(self):
        """Verbindung trennen"""
        self.log("Trenne Verbindung...")
        self.ps.execute("Disconnect-ExchangeOnline -Confirm:$false", timeout=30)
        self.connected = False
        self.mailboxes = []
        self.connect_btn.configure(text="Verbinden")
        self.mailbox_combo.configure(values=[], state="disabled")
        self.user_combo.configure(values=[], state="disabled")
        self.mailbox_combo.set("-- Erst verbinden --")
        self.user_combo.set("-- Erst verbinden --")
        self.refresh_btn.configure(state=tk.DISABLED)
        self.search_entry.delete(0, tk.END)
        self.log("Verbindung getrennt.")
    
    def set_buttons_state(self, state):
        """Alle Aktions-Buttons aktivieren/deaktivieren"""
        self.add_btn.configure(state=state)
        self.remove_btn.configure(state=state)
        self.connect_btn.configure(state=state)
        self.disconnect_btn.configure(state=state)
    
    def cleanup(self):
        """Aufräumen beim Beenden"""
        try:
            self.ps.execute("Disconnect-ExchangeOnline -Confirm:$false", timeout=10)
        except:
            pass
        self.ps.stop()


def main():
    root = tk.Tk()
    
    style = ttk.Style()
    style.configure("TButton", padding=5)
    style.configure("TEntry", padding=3)
    
    app = ExchangePermissionsGUI(root)
    
    def on_closing():
        app.cleanup()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()