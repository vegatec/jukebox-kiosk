import gi
import subprocess
import re
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import math

MODULE_SIZE = 8
PADDING     = 20
CORNER      = 24


def get_physical_ip():
    try:
        result = subprocess.run(
            ['ip', 'route', 'get', '8.8.8.8'],
            capture_output=True, text=True, check=True
        )
        match = re.search(r'src (\S+)', result.stdout)
        if match:
            return match.group(1)
    except Exception:
        pass
    return '127.0.0.1'


def build_qr_matrix(data):
    import qrcode
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.get_matrix()


def measure_text(text, font_size):
    """Measure text width using a throw-away Cairo surface."""
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    ctx  = cairo.Context(surf)
    ctx.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(font_size)
    ext = ctx.text_extents(text)
    return ext.width, ext.height


def rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r,  0,            math.pi / 2)
    cr.arc(x + r,     y + h - r, r,  math.pi / 2,  math.pi)
    cr.arc(x + r,     y + r,     r, -math.pi,      -math.pi / 2)
    cr.close_path()


class QRWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        ip       = get_physical_ip()
        self.url = f"http://{ip}:3000/remote-control"

        try:
            self.matrix = build_qr_matrix(self.url)
            n           = len(self.matrix)
            self.qr_px  = n * MODULE_SIZE

            text_w, _  = measure_text(self.url, 12)
            self.win_w = max(self.qr_px + PADDING * 2,
                             int(text_w) + PADDING * 2 + 10)
            self.win_h = self.qr_px + PADDING * 2 + 32
        except Exception:
            self.matrix = None
            self.qr_px  = 0
            self.win_w  = 420
            self.win_h  = 100

        self.set_default_size(self.win_w, self.win_h)
        self._dismissible = False
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._on_click)
        self.connect("draw", self.on_draw)
        GLib.timeout_add(10000, self._allow_dismiss)
        GLib.timeout_add(20000, Gtk.main_quit)

    def _allow_dismiss(self):
        self._dismissible = True
        return False

    def _on_click(self, *_):
        if self._dismissible:
            Gtk.main_quit()

    def on_draw(self, _widget, cr):
        # Fully transparent window background
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Dark card with rounded corners
        rounded_rect(cr, 0, 0, self.win_w, self.win_h, CORNER)
        cr.set_source_rgba(0.07, 0.07, 0.07, 0.92)
        cr.fill()

        if self.matrix:
            qr_x = (self.win_w - self.qr_px) // 2
            qr_y = PADDING

            # White quiet zone behind the QR modules
            cr.set_source_rgba(1, 1, 1, 1)
            cr.rectangle(qr_x, qr_y, self.qr_px, self.qr_px)
            cr.fill()

            # Dark modules
            cr.set_source_rgba(0.05, 0.05, 0.05, 1)
            for ri, row in enumerate(self.matrix):
                for ci, cell in enumerate(row):
                    if cell:
                        cr.rectangle(
                            qr_x + ci * MODULE_SIZE,
                            qr_y + ri * MODULE_SIZE,
                            MODULE_SIZE, MODULE_SIZE,
                        )
            cr.fill()

            # Cyan URL label centered below QR
            cr.set_source_rgba(0.0, 1.0, 1.0, 1.0)
            cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12)
            ext = cr.text_extents(self.url)
            cr.move_to(
                self.win_w / 2 - ext.width / 2 - ext.x_bearing,
                qr_y + self.qr_px + 22,
            )
            cr.show_text(self.url)
        else:
            cr.set_source_rgba(1, 0.4, 0.4, 1)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(14)
            msg = "Run: sudo apt install python3-qrcode"
            ext = cr.text_extents(msg)
            cr.move_to(
                self.win_w / 2 - ext.width / 2 - ext.x_bearing,
                self.win_h / 2 - ext.height / 2 - ext.y_bearing,
            )
            cr.show_text(msg)


win = QRWindow()
win.show_all()
Gtk.main()
