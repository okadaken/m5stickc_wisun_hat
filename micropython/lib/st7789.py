import framebuf
import utime
from machine import Pin, SPI, I2C

WHITE     = 0xFFFF
BLACK     = 0x0000
RED       = 0xF800
GREEN     = 0x07E0
LIGHTGREY = 0xC618

class ST7789:
    X_OFFSET = 40   # landscape: chip col 40-279 (240px幅)
    Y_OFFSET = 53   # landscape_left default

    def __init__(self):
        self.cs  = Pin(5,  Pin.OUT, value=1)
        self.dc  = Pin(23, Pin.OUT, value=1)
        self.rst = Pin(18, Pin.OUT, value=1)
        self.spi = SPI(1, baudrate=27000000, polarity=0, phase=0,
                       bits=8, firstbit=SPI.MSB, sck=Pin(13), mosi=Pin(15))
        self.width  = 240
        self.height = 135
        self._enable_power()
        self.rst.on(); utime.sleep_ms(5)
        self.rst.off(); utime.sleep_ms(20)
        self.rst.on(); utime.sleep_ms(150)
        self._init_display()

    def _enable_power(self):
        i2c = I2C(1, scl=Pin(22), sda=Pin(21), freq=100000)
        i2c.writeto_mem(0x34, 0x28, b'\xff')
        reg = i2c.readfrom_mem(0x34, 0x12, 1)[0]
        i2c.writeto_mem(0x34, 0x12, bytes([reg | 0x0c]))

    def _write_cmd(self, cmd):
        self.dc.off(); self.cs.off()
        self.spi.write(bytes([cmd]))
        self.cs.on()

    def _write_data(self, buf):
        self.dc.on(); self.cs.off()
        self.spi.write(buf)
        self.cs.on()

    def _set_window(self, x, y, w, h):
        x0 = x + self.X_OFFSET;  x1 = x0 + w - 1
        y0 = y + self.Y_OFFSET;  y1 = y0 + h - 1
        self._write_cmd(0x2a)
        self._write_data(bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._write_cmd(0x2b)
        self._write_data(bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))

    def _init_display(self):
        self._write_cmd(0x11); utime.sleep_ms(120)
        self._write_cmd(0x3A); self._write_data(b'\x05')
        self._write_cmd(0xB2); self._write_data(b'\x0c\x0c\x00\x33\x33')
        self._write_cmd(0xB7); self._write_data(b'\x35')
        self._write_cmd(0xBB); self._write_data(b'\x19')
        self._write_cmd(0xC0); self._write_data(b'\x2c')
        self._write_cmd(0xC2); self._write_data(b'\x01')
        self._write_cmd(0xC3); self._write_data(b'\x12')
        self._write_cmd(0xC4); self._write_data(b'\x20')
        self._write_cmd(0xC6); self._write_data(b'\x0f')
        self._write_cmd(0xD0); self._write_data(b'\xa4\xa1')
        self._write_cmd(0xE0)
        self._write_data(b'\xd0\x04\x0d\x11\x13\x2b\x3f\x54\x4c\x18\x0d\x0b\x1f\x23')
        self._write_cmd(0xE1)
        self._write_data(b'\xd0\x04\x0c\x11\x13\x2c\x3f\x44\x51\x2f\x1f\x1f\x20\x23')
        self._write_cmd(0x21)           # Display Inversion ON（色の正常化）
        self._write_cmd(0x36); self._write_data(b'\xa0')  # MADCTL landscape_left (MY+MV)
        self._write_cmd(0x29); utime.sleep_ms(10)
        self.fill(BLACK)

    def fill(self, color):
        self._set_window(0, 0, self.width, self.height)
        self._write_cmd(0x2c)
        self.dc.on(); self.cs.off()
        # RGB565: highバイト先に送る（ESP32 little-endianのframebufとは逆順）
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        row = bytes([hi, lo] * self.width)
        for _ in range(self.height):
            self.spi.write(row)
        self.cs.on()

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        self._set_window(x, y, w, h)
        self._write_cmd(0x2c)
        self.dc.on(); self.cs.off()
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        row = bytes([hi, lo] * w)
        for _ in range(h):
            self.spi.write(row)
        self.cs.on()

    def line(self, x0, y0, x1, y1, color):
        if y0 == y1:
            self.fill_rect(x0, y0, abs(x1 - x0) + 1, 1, color)
        elif x0 == x1:
            self.fill_rect(x0, y0, 1, abs(y1 - y0) + 1, color)

    def text(self, s, x, y, color, bg=BLACK):
        tmp = bytearray(128)  # 8×8×2
        out = bytearray(128)
        fb = framebuf.FrameBuffer(tmp, 8, 8, framebuf.RGB565)
        for i, ch in enumerate(s):
            fb.fill(bg)
            fb.text(ch, 0, 0, color)
            # framebuf はlittle-endian格納 → SPI用にバイトスワップ
            for j in range(0, 128, 2):
                out[j]   = tmp[j + 1]
                out[j+1] = tmp[j]
            self._set_window(x + i * 8, y, 8, 8)
            self._write_cmd(0x2c)
            self._write_data(out)

    def show(self):
        pass  # 直接描画のためフラッシュ不要

    def set_rotation(self, landscape_left=False):
        if landscape_left:
            self._write_cmd(0x36); self._write_data(b'\xa0')
            self.X_OFFSET = 40
            self.Y_OFFSET = 53
        else:
            self._write_cmd(0x36); self._write_data(b'\x60')
            self.X_OFFSET = 40
            self.Y_OFFSET = 52
        self.fill(BLACK)

    def big_text(self, s, x, y, color, bg=BLACK, scale=3):
        tmp = bytearray(128)
        fb  = framebuf.FrameBuffer(tmp, 8, 8, framebuf.RGB565)
        cw  = 8 * scale
        buf = bytearray(cw * cw * 2)
        fhi = (color >> 8) & 0xFF;  flo = color & 0xFF
        bhi = (bg    >> 8) & 0xFF;  blo = bg    & 0xFF
        for i, c in enumerate(s):
            fb.fill(0)
            fb.text(c, 0, 0, color)
            for row in range(8):
                for col in range(8):
                    j = (row * 8 + col) * 2
                    hi, lo = (fhi, flo) if (tmp[j+1] << 8) | tmp[j] else (bhi, blo)
                    for dr in range(scale):
                        for dc in range(scale):
                            off = ((row * scale + dr) * cw + col * scale + dc) * 2
                            buf[off] = hi; buf[off+1] = lo
            self._set_window(x + i * cw, y, cw, cw)
            self._write_cmd(0x2c)
            self._write_data(buf)
