import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango, PangoCairo
import cairo
import math

CARD_W   = 560
PADDING  = 36
CORNER   = 28
HEADER_GAP = 18

DARK_CARD = (0.05, 0.05, 0.05, 0.92)
AMBER     = (1.00, 0.75, 0.00, 1.00)
WHITE     = (1.00, 1.00, 1.00, 0.92)


def rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r,  0,            math.pi / 2)
    cr.arc(x + r,     y + h - r, r,  math.pi / 2,  math.pi)
    cr.arc(x + r,     y + r,     r, -math.pi,      -math.pi / 2)
    cr.close_path()


class MaintenanceWindow(Gtk.Window):
    def __init__(self, message):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.message = message
        self.text_w = CARD_W - PADDING * 2
        self.header_h, self.body_h = self._measure()

        win_h = PADDING * 2 + self.header_h + HEADER_GAP + self.body_h
        self.set_default_size(CARD_W, int(win_h))

        self.connect("draw", self.on_draw)

    def _layout(self, cr, font_desc, size, text):
        layout = PangoCairo.create_layout(cr)
        layout.set_width(Pango.units_from_double(self.text_w))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_alignment(Pango.Alignment.CENTER)
        font = Pango.FontDescription(font_desc)
        font.set_size(Pango.units_from_double(size))
        layout.set_font_description(font)
        layout.set_text(text, -1)
        return layout

    def _measure(self):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        cr = cairo.Context(surf)
        header = self._layout(cr, "Sans Bold", 16, "MAINTENANCE")
        body = self._layout(cr, "Sans", 22, self.message)
        return (header.get_pixel_size().height,
                body.get_pixel_size().height)

    def on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        win_w = self.get_allocated_width()
        win_h = self.get_allocated_height()

        rounded_rect(cr, 0, 0, win_w, win_h, CORNER)
        cr.set_source_rgba(*DARK_CARD)
        cr.fill()

        header = self._layout(cr, "Sans Bold", 16, "MAINTENANCE")
        cr.set_source_rgba(*AMBER)
        cr.move_to(PADDING, PADDING)
        PangoCairo.show_layout(cr, header)

        body = self._layout(cr, "Sans", 22, self.message)
        cr.set_source_rgba(*WHITE)
        cr.move_to(PADDING, PADDING + self.header_h + HEADER_GAP)
        PangoCairo.show_layout(cr, body)


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else ""
    win = MaintenanceWindow(message)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
