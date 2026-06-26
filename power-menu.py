import gi
import subprocess
import os
import json
import math
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

SINK_IDENTIFIER = "0"
_clean_env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
PIN_LENGTH = 4

# Geometry
MENU_W, MENU_H = 360, 280
PIN_W,  PIN_H  = 360, 430
SLIDER_H       = 100
CORNER         = 28
BTN_R          = 14

# Phases
PHASE_MENU       = 'menu'
PHASE_PIN        = 'pin'
PHASE_SLIDER     = 'slider'
PHASE_CHANGE_PIN = 'change_pin'

# Timeouts (ms)
MENU_DISMISS_MS    = 8_000
PIN_DISMISS_MS     = 30_000
SLIDER_DISMISS_MS  = 10_000
PIN_ERROR_CLEAR_MS = 1_500

# Colors (R, G, B, A)
DARK_CARD  = (0.05, 0.05, 0.05, 0.90)
CYAN       = (0.00, 1.00, 1.00, 1.00)
CYAN_DIM   = (0.00, 0.75, 0.75, 0.70)
DANGER_RED = (1.00, 0.30, 0.30, 1.00)
GRAY_MID   = (0.55, 0.55, 0.55, 0.80)
WHITE      = (1.00, 1.00, 1.00, 0.90)


# --- Config persistence ---

def load_pin():
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        pin = str(data.get("power_menu_pin", "1234"))
        if pin.isdigit() and len(pin) == PIN_LENGTH:
            return pin
    except Exception:
        pass
    return "1234"


def save_pin(pin):
    try:
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
        except Exception:
            data = {}
        data["power_menu_pin"] = pin
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save config: {e}")


# --- Drawing helpers ---

def _set_color(cr, rgba):
    cr.set_source_rgba(*rgba)


def rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r,  0,            math.pi / 2)
    cr.arc(x + r,     y + h - r, r,  math.pi / 2,  math.pi)
    cr.arc(x + r,     y + r,     r,  math.pi,      -math.pi / 2)
    cr.close_path()


def top_rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.line_to(x + w, y + h)
    cr.line_to(x,     y + h)
    cr.arc(x + r,     y + r, r,  math.pi,      -math.pi / 2)
    cr.close_path()


def draw_text_centered(cr, text, cx, cy, font="Sans", size=14, bold=False, rgba=WHITE):
    weight = cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL
    cr.select_font_face(font, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    ext = cr.text_extents(text)
    _set_color(cr, rgba)
    cr.move_to(cx - ext.width / 2 - ext.x_bearing,
               cy - ext.height / 2 - ext.y_bearing)
    cr.show_text(text)


def get_current_volume():
    try:
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, check=True
        )
        for part in result.stdout.split('/'):
            if '%' in part:
                return int(part.strip().split()[0].replace('%', ''))
    except Exception:
        pass
    return 50


class PowerMenuWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(MENU_W, MENU_H)

        self._correct_pin  = load_pin()

        # Volume slider state
        self._phase        = PHASE_MENU
        self._pin_entered  = ''
        self._pin_error    = False
        self._volume       = get_current_volume()
        self._vol_dragging = False
        self._track_x      = 0
        self._track_w      = 1
        self._btn_rects    = {}

        # Change-PIN state
        self._change_step    = 'new'   # 'new' | 'confirm'
        self._change_buf     = ''
        self._new_pin_first  = ''
        self._change_error   = None
        self._change_success = False

        # Timers
        self._menu_timer       = None
        self._pin_timer        = None
        self._slider_timer     = None
        self._change_pin_timer = None

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("draw",                 self._on_draw)
        self.connect("button-press-event",   self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event",  self._on_motion)

        self._menu_timer = GLib.timeout_add(MENU_DISMISS_MS, Gtk.main_quit)

    # --- Timer helpers ---

    def _cancel_timer(self, attr):
        t = getattr(self, attr)
        if t:
            GLib.source_remove(t)
            setattr(self, attr, None)

    # --- Phase transitions ---

    def _goto_pin(self):
        self._cancel_timer('_menu_timer')
        self._phase = PHASE_PIN
        self._pin_entered = ''
        self._pin_error = False
        self._btn_rects = {}
        self.resize(PIN_W, PIN_H)
        self.queue_draw()
        self._pin_timer = GLib.timeout_add(PIN_DISMISS_MS, Gtk.main_quit)

    def _goto_slider(self):
        self._cancel_timer('_pin_timer')
        self._cancel_timer('_change_pin_timer')
        self._phase = PHASE_SLIDER
        self._btn_rects = {}
        self._volume = get_current_volume()

        monitor = Gdk.Display.get_default().get_primary_monitor()
        geo = monitor.get_geometry()
        self.resize(geo.width, SLIDER_H)
        self.move(geo.x, geo.y + geo.height - SLIDER_H)
        self.queue_draw()
        self._reset_slider_timer()

    def _goto_change_pin(self):
        self._cancel_timer('_slider_timer')
        self._phase = PHASE_CHANGE_PIN
        self._change_step = 'new'
        self._change_buf = ''
        self._new_pin_first = ''
        self._change_error = None
        self._change_success = False
        self._btn_rects = {}

        monitor = Gdk.Display.get_default().get_primary_monitor()
        geo = monitor.get_geometry()
        cx = geo.x + (geo.width - PIN_W) // 2
        cy = geo.y + (geo.height - PIN_H) // 2
        self.resize(PIN_W, PIN_H)
        self.move(cx, cy)
        self.queue_draw()
        self._change_pin_timer = GLib.timeout_add(PIN_DISMISS_MS, Gtk.main_quit)

    def _reset_slider_timer(self):
        self._cancel_timer('_slider_timer')
        self._slider_timer = GLib.timeout_add(SLIDER_DISMISS_MS, Gtk.main_quit)

    # --- Drawing ---

    def _on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if self._phase == PHASE_MENU:
            self._draw_menu(cr)
        elif self._phase == PHASE_PIN:
            self._draw_pin_panel(cr, "ENTER PIN", self._pin_entered,
                                 len(self._correct_pin),
                                 "Incorrect PIN" if self._pin_error else None)
        elif self._phase == PHASE_SLIDER:
            self._draw_slider(cr, self.get_allocated_width())
        elif self._phase == PHASE_CHANGE_PIN:
            self._draw_change_pin(cr)

    def _draw_menu(self, cr):
        rounded_rect(cr, 0, 0, MENU_W, MENU_H, CORNER)
        _set_color(cr, DARK_CARD)
        cr.fill()

        draw_text_centered(cr, "POWER MENU", MENU_W / 2, 36,
                           font="Sans", size=15, bold=True, rgba=GRAY_MID)

        buttons = [
            ("power_off",     "POWER OFF",     62,  DANGER_RED),
            ("restart",       "RESTART",       128, GRAY_MID),
            ("change_volume", "CHANGE VOLUME", 194, CYAN),
        ]
        self._btn_rects = {}
        for key, label, y, color in buttons:
            bx, bw, bh = 24, 312, 56
            rounded_rect(cr, bx, y, bw, bh, BTN_R)
            _set_color(cr, color)
            cr.set_line_width(1.5)
            cr.stroke()
            draw_text_centered(cr, label, MENU_W / 2, y + bh / 2,
                               font="Sans", size=14, bold=True, rgba=color)
            self._btn_rects[key] = (bx, y, bw, bh)

    def _draw_pin_panel(self, cr, header, buf, n_dots, error_msg):
        """Shared renderer for both ENTER PIN and CHANGE PIN phases."""
        rounded_rect(cr, 0, 0, PIN_W, PIN_H, CORNER)
        _set_color(cr, DARK_CARD)
        cr.fill()

        draw_text_centered(cr, header, PIN_W / 2, 36,
                           font="Sans", size=15, bold=True, rgba=WHITE)

        dot_r = 10
        spacing = 28
        total_w = (n_dots - 1) * spacing
        dot_cx0 = PIN_W / 2 - total_w / 2
        dot_cy = 86
        for i in range(n_dots):
            cx = dot_cx0 + i * spacing
            if i < len(buf):
                _set_color(cr, CYAN)
                cr.arc(cx, dot_cy, dot_r, 0, 2 * math.pi)
                cr.fill()
            else:
                _set_color(cr, GRAY_MID)
                cr.arc(cx, dot_cy, dot_r, 0, 2 * math.pi)
                cr.set_line_width(1.5)
                cr.stroke()

        if error_msg:
            draw_text_centered(cr, error_msg, PIN_W / 2, 118,
                               font="Sans", size=13, rgba=DANGER_RED)

        pad_labels = [
            ['1', '2', '3'],
            ['4', '5', '6'],
            ['7', '8', '9'],
            [None, '0', '⌫'],
        ]
        cell_w, cell_h, gap = 96, 54, 8
        pad_w = 3 * cell_w + 2 * gap
        pad_x0 = (PIN_W - pad_w) // 2
        pad_y0 = 148

        self._btn_rects = {}
        for ri, row in enumerate(pad_labels):
            for ci, label in enumerate(row):
                if label is None:
                    continue
                bx = pad_x0 + ci * (cell_w + gap)
                by = pad_y0 + ri * (cell_h + gap)
                rounded_rect(cr, bx, by, cell_w, cell_h, BTN_R)
                color = CYAN_DIM if label == '⌫' else GRAY_MID
                _set_color(cr, color)
                cr.set_line_width(1.5)
                cr.stroke()
                draw_text_centered(cr, label, bx + cell_w / 2, by + cell_h / 2,
                                   font="Sans", size=18, bold=True, rgba=WHITE)
                key = 'backspace' if label == '⌫' else label
                self._btn_rects[key] = (bx, by, cell_w, cell_h)

    def _draw_change_pin(self, cr):
        if self._change_success:
            header = "PIN SAVED"
            error_msg = None
        elif self._change_step == 'new':
            header = "NEW PIN"
            error_msg = self._change_error
        else:
            header = "CONFIRM PIN"
            error_msg = self._change_error

        if self._change_success:
            rounded_rect(cr, 0, 0, PIN_W, PIN_H, CORNER)
            _set_color(cr, DARK_CARD)
            cr.fill()
            draw_text_centered(cr, "PIN SAVED", PIN_W / 2, PIN_H / 2,
                               font="Sans", size=20, bold=True, rgba=CYAN)
        else:
            self._draw_pin_panel(cr, header, self._change_buf, PIN_LENGTH, error_msg)

    def _draw_slider(self, cr, win_w):
        top_rounded_rect(cr, 0, 0, win_w, SLIDER_H, 16)
        _set_color(cr, DARK_CARD)
        cr.fill()

        label = f"VOL  {self._volume}%"
        _set_color(cr, CYAN)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(16)
        ext = cr.text_extents(label)
        cr.move_to(20, SLIDER_H / 2 - ext.height / 2 - ext.y_bearing)
        cr.show_text(label)

        # Two buttons on the right: CHANGE PIN + DONE
        done_w, done_h, done_y = 90, 56, 22
        chg_w = 110
        btn_gap = 8
        done_x = win_w - done_w - 16
        chg_x  = done_x - btn_gap - chg_w

        right_margin = win_w - chg_x + 8
        track_x = 160
        track_w = win_w - track_x - right_margin
        track_cy = SLIDER_H // 2
        self._track_x = track_x
        self._track_w = track_w

        # Track background
        rounded_rect(cr, track_x, track_cy - 4, track_w, 8, 4)
        _set_color(cr, GRAY_MID)
        cr.fill()

        # Filled portion
        fill_w = int(track_w * self._volume / 100)
        if fill_w > 0:
            rounded_rect(cr, track_x, track_cy - 4, fill_w, 8, 4)
            _set_color(cr, CYAN)
            cr.fill()

        # Thumb
        thumb_cx = track_x + int(track_w * self._volume / 100)
        _set_color(cr, CYAN)
        cr.arc(thumb_cx, track_cy, 14, 0, 2 * math.pi)
        cr.fill()
        _set_color(cr, WHITE)
        cr.arc(thumb_cx, track_cy, 14, 0, 2 * math.pi)
        cr.set_line_width(1.5)
        cr.stroke()

        # CHANGE PIN button
        rounded_rect(cr, chg_x, done_y, chg_w, done_h, BTN_R)
        _set_color(cr, CYAN_DIM)
        cr.set_line_width(1.5)
        cr.stroke()
        draw_text_centered(cr, "CHANGE PIN", chg_x + chg_w / 2, done_y + done_h / 2,
                           font="Sans", size=12, bold=True, rgba=CYAN_DIM)
        self._btn_rects['change_pin'] = (chg_x, done_y, chg_w, done_h)

        # DONE button
        rounded_rect(cr, done_x, done_y, done_w, done_h, BTN_R)
        _set_color(cr, GRAY_MID)
        cr.set_line_width(1.5)
        cr.stroke()
        draw_text_centered(cr, "DONE", done_x + done_w / 2, done_y + done_h / 2,
                           font="Sans", size=14, bold=True, rgba=GRAY_MID)
        self._btn_rects['done'] = (done_x, done_y, done_w, done_h)

    # --- Event handlers ---

    def _hit(self, name, ex, ey):
        r = self._btn_rects.get(name)
        if r is None:
            return False
        x, y, w, h = r
        return x <= ex <= x + w and y <= ey <= y + h

    def _on_press(self, _widget, event):
        ex, ey = event.x, event.y

        if self._phase == PHASE_MENU:
            if self._hit('power_off', ex, ey):
                self._do_poweroff()
            elif self._hit('restart', ex, ey):
                self._do_restart()
            elif self._hit('change_volume', ex, ey):
                self._goto_pin()

        elif self._phase == PHASE_PIN:
            for digit in '0123456789':
                if self._hit(digit, ex, ey):
                    self._pin_digit(digit)
                    return
            if self._hit('backspace', ex, ey):
                self._pin_backspace()

        elif self._phase == PHASE_SLIDER:
            if self._hit('done', ex, ey):
                Gtk.main_quit()
            elif self._hit('change_pin', ex, ey):
                self._goto_change_pin()
            elif (self._track_x <= ex <= self._track_x + self._track_w and
                  0 <= ey <= SLIDER_H):
                self._vol_dragging = True
                self._update_vol_from_x(ex)
                self._reset_slider_timer()

        elif self._phase == PHASE_CHANGE_PIN:
            if not self._change_success:
                for digit in '0123456789':
                    if self._hit(digit, ex, ey):
                        self._change_digit(digit)
                        return
                if self._hit('backspace', ex, ey):
                    self._change_backspace()

    def _on_release(self, _widget, _event):
        if self._phase == PHASE_SLIDER and self._vol_dragging:
            self._vol_dragging = False
            self._apply_volume()
            self._reset_slider_timer()

    def _on_motion(self, _widget, event):
        if self._phase == PHASE_SLIDER and self._vol_dragging:
            self._update_vol_from_x(event.x)

    # --- Volume helpers ---

    def _update_vol_from_x(self, x):
        vol = max(0, min(100, int((x - self._track_x) / max(1, self._track_w) * 100)))
        if vol != self._volume:
            self._volume = vol
            self.queue_draw()

    def _apply_volume(self):
        subprocess.run(["pactl", "set-sink-volume", SINK_IDENTIFIER,
                        f"{self._volume}%"])
        subprocess.Popen(["python3", "volume-indicator.py", str(self._volume)],
                         env=_clean_env)

    # --- PIN entry helpers ---

    def _pin_digit(self, digit):
        if len(self._pin_entered) < len(self._correct_pin):
            self._pin_entered += digit
            self.queue_draw()
            if len(self._pin_entered) == len(self._correct_pin):
                GLib.timeout_add(80, self._check_pin)

    def _pin_backspace(self):
        self._pin_entered = self._pin_entered[:-1]
        self.queue_draw()

    def _check_pin(self):
        if self._pin_entered == self._correct_pin:
            self._goto_slider()
        else:
            self._pin_error = True
            self._pin_entered = ''
            self.queue_draw()
            GLib.timeout_add(PIN_ERROR_CLEAR_MS, self._clear_pin_error)
        return False

    def _clear_pin_error(self):
        self._pin_error = False
        self.queue_draw()
        return False

    # --- Change-PIN helpers ---

    def _change_digit(self, digit):
        if len(self._change_buf) < PIN_LENGTH:
            self._change_buf += digit
            self.queue_draw()
            if len(self._change_buf) == PIN_LENGTH:
                GLib.timeout_add(80, self._advance_change_pin)

    def _change_backspace(self):
        self._change_buf = self._change_buf[:-1]
        self._change_error = None
        self.queue_draw()

    def _advance_change_pin(self):
        if self._change_step == 'new':
            self._new_pin_first = self._change_buf
            self._change_buf = ''
            self._change_step = 'confirm'
            self._change_error = None
            self.queue_draw()
        else:
            if self._change_buf == self._new_pin_first:
                save_pin(self._new_pin_first)
                self._correct_pin = self._new_pin_first
                self._change_success = True
                self.queue_draw()
                GLib.timeout_add(1200, self._goto_slider_from_change)
            else:
                self._change_error = "PINs don't match — try again"
                self._change_buf = ''
                self._change_step = 'new'
                self._new_pin_first = ''
                self.queue_draw()
        return False

    def _goto_slider_from_change(self):
        self._goto_slider()
        return False

    # --- System actions ---

    def _do_poweroff(self):
        Gtk.main_quit()
        subprocess.Popen(["systemctl", "poweroff"])

    def _do_restart(self):
        Gtk.main_quit()
        subprocess.Popen(["systemctl", "reboot"])


win = PowerMenuWindow()
win.show_all()
Gtk.main()
