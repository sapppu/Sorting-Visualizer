"""Minimal ILI9341 driver for MicroPython (320x240 SPI TFT)."""

from machine import Pin, SPI
import framebuf
import ustruct
import utime


class ILI9341:
    def __init__(self, spi, cs, dc, rst, width=320, height=240):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = width
        self.height = height
        self._init_display()

    def _init_display(self):
        self.rst(1); utime.sleep_ms(5)
        self.rst(0); utime.sleep_ms(20)
        self.rst(1); utime.sleep_ms(150)
        for cmd, data, delay in [
            (0x01, None, 150),
            (0x11, None, 500),
            (0x3A, b'\x55', 0),
            (0x36, b'\x28', 0),
            (0x13, None, 0),
            (0x29, None, 100),
        ]:
            self._cmd(cmd, data)
            if delay: utime.sleep_ms(delay)

    def _cmd(self, cmd, data=None):
        self.cs(0); self.dc(0)
        self.spi.write(bytes([cmd]))
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A, ustruct.pack('>HH', x0, x1))
        self._cmd(0x2B, ustruct.pack('>HH', y0, y1))
        self._cmd(0x2C)

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0 or x >= self.width or y >= self.height:
            return
        if x < 0: w += x; x = 0
        if y < 0: h += y; y = 0
        w = min(w, self.width - x)
        h = min(h, self.height - y)
        self._set_window(x, y, x + w - 1, y + h - 1)
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        chunk = bytes([hi, lo]) * min(w, 64)
        self.cs(0); self.dc(1)
        for _ in range(h):
            sent = 0
            while sent < w:
                n = min(w - sent, 64)
                self.spi.write(chunk[:n * 2])
                sent += n
        self.cs(1)

    def rect(self, x, y, w, h, color):
        self.fill_rect(x, y, w, 1, color)
        self.fill_rect(x, y + h - 1, w, 1, color)
        self.fill_rect(x, y, 1, h, color)
        self.fill_rect(x + w - 1, y, 1, h, color)

    def hline(self, x, y, w, color):
        self.fill_rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.fill_rect(x, y, 1, h, color)

    def text(self, string, x, y, color=0xFFFF, bg=0x0000, scale=1):
        """Render text using MicroPython's built-in framebuf font, scaled."""
        n = len(string)
        if n == 0:
            return
        total_w = n * 8
        mono_buf = bytearray(total_w)
        fb = framebuf.FrameBuffer(mono_buf, total_w, 8, framebuf.MONO_VLSB)
        fb.fill(0)
        fb.text(string, 0, 0, 1)
        scaled_w = total_w * scale
        hi_fg = (color >> 8) & 0xFF
        lo_fg = color & 0xFF
        hi_bg = (bg >> 8) & 0xFF
        lo_bg = bg & 0xFF
        row_buf = bytearray(scaled_w * 2)
        for py in range(8):
            for px in range(total_w):
                is_set = fb.pixel(px, py)
                hi = hi_fg if is_set else hi_bg
                lo = lo_fg if is_set else lo_bg
                for sx in range(scale):
                    idx = (px * scale + sx) * 2
                    row_buf[idx] = hi
                    row_buf[idx + 1] = lo
            for sy in range(scale):
                dest_y = y + py * scale + sy
                if 0 <= dest_y < self.height:
                    self._set_window(x, dest_y, x + scaled_w - 1, dest_y)
                    self.cs(0); self.dc(1)
                    self.spi.write(row_buf)
                    self.cs(1)

    def show(self):
        pass
