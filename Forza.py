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
VERSION = "v1.5.4"
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
DOCS_PATH = os.path.join(os.path.expanduser('~'), 'Documents', 'ZuhuProjects', 'ZuhuFH5WS')
CONFIG_FILE = os.path.join(DOCS_PATH, 'Config.json')

# Correct Colors
F_PINK   = "#EB3355" # Watermark/Pause/Super
F_CYAN   = "#6EC1E3" # Log/Normal/Wheelspin
F_YELLOW = "#FEC737" # Res/Debug
F_GREEN  = "#2FB35E" # Totals
F_WHITE  = "#FFFFFF"
F_BLACK  = "#000000"

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
SX, SY = CURR_W / BASE_W, CURR_H / BASE_H

def sc(coords):
    if len(coords) == 4: return (int(coords[0]*SX), int(coords[1]*SY), int(coords[2]*SX), int(coords[3]*SY))
    return (int(coords[0]*SX), int(coords[1]*SY))

# Coordinates
REGION_HEADER = sc((1060, 240, 1500, 310))      
REGION_CAR_NAME = sc((800, 930, 1760, 990))
REGION_PRICE = sc((1050, 1160, 1500, 1205))
REGION_BOTTOM_LEFT = sc((95, 1310, 550, 1365))  
CHECK_PIXEL_X, CHECK_PIXEL_Y = sc((1266, 242))  

REGION_SUPER_L = sc((550, 690, 900, 850))
REGION_SUPER_M = sc((1150, 690, 1500, 850))
REGION_SUPER__R = sc((1750, 690, 2100, 850))
REGION_NORMAL_REEL = sc((1400, 590, 2000, 840))

VALID_PRIZES = [1000, 2000, 4000, 5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 60000, 70000, 80000, 90000, 100000, 125000, 150000, 175000, 200000, 250000, 300000]

class ForzaCanvasUI:
    def __init__(self, canvas):
        self.canvas = canvas
        self.f_md = ("Verdana", int(14 * min(SX, SY)), "bold")
        self.f_sm = ("Verdana", int(10 * min(SX, SY)), "bold")
        self.f_db = ("Arial", int(12 * min(SX, SY)), "bold")

    def round_rect(self, x1, y1, x2, y2, r, color, **kwargs):
        points = [x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y1+r, x2, y2-r, x2, y2-r, x2, y2, x2-r, y2, x2-r, y2, x1+r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y2-r, x1, y1+r, x1, y1+r, x1, y1]
        return self.canvas.create_polygon(points, fill=color, smooth=True, **kwargs)

    def draw_box(self, x, y, label, content, color, tag, triple=False, align="left"):
        # Measure text widths
        l_temp = self.canvas.create_text(0,0, text=label, font=self.f_md)
        c_temp = self.canvas.create_text(0,0, text=content, font=self.f_md)
        l_w = (self.canvas.bbox(l_temp)[2] - self.canvas.bbox(l_temp)[0] + (15 * SX)) if label.strip() else (20 * SX)
        c_w = self.canvas.bbox(c_temp)[2] - self.canvas.bbox(c_temp)[0] + (30 * SX)
        self.canvas.delete(l_temp, c_temp)
        
        h = 35 * SY
        r = 8 * min(SX, SY)
        total_w = l_w + c_w + (l_w if triple else 0)

        start_x = x - total_w if align == "right" else x

        # Outline
        self.round_rect(start_x-2, y-2, start_x+total_w+2, y+h+2, r+2, color, tags=tag)
        # Left Square
        self.round_rect(start_x, y, start_x+l_w, y+h, r, color, tags=tag)
        self.canvas.create_text(start_x + l_w/2, y + h/2, text=label, fill=F_WHITE, font=self.f_md, tags=tag)
        # Middle White Box
        self.round_rect(start_x+l_w, y, start_x+l_w+c_w, y+h, r, F_WHITE, tags=tag)
        self.canvas.create_text(start_x+l_w + c_w/2, y + h/2, text=content, fill=color, font=self.f_md, tags=tag)
        # Right Square
        if triple:
            self.round_rect(start_x+l_w+c_w, y, start_x+total_w, y+h, r, color, tags=tag)

        return start_x, total_w

class ForzaOverlay:
    def __init__(self, config):
        self.root = tk.Tk()
        self.root.attributes("-topmost", True, "-transparentcolor", "black")
        self.root.overrideredirect(True)
        self.root.geometry(f"{CURR_W}x{CURR_H}+0+0")
        self.root.config(bg='black')

        self.canvas = tk.Canvas(self.root, width=CURR_W, height=CURR_H, bg='black', highlightthickness=0)
        self.canvas.pack()
        self.ui = ForzaCanvasUI(self.canvas)

        self.cfg = config
        self.debug_enabled = self.cfg.get("Debug_Mode", False)
        self.car_total, self.cred_total = 0, 0
        self.log_entries = []
        self.paused = True
        self.mode = "PRESS INSERT TO START"
        self.current_state = "PAUSED"
        
        self.refresh_ui()

    def refresh_ui(self):
        self.canvas.delete("ui_element")
        
        # --- TOP LEFT ---
        sx, sw = self.ui.draw_box(20*SX, 20*SY, "ZUHU'S", "FH5 REWARD RUNNER", F_PINK, "ui_element")
        self.ui.draw_box(sx + sw + 10*SX, 20*SY, "RES", f"{CURR_W}X{CURR_H}", F_YELLOW, "ui_element")

        # --- LOGS ---
        y_log = 65 * SY
        for prefix, text in self.log_entries[-8:]:
            self.ui.draw_box(20*SX, y_log, prefix, text, F_CYAN, "ui_element")
            y_log += 45 * SY

        # --- TOP MID: Mathematically Centered ---
        if self.paused:
            # Measure to find center
            l_w = 20 * SX
            c_temp = self.canvas.create_text(0,0, text="SCRIPT PAUSED", font=self.ui.f_md)
            c_w = self.canvas.bbox(c_temp)[2] - self.canvas.bbox(c_temp)[0] + (30 * SX)
            self.canvas.delete(c_temp)
            total_p_w = l_w + c_w + l_w
            self.ui.draw_box((CURR_W - total_p_w)/2, 20*SY, " ", "SCRIPT PAUSED", F_PINK, "ui_element", triple=True)

        # --- TOP RIGHT ---
        rx, rw = self.ui.draw_box(CURR_W - 20*SX, 20*SY, " ", self.mode, 
                                  F_PINK if "SUPER" in self.mode else (F_CYAN if "NORMAL" in self.mode else "#888888"), 
                                  "ui_element", align="right")
        self.ui.draw_box(rx - 10*SX, 20*SY, "DEBUG", "ON" if self.debug_enabled else "OFF", F_YELLOW, "ui_element", align="right")

        # --- BOTTOM LEFT ---
        if self.car_total + self.cred_total > 0:
            bx = 20*SX
            if self.car_total > 0: 
                lx, lw = self.ui.draw_box(bx, CURR_H - 105*SY, "CAR TOTAL", f"{self.car_total:,}", F_GREEN, "ui_element")
                bx = lx + lw + 10*SX
            if self.cred_total > 0: 
                lx, lw = self.ui.draw_box(bx, CURR_H - 105*SY, "CREDITS TOTAL", f"{self.cred_total:,}", F_GREEN, "ui_element")
                bx = lx + lw + 10*SX
            self.ui.draw_box(20*SX, CURR_H - 60*SY, "CR TOTAL", f"{self.car_total + self.cred_total:,}", F_GREEN, "ui_element")

        self.canvas.create_text(CURR_W-20*SX, CURR_H-20*SY, text="Controls: [INSERT] Start | Hold [~] 5s Debug | [CTRL+C] Exit", font=self.ui.f_sm, fill=F_PINK, anchor="se", tags="ui_element")
        
        if self.debug_enabled: self.draw_debug_boxes(self.current_state)

    def draw_debug_boxes(self, state):
        self.current_state = state
        self.canvas.delete("debug_box")
        if not self.debug_enabled: return
        
        # Helper to draw box + text
        def db_item(coords, label, color):
            l, t, r, b = coords
            self.canvas.create_rectangle(l, t, r, b, outline=color, width=2, tags="debug_box")
            self.canvas.create_text(l, t-5*SY, text=label, fill=color, font=self.ui.f_db, anchor="sw", tags="debug_box")

        if state in ["WAITING", "PAUSED"]:
            px, py = CHECK_PIXEL_X, CHECK_PIXEL_Y
            self.canvas.create_oval(px-5, py-5, px+5, py+5, outline="red", width=3, tags="debug_box")
            self.canvas.create_text(px+10, py, text="Detection Point", fill="red", font=self.ui.f_db, anchor="w", tags="debug_box")
        elif state == "SPINNING":
            db_item(REGION_BOTTOM_LEFT, "Action Detection", "#00FF00")
            mapping = [(REGION_SUPER_L, "S-Left"), (REGION_SUPER_M, "S-Mid"), (REGION_SUPER__R, "S-Right")] if current_mode == "SUPER" else [(REGION_NORMAL_REEL, "Normal Reel")]
            for reg, lbl in mapping: db_item(reg, lbl, "cyan")
        elif state == "CAR_SCREEN":
            db_item(REGION_HEADER, "Owned Check", "#00FF00")
            db_item(REGION_CAR_NAME, "Car Name", "#00FF00")
            db_item(REGION_PRICE, "Value Check", "#00FF00")

    def update_log(self, prefix, text):
        print(f"[{prefix}] {text}") # Restored CMD Print
        self.log_entries.append((prefix, text))
        self.refresh_ui()

    def update_mode(self, mode):
        self.mode = mode.upper()
        self.refresh_ui()

    def update_pause(self, is_paused):
        print(f"--- SCRIPT {'PAUSED' if is_paused else 'RESUMED'} ---") # Restored CMD Print
        self.paused = is_paused
        self.refresh_ui()

    def add_earnings(self, amount, is_car=True):
        self.car_total += amount if is_car else 0
        self.cred_total += 0 if is_car else amount
        self.refresh_ui()

    def toggle_debug(self):
        self.debug_enabled = not self.debug_enabled
        print(f"Debug Mode: {'ON' if self.debug_enabled else 'OFF'}")
        self.refresh_ui()

# --- LOGIC THREAD ---
overlay = None
paused, running, current_mode, sync_requested = True, True, "NORMAL", False

def toggle_pause():
    global paused, sync_requested
    paused = not paused
    if overlay: overlay.update_pause(paused)
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
            img = sct_i.grab({"top": CHECK_PIXEL_Y, "left": CHECK_PIXEL_X, "width": 1, "height": 1})
            current_mode = "SUPER" if (img.raw[2] > 230) else "NORMAL"
            if overlay: overlay.update_mode(f"{current_mode} WHEELSPIN")
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
            status = "KEEP" if keep else "SELL"
            content = f"{c_name} | {i_price:,}" if not keep else f"{c_name}"
            
            if overlay: 
                overlay.update_log(status, content)
                if not keep and cfg.get("Car_Earned", True): overlay.add_earnings(i_price, True)
            
            if keep: pydirectinput.press('enter')
            else:
                pydirectinput.press('down'); time.sleep(0.1); pydirectinput.press('down')
                time.sleep(0.1); pydirectinput.press('enter')
            time.sleep(1.0); continue

        bottom = get_ui_text(sct_i, REGION_BOTTOM_LEFT).upper()
        if any(x in bottom for x in ["SKIP", "COLLECT", "SPIN"]):
            if overlay: overlay.draw_debug_boxes("SPINNING")
            if not scanned_this_spin:
                if cfg.get("Credit_Earned", True):
                    time.sleep(cfg.get("Reel_Scan_Delay", 1.5))
                    mapping = {"LEFT": REGION_SUPER_L, "MIDDLE": REGION_SUPER_M, "RIGHT": REGION_SUPER__R} if current_mode == "SUPER" else {"MIDDLE": REGION_NORMAL_REEL}
                    spin_total = 0
                    for pos, reg in mapping.items():
                        val = price_to_int(get_reel_ocr(sct_i, reg))
                        if val > 50:
                            match = min(VALID_PRIZES, key=lambda x: abs(x - val))
                            spin_total += match
                            if overlay: overlay.update_log(f"CR {pos}", f"{match:,}")
                    if overlay: overlay.add_earnings(spin_total, False)
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
    
    def check_loop():
        if not running: overlay.root.destroy(); sys.exit(0)
        overlay.root.after(100, check_loop)
    overlay.root.after(100, check_loop)
    overlay.root.mainloop()