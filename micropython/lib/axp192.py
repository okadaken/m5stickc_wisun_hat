from machine import I2C, Pin

class AXP192:
    ADDR = 0x34

    def __init__(self, i2c):
        self.i2c = i2c

    def _write(self, reg, val):
        self.i2c.writeto_mem(self.ADDR, reg, bytes([val]))

    def _read(self, reg):
        return self.i2c.readfrom_mem(self.ADDR, reg, 1)[0]

    def backlight_on(self):
        self._write(0x28, 0xAF)            # LDO2 = 2.8V
        val = self._read(0x12)
        self._write(0x12, val | 0x04)      # LDO2 enable

    def backlight_off(self):
        val = self._read(0x12)
        self._write(0x12, val & ~0x04)     # LDO2 disable
