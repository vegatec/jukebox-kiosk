import gi
import subprocess
import re
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import cairo

def get_volume_info():
    try:
        # Get volume and mute status
        output = subprocess.check_output(["pactl", "get-sink-mute", "@DEFAULT_SINK@"]).decode()
        is_muted = "yes" in output.lower()
        
        vol_output = subprocess.check_output(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]).decode()
        volume = int(re.search(r'(\d+)%', vol_output).group(1))
        return volume, is_muted
    except:
        return 0, False

class VolumeWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_default_size(200, 200)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        self.volume, self.is_muted = get_volume_info()
        self.connect("draw", self.on_draw)
        GLib.timeout_add(1200, Gtk.main_quit)

    def on_draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        
        cx, cy = 100, 100
        
        # Background Circle
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.7)
        cr.arc(cx, cy, 60, 0, 2 * 3.14159)
        cr.fill()

        cr.set_line_width(10)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        if self.is_muted:
            # Draw Red Mute Ring
            cr.set_source_rgba(1.0, 0.3, 0.3, 0.9)
            cr.arc(cx, cy, 50, 0, 2 * 3.14159)
            cr.stroke()
            # Draw an X in the middle
            cr.move_to(cx-15, cy-15); cr.line_to(cx+15, cy+15)
            cr.move_to(cx+15, cy-15); cr.line_to(cx-15, cy+15)
            cr.stroke()
        else:
            # Draw Gray Track
            cr.set_source_rgba(0.3, 0.3, 0.3, 0.5)
            cr.arc(cx, cy, 50, 0, 2 * 3.14159)
            cr.stroke()
            # Draw Blue Volume Arc
            cr.set_source_rgba(0, 0.6, 1.0, 0.9)
            angle = (self.volume / 100) * 6.2831
            cr.arc(cx, cy, 50, -1.5708, -1.5708 + angle)
            cr.stroke()

win = VolumeWindow()
win.show_all()
Gtk.main()
