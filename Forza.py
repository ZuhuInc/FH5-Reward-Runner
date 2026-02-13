import pydirectinput
import time
import pytesseract
import keyboard
import sys
import os
import json
import tkinter as tk
from threading import Thread
from mss import mss
from PIL import Image

# --- CONFIGURATION & PATHS ---
VERSION = "v1.3.2"
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
DOCS_PATH = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuProjects', 'ZuhuFH5WS')
CONFIG_FILE = os.path.join(DOCS_PATH, 'Config.json')

def load_config():
    defaults = {
        "Keep_FE": True, "Keep_HV": False, "Value_HV": 1000000, 
        "Car_Earned": True, "Credit_Earned": True, 
        "Reel_Scan_Delay": 1.5, "Debug_Mode": False 
    }
    if not os.path.exists(DOCS_PATH): os.makedirs(DOCS_PATH)
    config = defaults.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config.update(json.load(f))
        except: pass
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    return config

# --- RESOLUTION SCALING ---
def get_screen_resolution():
    root = tk.Tk()
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    root.destroy()
    return w, h

CURR_W, CURR_H = get_screen_resolution()
BASE_W, BASE_H = 2560, 1440 
SCALE_X, SCALE_Y = CURR_W / BASE_W, CURR_H / BASE_H

def scale_coords(coords):
    if len(coords) == 4:
        return (int(coords[0]*SCALE_X), int(coords[1]*SCALE_Y), int(coords[2]*SCALE_X), int(coords[3]*SCALE_Y))
    return (int(coords[0]*SCALE_X), int(coords[1]*SCALE_Y))

# Coordinates
REGION_HEADER = scale_coords((1060, 240, 1500, 310))      
REGION_CAR_NAME = scale_coords((800, 930, 1760, 990))
REGION_PRICE = scale_coords((1050, 1160, 1500, 1205))
REGION_BOTTOM_LEFT = scale_coords((95, 1310, 550, 1365))  
CHECK_PIXEL_X, CHECK_PIXEL_Y = scale_coords((1266, 242))  

REGION_SUPER_L = scale_coords((550, 690, 900, 850))
REGION_SUPER_M = scale_coords((1150, 690, 1500, 850))
REGION_SUPER__R = scale_coords((1750, 690, 2100, 850))
REGION_NORMAL_REEL = scale_coords((1400, 590, 2000, 840))

VALID_PRIZES = [1000, 2000, 4000, 5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 60000, 70000, 80000, 90000, 100000, 125000, 150000, 175000, 200000, 250000, 300000]

class ForzaOverlay:
    def __init__(self, config):
        self.root = tk.Tk()
        self.root.attributes("-topmost", True, "-transparentcolor", "black")
        self.root.overrideredirect(True)
        self.root.geometry(f"{CURR_W}x{CURR_H}+0+0")
        self.root.config(bg='black')

        self.canvas = tk.Canvas(self.root, width=CURR_W, height=CURR_H, bg='black', highlightthickness=0)
        self.canvas.pack()

        self.f_lg = int(24 * min(SCALE_X, SCALE_Y))
        self.f_md = int(14 * min(SCALE_X, SCALE_Y))
        self.f_sm = int(10 * min(SCALE_X, SCALE_Y))
        self.f_db = int(13 * min(SCALE_X, SCALE_Y))

        # --- TOP LEFT SECTION (Watermark + Resolution) ---
        self.frame_top_left = tk.Frame(self.root, bg="black")
        self.frame_top_left.place(x=20 * SCALE_X, y=20 * SCALE_Y)

        self.label_watermark = tk.Label(self.frame_top_left, text="[Zuhu’s FH5 Reward Runner]", 
                                        font=("Verdana", self.f_md, "bold"), fg="#FF1493", bg="black")
        self.label_watermark.pack(side="left")

        self.label_res = tk.Label(self.frame_top_left, text=f"[{CURR_W}x{CURR_H}]", 
                                  font=("Verdana", self.f_md, "bold"), fg="yellow", bg="black")
        self.label_res.pack(side="left", padx=10)

        # --- Top LEFT 2 (LOG) ---
        self.log_lines = []
        self.label_left = tk.Label(self.root, text="", font=("Verdana", self.f_md, "bold"), 
                                   fg="aqua", bg="black", justify="left", anchor="nw")
        self.label_left.place(x=20 * SCALE_X, y=48 * SCALE_Y)
        
        # --- TOP MID (Paused Text) ---
        self.label_mid = tk.Label(self.root, text="", font=("Verdana", self.f_lg, "bold"), fg="#FF1493", bg="black")
        self.label_mid.place(relx=0.5, y=20 * SCALE_Y, anchor="n")

        # --- TOP RIGHT (Mode & Debug) ---
        self.frame_right = tk.Frame(self.root, bg="black")
        self.frame_right.place(relx=0.98, y=20 * SCALE_Y, anchor="ne")
        
        self.label_debug_tag = tk.Label(self.frame_right, text="[DEBUG: ON]", font=("Verdana", self.f_md, "bold"), fg="yellow", bg="black")
        self.label_mode = tk.Label(self.frame_right, text="[Press INSERT to Start]", font=("Verdana", self.f_md, "bold"), fg="#888888", bg="black")
        self.label_mode.pack(side="right")
        self.label_debug_tag.pack(side="right", padx=10)

        # --- BOTTOM RIGHT (Controls) ---
        self.label_controls = tk.Label(self.root, text=f"Controls: [INSERT] Start | Hold [~] 5s Debug | [CTRL+C] Exit", font=("Verdana", self.f_sm, "bold"), fg="#FF1493", bg="black")
        self.label_controls.place(relx=0.98, rely=0.98, anchor="se")

        self.car_earned_total, self.cred_earned_total = 0, 0
        self.cfg = config
        self.debug_enabled = self.cfg.get("Debug_Mode", False)
        
        self.label_car = tk.Label(self.root, text="", font=("Verdana", self.f_md, "bold"), fg="#FFD700", bg="black")
        self.label_cred = tk.Label(self.root, text="", font=("Verdana", self.f_md, "bold"), fg="#00FF7F", bg="black")
        self.label_total = tk.Label(self.root, text="", font=("Verdana", self.f_md+2, "bold"), fg="aqua", bg="black")

        self.refresh_ui_layout()

    def draw_text_shadow(self, x, y, text, color, anchor="sw"):
        font = ("Arial", self.f_db, "bold")
        self.canvas.create_text(x+1, y+1, text=text, fill="black", font=font, anchor=anchor)
        self.canvas.create_text(x, y, text=text, fill=color, font=font, anchor=anchor)

    def refresh_ui_layout(self):
        curr_y = 55 * SCALE_Y
        self.label_car.place_forget(); self.label_cred.place_forget(); self.label_total.place_forget()
        
        if self.car_earned_total > 0:
            self.label_car.place(relx=0.98, y=curr_y, anchor="ne")
            curr_y += 30 * SCALE_Y
        if self.cred_earned_total > 0:
            self.label_cred.place(relx=0.98, y=curr_y, anchor="ne")
            curr_y += 30 * SCALE_Y
        if self.car_earned_total > 0 or self.cred_earned_total > 0:
            self.label_total.place(relx=0.98, y=curr_y + 10 * SCALE_Y, anchor="ne")
        
        if self.debug_enabled: self.label_debug_tag.pack(side="right", padx=10)
        else: self.label_debug_tag.pack_forget()
        self.refresh_values()

    def draw_debug_boxes(self, state):
        self.canvas.delete("all")
        if not self.debug_enabled: return
        
        if state == "WAITING" or state == "PAUSED":
            px, py = CHECK_PIXEL_X, CHECK_PIXEL_Y
            self.canvas.create_oval(px-5, py-5, px+5, py+5, outline="red", width=3)
            self.draw_text_shadow(px+14, py, "Detection Point", "red", anchor="w")

        elif state == "SPINNING":
            l, t, r, b = REGION_BOTTOM_LEFT
            self.canvas.create_rectangle(l, t, r, b, outline="#00FF00", width=3)
            self.draw_text_shadow(l, t-8, "Action Detection", "#00FF00")
            
            if self.cfg.get("Credit_Earned", True):
                mapping = []
                if current_mode == "SUPER":
                    mapping = [(REGION_SUPER_L, "S-Left"), (REGION_SUPER_M, "S-Mid"), (REGION_SUPER__R, "S-Right")]
                else:
                    mapping = [(REGION_NORMAL_REEL, "Normal Reel")]
                
                for (rl, rt, rr, rb), rlab in mapping:
                    self.canvas.create_rectangle(rl, rt, rr, rb, outline="cyan", width=3)
                    self.draw_text_shadow(rl, rt-8, rlab, "cyan")

        elif state == "CAR_SCREEN":
            regions = [(REGION_HEADER, "Owned Check"), (REGION_CAR_NAME, "Car Name"), (REGION_PRICE, "Value Check")]
            for (l, t, r, b), label in regions:
                self.canvas.create_rectangle(l, t, r, b, outline="#00FF00", width=3)
                self.draw_text_shadow(l, t-8, label, "#00FF00")

    def toggle_debug(self):
        self.debug_enabled = not self.debug_enabled
        self.update_log(f"Debug Mode: {'ON' if self.debug_enabled else 'OFF'}")
        self.refresh_ui_layout()
        if paused: self.draw_debug_boxes("PAUSED")

    def update_log(self, text):
        print(text)
        self.log_lines.append(text)
        if len(self.log_lines) > 8: self.log_lines.pop(0)
        self.label_left.config(text="\n".join(self.log_lines))

    def update_pause(self, is_paused):
        self.label_mid.config(text="--- SCRIPT PAUSED ---" if is_paused else "")

    def update_mode(self, mode):
        color = "#FF1493" if "Super" in mode else "#00BFFF"
        self.label_mode.config(text=f"[{mode}]", fg=color)

    def add_earnings(self, amount, is_car=True):
        if is_car: self.car_earned_total += amount
        else: self.cred_earned_total += amount
        self.refresh_ui_layout() 

    def refresh_values(self):
        self.label_car.config(text=f"[CAR Credits]: {self.car_earned_total:,} CR")
        self.label_cred.config(text=f"[CR Credits]: {self.cred_earned_total:,} CR")
        self.label_total.config(text=f"[Total Credits]: {self.car_earned_total + self.cred_earned_total:,} CR")

# --- GLOBALS & LOGIC ---
overlay = None
paused, running, current_mode, sync_requested = True, True, "NORMAL", False

def toggle_pause():
    global paused, sync_requested
    paused = not paused
    if overlay: 
        overlay.update_pause(paused)
        if paused: overlay.draw_debug_boxes("PAUSED")
    if not paused: sync_requested = True

keyboard.add_hotkey('insert', toggle_pause)
keyboard.add_hotkey('ctrl+c', lambda: globals().update(running=False))

def logic_thread():
    global sync_requested, running, current_mode
    sct_i = mss()
    cfg = load_config()
    scanned_this_spin = False
    tilde_start = None

    while running:
        if keyboard.is_pressed('`'):
            if tilde_start is None: tilde_start = time.time()
            elif time.time() - tilde_start > 5:
                if overlay: overlay.toggle_debug()
                tilde_start = time.time() + 999
        else: tilde_start = None

        if paused:
            if overlay: overlay.draw_debug_boxes("PAUSED")
            time.sleep(0.1); continue
        
        if sync_requested:
            cfg = load_config() 
            if overlay: 
                overlay.cfg = cfg
                overlay.refresh_ui_layout()
            img = sct_i.grab({"top": CHECK_PIXEL_Y, "left": CHECK_PIXEL_X, "width": 1, "height": 1})
            current_mode = "SUPER" if (img.raw[2] > 230) else "NORMAL"
            if overlay: overlay.update_mode("Super Wheelspin" if current_mode == "SUPER" else "Normal Wheelspin")
            sync_requested = False
            
        header = get_ui_text(sct_i, REGION_HEADER).upper()
        
        if any(word in header for word in ["OWNED", "ALREADY", "CAR"]):
            if overlay: overlay.draw_debug_boxes("CAR_SCREEN")
            name_raw = get_ui_text(sct_i, REGION_CAR_NAME)
            price_raw = get_ui_text(sct_i, REGION_PRICE)
            c_name = "".join([c for c in name_raw if c.isalnum() or c in " '-"]).strip()
            i_price = price_to_int(price_raw)
            if len(c_name) < 3: continue
            
            keep = (" FE" in c_name.upper()) or (cfg["Keep_HV"] and i_price >= cfg["Value_HV"])
            
            status_text = "KEEP" if keep else "SELL"
            price_display = f"FE/HV" if keep else f"{i_price:,}"
            overlay.update_log(f"[{status_text}] {c_name} [{price_display}]")
            
            if not keep and cfg.get("Car_Earned", True):
                overlay.add_earnings(i_price, is_car=True)
            
            if keep: pydirectinput.press('enter')
            else:
                pydirectinput.press('down'); time.sleep(0.05); pydirectinput.press('down')
                time.sleep(0.05); pydirectinput.press('enter')
            time.sleep(1.0); continue

        bottom = get_ui_text(sct_i, REGION_BOTTOM_LEFT).upper()
        if any(x in bottom for x in ["SKIP", "COLLECT", "SPIN"]):
            if overlay: overlay.draw_debug_boxes("SPINNING")
            if not scanned_this_spin:
                if cfg.get("Credit_Earned", True):
                    time.sleep(cfg.get("Reel_Scan_Delay", 1.5))
                    
                    if current_mode == "SUPER":
                        mapping = {"LEFT": REGION_SUPER_L, "MIDDLE": REGION_SUPER_M, "RIGHT": REGION_SUPER__R}
                    else:
                        mapping = {"REEL": REGION_NORMAL_REEL}
                    
                    spin_total = 0
                    for pos, reg in mapping.items():
                        val = price_to_int(get_reel_ocr(sct_i, reg))
                        if val > 50:
                            match = min(VALID_PRIZES, key=lambda x: abs(x - val))
                            spin_total += match
                            if overlay: overlay.update_log(f"[CR {pos}] {match:,}")
                    if overlay: overlay.add_earnings(spin_total, is_car=False)
                else: time.sleep(0.4)
                scanned_this_spin = True
            pydirectinput.press('enter'); time.sleep(0.5); scanned_this_spin = False
        else:
            if overlay: overlay.draw_debug_boxes("WAITING")
        time.sleep(0.05)

# --- OCR HELPERS ---
def get_reel_ocr(sct, reg):
    l, t, r, b = reg
    img = sct.grab({"top": t, "left": l, "width": r - l, "height": b - t})
    img_pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX").convert('L')
    img_pil = img_pil.resize((img_pil.width*2, img_pil.height*2), Image.LANCZOS)
    img_pil = img_pil.point(lambda x: 255 if x > 200 else 0)
    return pytesseract.image_to_string(img_pil, config='--psm 7 -c tessedit_char_whitelist=0123456789,').strip()

def get_ui_text(sct, reg):
    l, t, r, b = reg
    img = sct.grab({"top": t, "left": l, "width": r - l, "height": b - t})
    return pytesseract.image_to_string(Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX").convert('L'), config='--psm 7').strip()

def price_to_int(s):
    try: return int("".join(filter(str.isdigit, s)))
    except: return 0

if __name__ == "__main__":
    conf = load_config()
    print(f"--- Forza Wheelspin Automator {VERSION} ---")
    print(f"Detected Resolution: {CURR_W}x{CURR_H}")
    print("Controls: [INSERT] Start/Pause | [CTRL+C] Exit")
    
    t = Thread(target=logic_thread, daemon=True)
    t.start()
    overlay = ForzaOverlay(conf)
    overlay.update_pause(True) 
    
    def check_loop():
        if not running:
            print("\n--- [Exit] Triggered by User (Ctrl+C) ---")
            overlay.root.destroy(); sys.exit(0)
        overlay.root.after(100, check_loop)
    overlay.root.after(100, check_loop)
    try: overlay.root.mainloop()
    except KeyboardInterrupt: sys.exit(0)