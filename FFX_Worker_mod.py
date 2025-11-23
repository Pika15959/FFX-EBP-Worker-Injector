import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import os
import json
import struct
import re
from Worker_Data import ebp_patcher

# --- CONSTANTS ---
WINDOW_WIDTH = 1350
WINDOW_HEIGHT = 950
NUM_ROWS = 24
CSV_FILENAME = r"Worker_Data\ebpcommands.csv"

# --- GLOBAL STORAGE ---
k = "" 

# --- OBJECT GENERATION SETTINGS ---
OBJECT_TOTAL_SIZE = 500  

# Folder Paths
BASE_DIR = "Worker_Data"
WORKER_DIR = os.path.join(BASE_DIR, "Worker")
ENTRY_DIR = os.path.join(BASE_DIR, "Entry")

# Layout Controls
OUTER_MARGIN = 45
ROW_SPACING = 0
ROW_INTERNAL_PADY = 0
ENTRY_HEIGHT_PAD = 0

class RowWidget:
    """
    Row: [Dropdown] | [xOffset] | [Text Entry] | [Command Data] | [Quick Input]
    """
    def __init__(self, parent, row_index, update_callback, focus_neighbor_callback, command_map, quick_input_data):
        self.row_index = row_index
        self.update_callback = update_callback
        self.focus_neighbor = focus_neighbor_callback
        self.command_map = command_map
        self.quick_input_map = quick_input_data['map']
        
        self.frame = tk.Frame(parent, bg="#f0f0f0")
        self.frame.pack(fill="x", pady=ROW_SPACING)
        
        # 1. Dropdown (Left)
        vals = [""] + [f"j{i:02X}" for i in range(12)]
        self.combo1 = ttk.Combobox(self.frame, values=vals, width=5, state="readonly")
        self.combo1.pack(side="left", padx=(0, 5), pady=ROW_INTERNAL_PADY)
        self.combo1.current(0)
        self.combo1.bind("<<ComboboxSelected>>", self._on_combo_change)

        # 2. Offset Display (Left)
        self.count_label = tk.Label(
            self.frame,
            text="0000",
            width=6,
            anchor="e",
            bg="#f0f0f0",
            fg="#555",
            font=("Consolas", 9)
        )
        self.count_label.pack(side="left", fill="y", padx=(0, 10), pady=ROW_INTERNAL_PADY)

        # --- RIGHT SIDE ---
        self.quick_vals = [""] + quick_input_data['labels']
        self.quick_combo = ttk.Combobox(self.frame, values=self.quick_vals, width=20, state="readonly")
        self.quick_combo.pack(side="right", padx=(5, 0), pady=ROW_INTERNAL_PADY)
        self.quick_combo.bind("<<ComboboxSelected>>", self._on_quick_select)
        
        self.cmd_result_var = tk.StringVar()
        self.cmd_label = tk.Label(
            self.frame,
            textvariable=self.cmd_result_var,
            width=25,
            anchor="w",
            bg="#e8e8e8",
            fg="#000088",
            font=("Arial", 9, "italic"),
            relief="flat"
        )
        self.cmd_label.pack(side="right", fill="y", padx=(5, 5), pady=ROW_INTERNAL_PADY)

        # --- CENTER ---
        self.text_container = tk.Frame(self.frame, bg="white", bd=0)
        self.text_container.pack(side="left", fill="x", expand=True, padx=(0, 0), pady=ROW_INTERNAL_PADY)

        self.text_var = tk.StringVar()
        self.text_var.trace_add("write", self._on_text_change)
        
        self.entry = tk.Entry(
            self.text_container,
            textvariable=self.text_var,
            relief="flat",
            bg="white",
            font=("Consolas", 11)
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=ENTRY_HEIGHT_PAD, padx=5)
        
        self.entry.bind("<Up>", lambda e: self.focus_neighbor(self.row_index, -1))
        self.entry.bind("<Down>", lambda e: self.focus_neighbor(self.row_index, 1))
        self.entry.bind("<Return>", lambda e: self.focus_neighbor(self.row_index, 1))

    def _on_combo_change(self, event):
        self.update_callback()

    def _on_quick_select(self, event):
        label = self.quick_combo.get()
        if label in self.quick_input_map:
            code_to_insert = self.quick_input_map[label]
            self.text_var.set(code_to_insert)
            self.quick_combo.set("")
            self.entry.focus_set()

    def _on_text_change(self, *args):
        text_content = self.text_var.get().lower()
        found_value = ""
        if self.command_map:
            sorted_keys = sorted(self.command_map.keys(), key=len, reverse=True)
            for key in sorted_keys:
                if key.lower() in text_content:
                    found_value = self.command_map[key]
                    break
        self.cmd_result_var.set(found_value)
        self.update_callback()

    def get_text_length(self):
        raw_text = self.text_var.get().replace(" ", "")
        length = len(raw_text)
        if length == 0:
            return 0
        return (length + 1) // 2

    def set_display_count(self, count):
        num_bytes = max(2, (count.bit_length() + 7) // 8)
        byte_data = count.to_bytes(num_bytes, byteorder='big')
        hex_str = byte_data.hex().upper()
        self.count_label.config(text=hex_str)

    def get_data(self):
        return {
            "c1": self.combo1.get(),
            "text": self.text_var.get()
        }

    def set_data(self, data):
        self.combo1.set(data.get("c1", ""))
        self.text_var.set(data.get("text", ""))

    def focus(self):
        self.entry.focus_set()

class DataEntryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Unified Input Interface")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        
        self._ensure_directories()
        self.command_map, self.quick_input_data = self.load_csv_data()
        self.hex_codes_for_parsing = []
        self._load_parsing_data()
        
        self.fields = ["INIT", "MAIN", "TALK", "SCOUT", "CROSS", "TOUCH", "E06", "E07"]
        
        self.data_store = {}
        for field in self.fields:
            self.data_store[field] = [{"c1": "", "text": ""} for _ in range(NUM_ROWS)]

        # --- UPDATE STATE ---
        self.target_file_path = None # internal usage for update
        self.master_file_path = ""   # Persistent file path
        # --------------------

        self.current_field = "INIT"
        self.rows = []
        self.nav_buttons = {}

        self.main_container = tk.Frame(self.root, bg="#d9d9d9")
        self.main_container.pack(fill="both", expand=True, padx=OUTER_MARGIN, pady=OUTER_MARGIN)

        self._setup_top_nav()
        self._setup_editor_area()
        self._setup_footer()
        
        self._highlight_active_button()
        self.load_current_field_data()

    def _ensure_directories(self):
        os.makedirs(WORKER_DIR, exist_ok=True)
        os.makedirs(ENTRY_DIR, exist_ok=True)

    def _load_parsing_data(self):
        self.hex_codes_for_parsing = []
        if os.path.exists(CSV_FILENAME):
            try:
                with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) >= 3:
                            code = row[2].strip().replace(" ", "").lower()
                            if code:
                                self.hex_codes_for_parsing.append(code)
                self.hex_codes_for_parsing.sort(key=len, reverse=True)
            except:
                pass

    def load_csv_data(self):
        cmd_map = {}
        quick_data = {'labels': [], 'map': {}}
        if os.path.exists(CSV_FILENAME):
            try:
                with open(CSV_FILENAME, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) >= 2:
                            key = row[0].strip()
                            val = row[1].strip()
                            if key:
                                cmd_map[key] = val
                        if len(row) >= 4:
                            code = row[2].strip()
                            label = row[3].strip()
                            if label:
                                quick_data['labels'].append(label)
                                quick_data['map'][label] = code
                print(f"Loaded CSV: {len(cmd_map)} cmds, {len(quick_data['labels'])} quick inputs.")
            except Exception as e:
                messagebox.showerror("CSV Error", f"Failed to read {CSV_FILENAME}:\n{e}")
        return cmd_map, quick_data

    def _setup_top_nav(self):
        nav_frame = tk.Frame(self.main_container, bg="#333", pady=10, padx=10)
        nav_frame.pack(fill="x")

        tk.Label(nav_frame, text="CONTEXT:", bg="#333", fg="#aaa", font=("Arial", 10, "bold")).pack(side="left", padx=(0, 15))

        for field in self.fields:
            btn = tk.Button(
                nav_frame,
                text=field,
                command=lambda f=field: self.switch_context(f),
                font=("Arial", 10, "bold"),
                width=10,
                relief="flat",
                pady=5
            )
            btn.pack(side="left", padx=2)
            self.nav_buttons[field] = btn

    def _setup_editor_area(self):
        header_frame = tk.Frame(self.main_container, bg="#e0e0e0", pady=4)
        header_frame.pack(fill="x", padx=0, pady=(15, 0))
        
        tk.Label(header_frame, text="JUMP TAG", bg="#e0e0e0", width=10, anchor="w", font=("Arial", 8, "bold")).pack(side="left", padx=(0, 0))
        tk.Label(header_frame, text="xOFFSET", bg="#e0e0e0", width=10, anchor="w", font=("Consolas", 9, "bold")).pack(side="left", padx=(0, 10))
        tk.Label(header_frame, text="CODE INPUT", bg="#e0e0e0", font=("Arial", 8, "bold")).pack(side="left", padx=(0, 0))
        
        tk.Label(header_frame, text="QUICK INPUT", bg="#e0e0e0", width=20, anchor="w", font=("Arial", 8, "bold")).pack(side="right", padx=(5, 0))
        tk.Label(header_frame, text="COMMAND DATA", bg="#e0e0e0", width=25, anchor="w", font=("Arial", 8, "bold")).pack(side="right", padx=(5, 5))

        container_border = tk.Frame(self.main_container, bg="#888", bd=1)
        container_border.pack(fill="both", expand=True, padx=0, pady=0)
        
        self.editor_frame = tk.Frame(container_border, bg="#f0f0f0")
        self.editor_frame.pack(fill="both", expand=True)

        for i in range(NUM_ROWS):
            row = RowWidget(
                self.editor_frame,
                i,
                self.recalculate_cumulative,
                self.move_focus,
                self.command_map,
                self.quick_input_data
            )
            self.rows.append(row)

    def _setup_footer(self):
        footer = tk.Frame(self.main_container, pady=10, bg="#d9d9d9")
        footer.pack(fill="x")
        
        top_footer = tk.Frame(footer, bg="#d9d9d9")
        top_footer.pack(fill="x", expand=True)

        left_section = tk.Frame(top_footer, bg="#d9d9d9")
        left_section.pack(side="left", fill="both", expand=True)

        right_section = tk.Frame(top_footer, bg="#d9d9d9")
        right_section.pack(side="right", fill="y", padx=(10, 0))

        left_section.columnconfigure(1, weight=1)
        tk.Label(left_section, text="Entry Table:", bg="#d9d9d9", font=("Arial", 9)).grid(row=0, column=0, sticky="w", pady=4)
        
        self.entry_table_var = tk.StringVar()
        entry_lbl = tk.Label(
            left_section,
            textvariable=self.entry_table_var,
            bg="#eee",
            anchor="w",
            font=("Consolas", 10),
            relief="sunken",
            padx=5,
            pady=2
        )
        entry_lbl.grid(row=0, column=1, sticky="ew", padx=(10, 40), pady=4)

        tk.Label(left_section, text="Jump Table:", bg="#d9d9d9", font=("Arial", 9)).grid(row=1, column=0, sticky="w", pady=4)
        
        self.jump_table_var = tk.StringVar()
        jump_lbl = tk.Label(
            left_section,
            textvariable=self.jump_table_var,
            bg="#eee",
            anchor="w",
            font=("Consolas", 10),
            relief="sunken",
            padx=5,
            pady=2
        )
        jump_lbl.grid(row=1, column=1, sticky="ew", padx=(10, 40), pady=4)

        btn_width = 22
        tk.Button(right_section, text="Save Worker Profile", command=self.save_worker, bg="#cceeff", width=btn_width).pack(pady=2)
        tk.Button(right_section, text="Load Worker Profile", command=self.load_worker, bg="#cceeff", width=btn_width).pack(pady=2)
        tk.Frame(right_section, height=5, bg="#d9d9d9").pack()
        tk.Button(right_section, text="Save Function (Page)", command=self.save_function, bg="#ccffcc", width=btn_width).pack(pady=2)
        tk.Button(right_section, text="Load Function (Page)", command=self.load_function, bg="#ccffcc", width=btn_width).pack(pady=2)

        tk.Frame(footer, height=10, bg="#d9d9d9").pack(fill="x")
        bottom_row_frame = tk.Frame(footer, bg="#d9d9d9")
        bottom_row_frame.pack(side="bottom", pady=5)

        # --- NEW MASTER FILE SECTION ---
        master_file_frame = tk.Frame(bottom_row_frame, bg="#d9d9d9", bd=1, relief="solid")
        master_file_frame.pack(side="left", padx=(0, 300), fill="y")
        
        #tk.Label(master_file_frame, text="TARGET FILE", font=("Arial", 7, "bold"), bg="#ccc", fg="#333", width=25).pack(fill="x")
        
        tk.Button(master_file_frame, text="SELECT FILE", command=self.select_master_file,
                  bg="#555", fg="white", font=("Arial", 9, "bold"), width=20).pack(pady=(5,2), padx=5)
        
        self.master_file_label = tk.Label(master_file_frame, text="No File Selected", 
                                          bg="#d9d9d9", fg="#888", font=("Arial", 8, "italic"), width=25)
        self.master_file_label.pack(pady=(0, 5))
        # -------------------------------

        left_btn_frame = tk.Frame(bottom_row_frame, bg="#d9d9d9")
        left_btn_frame.pack(side="left", padx=(0, 20))

        tk.Button(left_btn_frame, text="Scan for Custom Workers", command=self.scan_custom_workers,
                  bg="#666", fg="white", font=("Arial", 9, "bold"), width=25).pack(pady=(0, 2))
        
        tk.Button(left_btn_frame, text="Update Custom Worker", command=self.update_custom_worker,
                  bg="#666", fg="white", font=("Arial", 9, "bold"), width=25).pack(pady=(2, 0))

        btn = tk.Button(bottom_row_frame, text="ADD WORKER TO EBP", command=self.print_data,
                        bg="#444", fg="white", font=("Arial", 10, "bold"), relief="flat", padx=20, pady=12)
        btn.pack(side="left")

    def select_master_file(self):
        filename = filedialog.askopenfilename(
            title="Select Target Master File",
            filetypes=(("EBP Files", "*.ebp"), ("All Files", "*.*"))
        )
        if filename:
            self.master_file_path = filename
            global k
            k = filename # Update global k
            
            # Update display
            display_name = os.path.basename(filename)
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            self.master_file_label.config(text=display_name, fg="#000")
            print(f"Master File Selected: {k}")

    # --- SAVE / LOAD HANDLERS ---
    def save_worker(self):
        self.save_current_field_data()
        filename = filedialog.asksaveasfilename(initialdir=WORKER_DIR, title="Save Worker Profile", filetypes=(("JSON Files", "*.json"), ("All Files", "*.*")), defaultextension=".json")
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.data_store, f, indent=4)
                messagebox.showinfo("Success", "Worker Profile Saved Successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save worker:\n{e}")

    def load_worker(self):
        filename = filedialog.askopenfilename(initialdir=WORKER_DIR, title="Load Worker Profile", filetypes=(("JSON Files", "*.json"), ("All Files", "*.*")))
        if filename:
            try:
                with open(filename, 'r') as f:
                    loaded_data = json.load(f)
                if not isinstance(loaded_data, dict):
                    raise ValueError("Invalid file format")
                self.data_store = loaded_data
                for field in self.fields:
                    if field not in self.data_store:
                        self.data_store[field] = [{"c1": "", "text": ""} for _ in range(NUM_ROWS)]
                self.load_current_field_data()
                messagebox.showinfo("Success", "Worker Profile Loaded.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load worker:\n{e}")

    def save_function(self):
        self.save_current_field_data()
        default_name = f"{self.current_field}_data.json"
        filename = filedialog.asksaveasfilename(initialdir=ENTRY_DIR, initialfile=default_name, title=f"Save {self.current_field} Function", filetypes=(("JSON Files", "*.json"), ("All Files", "*.*")), defaultextension=".json")
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.data_store[self.current_field], f, indent=4)
                messagebox.showinfo("Success", f"Function '{self.current_field}' Saved.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save function:\n{e}")

    def load_function(self):
        filename = filedialog.askopenfilename(initialdir=ENTRY_DIR, title=f"Load Data into {self.current_field}", filetypes=(("JSON Files", "*.json"), ("All Files", "*.*")))
        if filename:
            try:
                with open(filename, 'r') as f:
                    loaded_rows = json.load(f)
                if not isinstance(loaded_rows, list):
                    raise ValueError("Invalid file format")
                self.data_store[self.current_field] = loaded_rows
                self.load_current_field_data()
                messagebox.showinfo("Success", f"Data loaded into '{self.current_field}'.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load function:\n{e}")

    # --- CORE LOGIC ---
    def update_footer_tables(self):
        temp_store = self.data_store.copy()
        current_rows_data = []
        for row in self.rows:
            current_rows_data.append(row.get_data())
        temp_store[self.current_field] = current_rows_data

        entry_offsets = []
        jump_offsets = {f"j{i:02X}": None for i in range(12)}
        global_offset = 0
        
        for field in self.fields:
            entry_offsets.append(global_offset)
            rows = temp_store[field]
            for r in rows:
                tag = r['c1']
                if tag in jump_offsets and jump_offsets[tag] is None:
                    jump_offsets[tag] = global_offset
                txt = r['text'].replace(" ", "")
                length = 0
                if txt:
                    length = (len(txt) + 1) // 2
                global_offset += length

        entry_str_parts = []
        for off in entry_offsets:
            b = off.to_bytes(4, byteorder='little')
            entry_str_parts.append(b.hex().upper())
        self.entry_table_var.set("  ".join(entry_str_parts))

        jump_str_parts = []
        for i in range(12):
            tag = f"j{i:02X}"
            off = jump_offsets[tag]
            if off is None:
                off = 0
            b = off.to_bytes(4, byteorder='little')
            jump_str_parts.append(b.hex().upper())
        self.jump_table_var.set("  ".join(jump_str_parts))

    def move_focus(self, current_index, direction):
        new_index = current_index + direction
        if 0 <= new_index < len(self.rows):
            self.rows[new_index].focus()

    def switch_context(self, new_field):
        if self.current_field == new_field:
            return
        self.save_current_field_data()
        self.current_field = new_field
        self._highlight_active_button()
        self.load_current_field_data()

    def _highlight_active_button(self):
        for field, btn in self.nav_buttons.items():
            if field == self.current_field:
                btn.config(bg="#007acc", fg="white")
            else:
                btn.config(bg="#e1e1e1", fg="black")

    def save_current_field_data(self):
        data_list = []
        for row in self.rows:
            data_list.append(row.get_data())
        self.data_store[self.current_field] = data_list

    def get_previous_pages_total(self):
        total = 0
        current_idx = self.fields.index(self.current_field)
        for i in range(current_idx):
            field_name = self.fields[i]
            rows = self.data_store[field_name]
            for r in rows:
                txt = r['text'].replace(" ", "")
                if txt:
                    total += (len(txt) + 1) // 2
        return total

    def load_current_field_data(self):
        data_list = self.data_store[self.current_field]
        for i, row in enumerate(self.rows):
            if i < len(data_list):
                row.set_data(data_list[i])
            else:
                row.set_data({"c1": "", "text": ""})
        self.recalculate_cumulative()

    def recalculate_cumulative(self):
        running_total = self.get_previous_pages_total()
        for row in self.rows:
            row.set_display_count(running_total)
            running_total += row.get_text_length()
        self.update_footer_tables()

    # --- SCANNING LOGIC (Reusable) ---

    def _scan_file_logic(self, filename):
        """Shared scanning logic for both Load and Update functions."""
        SIGNATURE = bytes.fromhex("81 82 83 80 71 72 73 70 61 62 63 60")
        SIG_OFFSET_FROM_START = OBJECT_TOTAL_SIZE - 12
        found_objects = []
        
        try:
            with open(filename, "rb") as f:
                file_data = f.read()
            
            search_index = 0
            while True:
                sig_index = file_data.find(SIGNATURE, search_index)
                if sig_index == -1:
                    break 
                
                obj_start_index = sig_index - SIG_OFFSET_FROM_START
                if obj_start_index < 0:
                    search_index = sig_index + 1
                    continue

                obj_end_index = obj_start_index + OBJECT_TOTAL_SIZE
                found_object = file_data[obj_start_index : obj_end_index]
                found_objects.append((found_object, obj_start_index))
                search_index = sig_index + 1
                
            return found_objects
        except Exception as e:
            messagebox.showerror("Scan Error", f"An error occurred:\n{e}")
            return None

    def scan_custom_workers(self):
        """Scans for workers to LOAD into the UI."""
        if self.master_file_path and os.path.exists(self.master_file_path):
            filename = self.master_file_path
        else:
            filename = filedialog.askopenfilename(
                title="Scan File for Custom Workers",
                filetypes=(("All Files", "*.*"), ("EBP Files", "*.ebp"))
            )
            if filename:
                # If they manually select one here, treat it as the master file going forward?
                # For now, let's just update the internal pointer, but maybe not the master global unless explicit
                pass
        
        if not filename:
            return

        found_objects = self._scan_file_logic(filename)
        
        if not found_objects:
            messagebox.showinfo("Scan Result", "No Custom Workers found.")
            return

        print(f"\nScan Complete. Found {len(found_objects)} worker(s).")
        
        if len(found_objects) == 1:
            ans = messagebox.askyesno("Load Data", f"Found 1 object at 0x{found_objects[0][1]:X}.\nLoad into UI?")
            if ans:
                self.load_from_object(found_objects[0][0])
        else:
            self._show_worker_selection_dialog(found_objects, mode="load")

    def _show_worker_selection_dialog(self, found_objects, mode="load"):
            """Selection dialog. Mode can be 'load' or 'update'."""
            selection_win = tk.Toplevel(self.root)
            selection_win.title(f"Select Worker to {mode.title()}")
            selection_win.geometry("400x300")
            
            tk.Label(selection_win, text=f"Found {len(found_objects)} workers.", font=("Arial", 10)).pack(pady=10)
            
            list_frame = tk.Frame(selection_win)
            list_frame.pack(fill="both", expand=True, padx=10, pady=5)
            
            scrollbar = tk.Scrollbar(list_frame)
            scrollbar.pack(side="right", fill="y")
            
            lb = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Consolas", 10))
            lb.pack(side="left", fill="both", expand=True)
            scrollbar.config(command=lb.yview)
            
            for i, (data, offset) in enumerate(found_objects):
                lb.insert(tk.END, f"Worker #{i+1} - Offset: 0x{offset:08X}")
                
            def on_confirm():
                selection = lb.curselection()
                if selection:
                    index = selection[0]
                    data_bytes, offset = found_objects[index]
                    
                    if mode == "load":
                        self.load_from_object(data_bytes)
                    elif mode == "update":
                        if self.target_file_path and os.path.exists(self.target_file_path):
                            self._perform_update_write(self.target_file_path, offset)
                        else:
                            messagebox.showerror("Error", "Target file path was lost. Please try again.")
                    
                    selection_win.destroy()
                else:
                    messagebox.showwarning("Selection", "Please select a worker first.")

            tk.Button(selection_win, text=f"{mode.title()} Selected", command=on_confirm, bg="#007acc", fg="white").pack(pady=10)
            # --- NEW UPDATE LOGIC ---

    def update_custom_worker(self):
        if self.master_file_path and os.path.exists(self.master_file_path):
            filename = self.master_file_path
        else:
            filename = filedialog.askopenfilename(
                title="Select File to Update",
                filetypes=(("All Files", "*.*"), ("EBP Files", "*.ebp"))
            )
        
        if not filename:
            return

        # Scan internally
        found_objects = self._scan_file_logic(filename)
        
        if not found_objects:
            messagebox.showerror("Error", "No custom workers found in this file to update.")
            return

        self.target_file_path = filename # Store for the dialog callback

        if len(found_objects) == 1:
            ans = messagebox.askyesno("Update Worker", f"Found 1 worker at 0x{found_objects[0][1]:X}.\nOverwrite this worker with current UI data?")
            if ans:
                self._perform_update_write(filename, found_objects[0][1])
        else:
            self._show_worker_selection_dialog(found_objects, mode="update")

    def _perform_update_write(self, filename, offset):
        """
        Reads 'X' (first 4 bytes) from the file at 'offset'.
        Generates new object where pointers = X + RelativePos.
        Writes result back to file.
        """
        try:
            # 1. Read 'X' (The Anchor)
            with open(filename, "rb") as f:
                f.seek(offset)
                x_bytes = f.read(4)
                if len(x_bytes) < 4:
                    raise ValueError("Unexpected EOF reading anchor X.")
                x_val = struct.unpack('<I', x_bytes)[0]
            
            print(f"Updating Worker at 0x{offset:08X}")
            print(f"Captured Anchor X: 0x{x_val:08X}")

            # 2. Generate the new buffer using X as base
            new_object = self._generate_relative_update_object(x_val)
            
            if not new_object:
                return # Error during generation

            # 3. Write it back
            with open(filename, "r+b") as f:
                f.seek(offset)
                f.write(new_object)
            
            messagebox.showinfo("Success", "Worker updated successfully.")
            print("Worker update complete.")

        except Exception as e:
            messagebox.showerror("Update Error", f"Failed to update worker:\n{e}")

    def _generate_relative_update_object(self, anchor_x):
        """
        Generates the 500-byte object where every pointer is (Anchor_X + Relative_Offset).
        """
        self.save_current_field_data()
        temp_store = self.data_store
        
        entry_final_values = []
        jump_final_values = {f"j{i:02X}": None for i in range(12)}
        all_code_bytes = bytearray()
        
        current_relative_ptr = 0

        # Calculate Relative Offsets for Code
        for field in self.fields:
            # The pointer value is simply Anchor_X + Current_Relative_Distance
            val = anchor_x + current_relative_ptr
            
            # Ensure 32-bit wrap
            val = val & 0xFFFFFFFF
            entry_final_values.append(val)
            
            rows = temp_store[field]
            for row in rows:
                tag = row['c1']
                if tag in jump_final_values and jump_final_values[tag] is None:
                    val = anchor_x + current_relative_ptr
                    val = val & 0xFFFFFFFF
                    jump_final_values[tag] = val

                txt = row['text'].replace(" ", "").strip()
                if txt:
                    try:
                        b_data = bytes.fromhex(txt)
                        all_code_bytes.extend(b_data)
                        current_relative_ptr += len(b_data)
                    except ValueError:
                        messagebox.showerror("Hex Error", f"Invalid Hex in {field}: {txt}")
                        return None

        # Fill missing jumps with 0
        for k, v in jump_final_values.items():
            if v is None:
                jump_final_values[k] = 0

        # Build Buffer
        buffer = bytearray(b'\x3C' * OBJECT_TOTAL_SIZE)
        
        ENTRIES_START = 0
        JUMPS_START = 32
        CODE_START = 80
        FOOTER_START = OBJECT_TOTAL_SIZE - 16

        # Write Entries
        for i, val in enumerate(entry_final_values):
            start_idx = ENTRIES_START + (i * 4)
            buffer[start_idx : start_idx+4] = struct.pack('<I', val)

        # Write Jumps
        sorted_jumps = [jump_final_values[f"j{i:02X}"] for i in range(12)]
        for i, val in enumerate(sorted_jumps):
            start_idx = JUMPS_START + (i * 4)
            buffer[start_idx : start_idx+4] = struct.pack('<I', val)

        # Write Code
        code_len = len(all_code_bytes)
        max_code_space = FOOTER_START - CODE_START 
        if code_len > max_code_space:
            messagebox.showerror("Overflow", f"Code is too long! ({code_len} bytes). Max is {max_code_space}.")
            return None
        buffer[CODE_START : CODE_START + code_len] = all_code_bytes

        # Footer: Write X (Anchor) into Ref Ptr + Signature
        buffer[FOOTER_START : FOOTER_START+4] = struct.pack('<I', anchor_x)
        
        rest_hex = "81 82 83 80 71 72 73 70 61 62 63 60"
        rest_bytes = bytes.fromhex(rest_hex)
        buffer[FOOTER_START+4 : FOOTER_START+16] = rest_bytes
        
        return buffer

    # --- EXISTING PARSING/LOADING/ADDING ---

    def load_from_object(self, data_bytes):
        try:
            FOOTER_START = OBJECT_TOTAL_SIZE - 16
            footer = data_bytes[FOOTER_START:]
            ref_ptr = struct.unpack('<I', footer[0:4])[0]

            ENTRIES_START = 0
            JUMPS_START = 32
            CODE_START = 80
            
            entry_ptrs = []
            for i in range(8):
                offset = ENTRIES_START + (i*4)
                val = struct.unpack('<I', data_bytes[offset:offset+4])[0]
                entry_ptrs.append(val)
            
            jump_ptrs = []
            for i in range(12):
                offset = JUMPS_START + (i*4)
                val = struct.unpack('<I', data_bytes[offset:offset+4])[0]
                jump_ptrs.append(val)

            rel_entries = []
            for val in entry_ptrs:
                rel = val - ref_ptr
                rel_entries.append(rel)
            
            rel_jumps = {}
            for i, val in enumerate(jump_ptrs):
                if val != 0:
                    diff = val - ref_ptr
                    rel_jumps[diff] = f"j{i:02X}"

            full_code_block = data_bytes[CODE_START : FOOTER_START]
            new_data_store = {}

            for i, field in enumerate(self.fields):
                start_offset = rel_entries[i]
                if i < len(self.fields) - 1:
                    end_offset = rel_entries[i+1]
                else:
                    end_offset = len(full_code_block)

                if start_offset < 0 or start_offset >= len(full_code_block):
                    chunk = b""
                else:
                    if end_offset > len(full_code_block):
                        end_offset = len(full_code_block)
                    if end_offset < start_offset:
                          end_offset = start_offset
                    chunk = full_code_block[start_offset : end_offset]

                page_rows = self._parse_chunk_to_rows(chunk, start_offset, rel_jumps)
                new_data_store[field] = page_rows

            self.data_store = new_data_store
            self.load_current_field_data()
            messagebox.showinfo("Success", "Data loaded into UI from Object.")

        except Exception as e:
            print(f"Parsing Error: {e}")
            messagebox.showerror("Parsing Error", f"Failed to parse object:\n{e}")

    def _parse_chunk_to_rows(self, chunk, chunk_start_rel_offset, jump_map):
            rows = []
            cursor = 0
            length = len(chunk)
            current_row_bytes = bytearray()
            current_row_tag = ""
            
            def flush_row():
                nonlocal current_row_bytes, current_row_tag
                # Only flush if we have content or a tag
                if len(current_row_bytes) > 0 or current_row_tag:
                    
                    # 1. Get Raw Hex
                    hex_raw = current_row_bytes.hex().upper()

                    # --- NEW LOGIC: COMPRESS PADDING ---
                    # Find sequences of "3C" repeated 11 or more times (>10)
                    # and replace them with a single "3C"
                    hex_raw = re.sub(r'(3C){11,}', '3C', hex_raw)
                    # -----------------------------------
                    
                    # 2. Apply Cosmetic Tweak (Right-aligned 3-byte grouping)
                    rev_hex = hex_raw[::-1]
                    chunks = [rev_hex[i:i+6] for i in range(0, len(rev_hex), 6)]
                    hex_txt = " ".join(chunks)[::-1]
                    
                    rows.append({"c1": current_row_tag, "text": hex_txt})
                
                current_row_bytes = bytearray()
                current_row_tag = ""

            while cursor < length:
                # Absolute offset relative to code block start (80)
                abs_offset_in_code = chunk_start_rel_offset + cursor
                
                # 1. Check if this is a Jump Target
                if abs_offset_in_code in jump_map:
                    flush_row()
                    current_row_tag = jump_map[abs_offset_in_code]

                # 2. Check for CSV Search Terms
                match_found = False
                remaining_bytes = chunk[cursor:]
                remaining_hex = remaining_bytes.hex().lower()
                
                for code in self.hex_codes_for_parsing:
                    if remaining_hex.startswith(code):
                        # Match!
                        match_len_bytes = len(code) // 2
                        
                        if len(current_row_bytes) > 0:
                            flush_row()
                        
                        # Process the command bytes
                        cmd_bytes = remaining_bytes[:match_len_bytes]
                        hex_raw_cmd = cmd_bytes.hex().upper()
                        
                        # Apply cosmetic spacing to command too
                        rev_hex_cmd = hex_raw_cmd[::-1]
                        chunks_cmd = [rev_hex_cmd[i:i+6] for i in range(0, len(rev_hex_cmd), 6)]
                        hex_display = " ".join(chunks_cmd)[::-1]
                        
                        rows.append({"c1": current_row_tag, "text": hex_display})
                        current_row_tag = "" # Consumed
                        
                        cursor += match_len_bytes
                        match_found = True
                        break
                
                if match_found:
                    continue

                # 3. Just a normal byte
                current_row_bytes.append(chunk[cursor])
                cursor += 1
            
            # Flush leftovers
            flush_row()
            
            # Pad with empty rows if needed
            while len(rows) < NUM_ROWS:
                rows.append({"c1": "", "text": ""})
                
            return rows[:NUM_ROWS]
    def print_data(self):
        """Standard 'Add New' Logic (Appends to end)"""
        self.save_current_field_data()
        
        # Check if master file is selected
        if self.master_file_path and os.path.exists(self.master_file_path):
            filename = self.master_file_path
        else:
            filename = filedialog.askopenfilename(title="Select EBP File", filetypes=(("EBP Files", "*.ebp"), ("All Files", "*.*")))
        
        if not filename: return

        global k
        k = filename
        print(f"Filepath selected: {k}")
        ebp_patcher.patch_ebp(k, n_clones=1, q_source_id=1)
        self.root.clipboard_clear()
        self.root.clipboard_append(k)
        self.root.update()

        print(" EBP WORKER ANALYSIS")
        print(f"File: {os.path.basename(filename)}")

        try:
            file_size = os.path.getsize(filename)
            entry_val = file_size - 64
            jump_val = entry_val + 0x20
            
            code_start_val = 0
            with open(filename, "rb") as f:
                f.seek(0x70)
                data = f.read(4)
                if len(data) < 4: return 
                else:
                    val_at_70 = int.from_bytes(data, 'little')
                    code_start_val = val_at_70 + 0x40

            print(f" GENERATING {OBJECT_TOTAL_SIZE}-BYTE OBJECT")
            print("\n[Updating File Footer Pointers...]")
            try:
                with open(filename, "r+b") as f:
                    f.seek(-20, 2) 
                    f.write(entry_val.to_bytes(4, 'little'))
                    f.write(jump_val.to_bytes(4, 'little'))
            except Exception as e:
                messagebox.showerror("File Error", f"Could not update file pointers:\n{e}")
                return 

            final_object = self._generate_byte_object(code_start_val, entry_val)

            if final_object:
                print("\n[Appending Block to File...]")
                try:
                    with open(filename, "ab") as f:
                        f.write(final_object)
                    messagebox.showinfo("Success", f"File Pointers updated and new Worker Object appended.")
                except Exception as e:
                    messagebox.showerror("File Error", f"Could not append to file:\n{e}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to analyze EBP file:\n{e}")

    def _generate_byte_object(self, base_offset, custom_entry_ptr):
        """Standard generator for NEW objects (uses full formula)"""
        def calculate_complex_pointer(relative_pos):
            pos_in_obj = relative_pos + 0x50
            step_2 = pos_in_obj + custom_entry_ptr
            step_3 = step_2 + 0x40
            final_val = step_3 - base_offset
            return final_val & 0xFFFFFFFF

        self.save_current_field_data()
        temp_store = self.data_store
        entry_final_values = [] 
        jump_final_values = {f"j{i:02X}": None for i in range(12)}
        all_code_bytes = bytearray()
        current_relative_ptr = 0

        for field in self.fields:
            val = calculate_complex_pointer(current_relative_ptr)
            entry_final_values.append(val)
            rows = temp_store[field]
            for row in rows:
                tag = row['c1']
                if tag in jump_final_values and jump_final_values[tag] is None:
                    val = calculate_complex_pointer(current_relative_ptr)
                    jump_final_values[tag] = val
                txt = row['text'].replace(" ", "").strip()
                if txt:
                    try:
                        b_data = bytes.fromhex(txt)
                        all_code_bytes.extend(b_data)
                        current_relative_ptr += len(b_data)
                    except ValueError:
                        return None

        for k, v in jump_final_values.items():
            if v is None: jump_final_values[k] = 0 

        buffer = bytearray(b'\x3C' * OBJECT_TOTAL_SIZE)
        ENTRIES_START = 0
        JUMPS_START = 32
        CODE_START  = 80
        FOOTER_START = OBJECT_TOTAL_SIZE - 16

        for i, val in enumerate(entry_final_values):
            start_idx = ENTRIES_START + (i * 4)
            buffer[start_idx : start_idx+4] = struct.pack('<I', val)

        sorted_jumps = [jump_final_values[f"j{i:02X}"] for i in range(12)]
        for i, val in enumerate(sorted_jumps):
            start_idx = JUMPS_START + (i * 4)
            buffer[start_idx : start_idx+4] = struct.pack('<I', val)

        code_len = len(all_code_bytes)
        max_code_space = FOOTER_START - CODE_START 
        if code_len > max_code_space: return None
        buffer[CODE_START : CODE_START + code_len] = all_code_bytes

        init_ptr_bytes = buffer[0:4]
        buffer[FOOTER_START : FOOTER_START+4] = init_ptr_bytes
        rest_hex = "81 82 83 80 71 72 73 70 61 62 63 60"
        rest_bytes = bytes.fromhex(rest_hex)
        buffer[FOOTER_START+4 : FOOTER_START+16] = rest_bytes
        return buffer

def create_dummy_csv():
    if not os.path.exists(CSV_FILENAME):
        print("Creating dummy CSV for testing...")
        data = [
            ["move", "Action: MOVE UNIT", "A0 01", "Move Normal"],
            ["hello", "sys: Greeting", "H1 00", "Greet"]
        ]
        try:
            with open(CSV_FILENAME, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(data)
        except Exception as e:
            print(f"Could not create dummy csv: {e}")

if __name__ == "__main__":
    create_dummy_csv()
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = DataEntryApp(root)
    root.mainloop()
