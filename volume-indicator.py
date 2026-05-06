import gi
import subprocess
import re
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import cairo
import math

def get_volume_info():
    try:
        output = subprocess.check_output(["pactl", "get-sink-mute", "@DEFAULT_SINK@"]).decode()
        is_muted = "yes" in output.lower()

        vol_output = subprocess.check_output(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]).decode()
        volume = int(re.search(r'(\d+)%', vol_output).group(1))
        return volume, is_muted
    except:
        return 0, False

SIZE   = 320
CX, CY = SIZE // 2, SIZE // 2
TRACK_R = 100
CORNER  = 40   # rounded corner radius for the background card

def rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r,     r,  -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r,  0,             math.pi / 2)
    cr.arc(x + r,     y + h - r, r,  math.pi / 2,   math.pi)
    cr.arc(x + r,     y + r,     r, -math.pi,       -math.pi / 2)
    cr.close_path()

class VolumeWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_default_size(SIZE, SIZE)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.volume, self.is_muted = get_volume_info()
        self.connect("draw", self.on_draw)
        GLib.timeout_add(1400, Gtk.main_quit)

    def on_draw(self, _widget, cr):
        # Clear to fully transparent
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        cr.set_operator(cairo.OPERATOR_OVER)

        # Semi-transparent dark card with rounded corners
        rounded_rect(cr, 0, 0, SIZE, SIZE, CORNER)
        cr.set_source_rgba(0.05, 0.05, 0.05, 0.78)
        cr.fill()

        cr.set_line_width(14)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        if self.is_muted:
            # Red mute ring
            cr.set_source_rgba(1.0, 0.3, 0.3, 0.9)
            cr.arc(CX, CY, TRACK_R, 0, 2 * math.pi)
            cr.stroke()
            # X mark
            cr.move_to(CX - 22, CY - 22); cr.line_to(CX + 22, CY + 22)
            cr.move_to(CX + 22, CY - 22); cr.line_to(CX - 22, CY + 22)
            cr.stroke()
        else:
            # Gray background track
            cr.set_source_rgba(0.3, 0.3, 0.3, 0.5)
            cr.arc(CX, CY, TRACK_R, 0, 2 * math.pi)
            cr.stroke()

            # Cyan volume arc
            cr.set_source_rgba(0.0, 1.0, 1.0, 0.95)
            angle = (self.volume / 100) * 2 * math.pi
            cr.arc(CX, CY, TRACK_R, -math.pi / 2, -math.pi / 2 + angle)
            cr.stroke()

            # Percentage label centered
            cr.set_source_rgba(0.0, 1.0, 1.0, 1.0)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(52)
            label = f"{self.volume}%"
            ext = cr.text_extents(label)
            cr.move_to(CX - ext.width / 2 - ext.x_bearing,
                       CY - ext.height / 2 - ext.y_bearing)
            cr.show_text(label)

win = VolumeWindow()
win.show_all()
Gtk.main()
