from machine import I2C, Pin, PWM
import machine
import gc
import utime
import ure
import uos
import _thread
import network
from umqtt.simple import MQTTClient
import ntptime
import wisun_udp
from lib.st7789 import ST7789, WHITE, BLACK, RED, LIGHTGREY
from lib.axp192 import AXP192

# 固定値
GET_COEFFICIENT         = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x01\xD3\x00'
GET_TOTAL_POWER_UNIT    = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x01\xE1\x00'
GET_NOW_PA              = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x02\xE7\x00\xE8\x00'
GET_NOW_P               = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x01\xE7\x00'
GET_TOTAL_POWER_30      = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x01\xEA\x00'

# 変数宣言
SCAN_COUNT  = 6
channel     = ''
panid       = ''
macadr      = ''
lqi         = ''
BRID        = ''
BRPSWD      = ''
WIFI_SSID   = ''
WIFI_PASS   = ''

lcd_mute          = False
data_mute         = False
_rotation         = True    # False=右向き、True=左向き（デフォルト左向き）
_rotation_changed = False
_last_btn_b_ms    = 0
m5type      = 0     # M5StickC固定
np_interval = 5
TIMEOUT        = 30
RESTART_TIMEOUT = 300   # E7未受信でこの秒数(5分)経過後に自動再起動
AMPERE_RED  = 0.7
AMPERE_LIMIT = 30


def localtime_jst():
    t = utime.time() + 9 * 3600
    return utime.localtime(t)


def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    utime.sleep_ms(500)
    wlan.active(True)
    print('>> WiFi connecting to: ' + ssid)
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        for _ in range(30):
            if wlan.isconnected():
                break
            utime.sleep(1)
    if not wlan.isconnected():
        raise OSError('WiFi failed, status=' + str(wlan.status()))
    print('>> WiFi OK: ' + str(wlan.ifconfig()[0]))


def time_count():
    while True:
        t = localtime_jst()
        date_str = '{}-{:02d}-{:02d}'.format(t[0], t[1], t[2])
        time_str = '{:02d}:{:02d}:{:02d}'.format(t[3], t[4], t[5])
        if _lcd_lock.acquire(False):   # 取れなければこの1秒はスキップ
            try:
                lcd.fill_rect(0, 0, 240, 22, BLACK)
                lcd.text(date_str, 2, 7, WHITE)
                lcd.text(time_str, 174, 7, WHITE)
                lcd.show()
            finally:
                _lcd_lock.release()
        utime.sleep(1)


def buttonA_wasPressed():
    global lcd_mute
    if lcd_mute:
        lcd_mute = False
        axp.backlight_on()
    else:
        lcd_mute = True
        axp.backlight_off()


def buttonB_wasPressed():
    global _rotation, _rotation_changed, _last_btn_b_ms
    if _btnB_pin.value() != 0:          # 実際には押されていない（ノイズ除去）
        return
    now = utime.ticks_ms()
    if utime.ticks_diff(now, _last_btn_b_ms) < 500:  # チャタリング防止
        return
    _last_btn_b_ms = now
    _rotation = not _rotation
    _rotation_changed = True


def draw_lcd():
    lcd.fill(BLACK)
    lcd.line(0, 22, 240, 22, LIGHTGREY)
    draw_w()
    lcd.show()


def draw_w():
    global data_mute, AMPERE_LIMIT, AMPERE_RED
    if data_mute or u.instant_power[0] == 0:
        fc = BLACK
    elif u.instant_power[0] >= AMPERE_LIMIT * AMPERE_RED * 100:
        fc = RED
        if lcd_mute:
            axp.backlight_on()
    else:
        fc = WHITE
        if lcd_mute:
            axp.backlight_off()
    pwr = str(u.instant_power[0])
    _lcd_lock.acquire(True)
    try:
        lcd.fill_rect(0, 24, 240, 111, BLACK)
        # 瞬間電力値 右寄せ（scale=4 = 1文字32px幅）
        label = pwr + 'W'
        lcd.big_text(label, 240 - len(label) * 32, 38, fc, scale=4)
        # 積算コスト 縦並び右寄せ（固定10文字 → x=160で右端ぴったり）
        def _yen(d, v):
            return '{}d:{:5d} Yen'.format(d, v) if v else '{}d: ----  --'.format(d)
        lcd.text(_yen(10, u.price[10]), 136, 86, LIGHTGREY)
        lcd.text(_yen(20, u.price[20]), 136, 98, LIGHTGREY)
        lcd.text(_yen(30, u.price[30]), 136, 110, LIGHTGREY)
        lcd.show()
    finally:
        _lcd_lock.release()


def wisun_set_filechk():
    global AMPERE_LIMIT, AMPERE_RED, TIMEOUT, BRID, BRPSWD, WIFI_SSID, WIFI_PASS

    scanfile_flg = False
    for file_name in uos.listdir('/'):
        if file_name == 'wisun_set_m.txt':
            scanfile_flg = True

    if scanfile_flg:
        print('>> found [wisun_set_m.txt] !')
        with open('/wisun_set_m.txt', 'r') as f:
            for file_line in f:
                filetxt = file_line.strip().split(':')
                if filetxt[0] == 'AMPERE_RED':
                    if float(filetxt[1]) >= 0 and float(filetxt[1]) <= 1:
                        AMPERE_RED = float(filetxt[1])
                        print('- AMPERE_RED: ' + str(AMPERE_RED))
                elif filetxt[0] == 'AMPERE_LIMIT':
                    if int(filetxt[1]) >= 20:
                        AMPERE_LIMIT = int(filetxt[1])
                        print('- AMPERE_LIMIT: ' + str(AMPERE_LIMIT))
                elif filetxt[0] == 'TIMEOUT':
                    if int(filetxt[1]) > 0:
                        TIMEOUT = int(filetxt[1])
                        print('- TIMEOUT: ' + str(TIMEOUT))
                elif filetxt[0] == 'BRID':
                    BRID = str(filetxt[1])
                    print('- BRID: ' + str(BRID))
                elif filetxt[0] == 'BRPSWD':
                    BRPSWD = str(filetxt[1])
                    print('- BRPSWD: ' + str(BRPSWD))
                elif filetxt[0] == 'WIFI_SSID':
                    WIFI_SSID = str(filetxt[1])
                    print('- WIFI_SSID: ' + str(WIFI_SSID))
                elif filetxt[0] == 'WIFI_PASS':
                    WIFI_PASS = str(filetxt[1])

        if len(BRID) == 32 and len(BRPSWD) == 12 and len(WIFI_SSID) > 0 and len(WIFI_PASS) > 0:
            scanfile_flg = True
        else:
            print('>> [wisun_set_m.txt] Illegal!!')
            scanfile_flg = False
    else:
        print('>> no [wisun_set_m.txt] !')
    return scanfile_flg


def wisun_scan_filechk():
    global channel, panid, macadr, lqi

    scanfile_flg = False
    for file_name in uos.listdir('/'):
        if file_name == 'Wi-SUN_SCAN.txt':
            scanfile_flg = True
    if scanfile_flg:
        print('>> found [Wi-SUN_SCAN.txt] !')
        with open('/Wi-SUN_SCAN.txt', 'r') as f:
            for file_line in f:
                filetxt = file_line.strip().split(':')
                if filetxt[0] == 'Channel':
                    channel = filetxt[1]
                    print('- Channel: ' + channel)
                elif filetxt[0] == 'Pan_ID':
                    panid = filetxt[1]
                    print('- Pan_ID: ' + panid)
                elif filetxt[0] == 'MAC_Addr':
                    macadr = filetxt[1]
                    print('- MAC_Addr: ' + macadr)
                elif filetxt[0] == 'LQI':
                    lqi = filetxt[1]
                    print('- LQI: ' + lqi)
                elif filetxt[0] == 'COEFFICIENT':
                    u.power_coefficient = int(filetxt[1])
                    print('- COEFFICIENT: ' + str(u.power_coefficient))
                elif filetxt[0] == 'UNIT':
                    u.power_unit = float(filetxt[1])
                    print('- UNIT: ' + str(u.power_unit))
        if len(channel) == 2 and len(panid) == 4 and len(macadr) == 16:
            scanfile_flg = True
        else:
            print('>> [Wi-SUN_SCAN.txt] Illegal!!')
            scanfile_flg = False
    else:
        print('>> no [Wi-SUN_SCAN.txt] !')
    return scanfile_flg


_lcd_lock = _thread.allocate_lock()

def readline():
    timeout = 60
    start = utime.time()
    while utime.time() - start < timeout:
        if bp35a1.any():
            return bp35a1.readline()
        utime.sleep_ms(50)
    return None


# メインプログラムはここから

print('>> M5Type = M5StickC')

# 基本設定ファイルチェック
if not wisun_set_filechk():
    raise ValueError('err!! Check [wisun_set_m.txt] and restart!!')

# ハードウェア初期化
_i2c = I2C(1, scl=Pin(22), sda=Pin(21), freq=100000)
axp = AXP192(_i2c)
lcd = ST7789()
axp.backlight_on()

_st_y    = 2   # 次の行のY座標
_st_last = None

def show_status(msg):
    global _st_y, _st_last
    if msg == _st_last:   # 連続する同一メッセージはスキップ（スキャン中の繰り返しなど）
        return
    _st_last = msg
    if _st_y > 126:       # 画面下端に達したら最終行を上書き
        _st_y = 126
        lcd.fill_rect(0, _st_y, 240, 9, BLACK)
    lcd.text(msg, 2, _st_y, WHITE)
    lcd.show()
    _st_y += 10

def _btnA_irq(pin):
    buttonA_wasPressed()

def _btnB_irq(pin):
    buttonB_wasPressed()

_btnA_pin = Pin(37, Pin.IN)
_btnB_pin = Pin(39, Pin.IN)
_btnA_pin.irq(trigger=Pin.IRQ_FALLING, handler=_btnA_irq)
_btnB_pin.irq(trigger=Pin.IRQ_FALLING, handler=_btnB_irq)

# WiFi接続
connect_wifi(WIFI_SSID, WIFI_PASS)
show_status('WiFi connected')
print('>> WiFi init OK')

# UDPデータインスタンス生成
u = wisun_udp.udp_read()
print('>> UDP reader init OK')

# BP35A1 UART設定
bp35a1 = machine.UART(1, tx=0, rx=26)  # Wi-SUN HAT rev0.2用
bp35a1.init(115200, bits=8, parity=None, stop=1, timeout=2000)
show_status('UART ready')
print('>> UART init OK')

# UARTの送受信バッファーの塵データをクリア
utime.sleep(0.5)
if bp35a1.any() != 0:
    dust = bp35a1.read()
bp35a1.write('\r\n')
utime.sleep(1)
if bp35a1.any() != 0:
    dust = bp35a1.read()
bp35a1.write('\r\n')
utime.sleep(0.5)
print('>> UART RX/TX Data Clear!')

# コマンドエコーバックをオンにする
bp35a1.write('SKSREG SFE 1\r\n')
utime.sleep(0.5)
while True:
    line = None
    if bp35a1.any() != 0:
        line = bp35a1.readline()
        print('*')
    if line is not None:
        if ure.match('OK', line.strip()):
            break
print('>> BA35A1 Echo back ON set OK')
utime.sleep(0.5)

# ERXUDPデータ部表示形式をASCIIへ変更
bp35a1.write('ROPT\r\n')
utime.sleep(0.5)
mode_flg = False
while True:
    line = bp35a1.readline()
    if ure.match("OK", line):
        print(' - BP35A1 ASCII mode')
        break

if ure.match("OK 00", line):
    print(' - BP35A1 Binary Mode')
    mode_flg = True
utime.sleep(0.5)

if mode_flg:
    bp35a1.write('WOPT 01\r\n')
    print('>> BP35A1 ASCII mode set')
    utime.sleep(0.5)
    while True:
        line = bp35a1.readline()
        if ure.match("OK", line):
            print('>> BP35A1 ASCII mode set OK')
            break
show_status('BP35A1 ready')

# 以前のPANAセッションを解除
bp35a1.write('SKTERM\r\n')
utime.sleep(0.5)
while True:
    line = bp35a1.readline()
    if ure.match("OK", line):
        print(' -Old Session Clear!')
        break
    elif ure.match("FAIL ER10", line):
        print(' -Non Old Session')
        break
show_status('Session cleared')

# B-root PASSWORDを送信
bp35a1.write("SKSETPWD C " + BRPSWD + "\r\n")
utime.sleep(0.5)
while True:
    line = None
    if bp35a1.any() != 0:
        line = bp35a1.readline()
        print('*')
    if line is not None:
        if ure.match('OK', line.strip()):
            print('>> BA35A1 B-root PASSWORD set OK')
            break
show_status('Password set')
utime.sleep(0.5)

# B-root IDを送信
bp35a1.write("SKSETRBID " + BRID + "\r\n")
utime.sleep(0.5)
while True:
    line = None
    if bp35a1.any() != 0:
        line = bp35a1.readline()
        print('*')
    if line is not None:
        if ure.match('OK', line.strip()):
            print('>> BA35A1 B-root ID set OK')
            break
show_status('B-root ID set')
utime.sleep(1)
gc.collect()

# Wi-SUNチャンネルスキャン（Wi-SUN_SCAN.txtが無い or 異常値の場合）
if not wisun_scan_filechk():
    scanOK = False
    print('>> Activescan start!')
    while not scanOK:
        bp35a1.write("SKSCAN 2 FFFFFFFF " + str(SCAN_COUNT) + "\r\n")
        utime.sleep(0.5)
        show_status('Scanning WiSUN...')
        scanEnd = False
        while not scanEnd:
            line = None
            if bp35a1.any() != 0:
                line = bp35a1.readline()
                print('*')
                show_status('Scanning WiSUN...')
                if line is not None:
                    if ure.match("EVENT 22", line.strip()):
                        print('-')
                        scanEnd = True
                    elif ure.match("Channel:", line.strip()):
                        pickuptext = ure.compile(':')
                        pickt = pickuptext.split(line.strip())
                        channel = str(pickt[1].strip(), 'utf-8')
                        print(" Channel= " + str(channel))
                    elif ure.match("Pan ID:", line.strip()):
                        pickuptext = ure.compile(':')
                        pickt = pickuptext.split(line.strip())
                        panid = str(pickt[1].strip(), 'utf-8')
                        print(" Pan_ID= " + str(panid))
                    elif ure.match("Addr:", line.strip()):
                        pickuptext = ure.compile(':')
                        pickt = pickuptext.split(line.strip())
                        macadr = str(pickt[1].strip(), 'utf-8')
                        print(" MAC_Addr= " + str(macadr))
                    elif ure.match("LQI:", line.strip()):
                        pickuptext = ure.compile(':')
                        pickt = pickuptext.split(line.strip())
                        lqi = str(pickt[1].strip(), 'utf-8')
                        print(" LQI= " + str(lqi))
                    print(line.strip())
            utime.sleep(0.5)
            gc.collect()
            show_status('Scanning WiSUN...')
        SCAN_COUNT += 1

        if SCAN_COUNT > 10:
            show_status('Scan failed! Reboot')
            raise ValueError('Scan retry count over! Please Reboot!')
        elif len(channel) == 2 and len(panid) == 4 and len(macadr) == 16 and len(lqi) == 2:
            show_status('Scan OK')
            with open('/Wi-SUN_SCAN.txt', 'w') as f:
                f.write('Channel:' + str(channel) + '\r\n')
                f.write('Pan_ID:' + str(panid) + '\r\n')
                f.write('MAC_Addr:' + str(macadr) + '\r\n')
                f.write('LQI:' + str(lqi) + '\r\n')
                print('>> [Wi-SUN_SCAN.txt] maked!!')
            print('Scan All Clear!')
            scanOK = True
show_status('PANA connecting...')

# PANA接続処理
while True:
    bp35a1.write("SKSREG S2 " + channel + "\r\n")
    utime.sleep(0.5)
    while True:
        line = None
        if bp35a1.any() != 0:
            line = bp35a1.readline()
            print('*a')
        if line is not None:
            if ure.match('OK', line.strip()):
                break

    bp35a1.write("SKSREG S3 " + panid + "\r\n")
    utime.sleep(0.5)
    while True:
        line = None
        if bp35a1.any() != 0:
            line = bp35a1.readline()
            print('*b')
        if line is not None:
            if ure.match('OK', line.strip()):
                break

    bp35a1.write("SKLL64 " + macadr + "\r\n")
    utime.sleep(0.5)
    while True:
        line = None
        if bp35a1.any() != 0:
            line = bp35a1.readline()
            print('*c')
        if line is not None:
            if len(line.strip()) == 39:
                ipv6Addr = str(line.strip(), 'utf-8')
                print('IPv6 Addr = ' + str(ipv6Addr))
                break

    gc.collect()
    utime.sleep(1)

    bp35a1.write('SKSREG SFE 0\r\n')
    utime.sleep(0.5)
    while True:
        line = bp35a1.readline()
        print(line)
        if ure.match("OK", line):
            print('>> BA35A1 Echo back OFF set OK')
            break

    print('PANA authentication start!!')
    bp35a1.write("SKJOIN " + ipv6Addr + "\r\n")
    utime.sleep(0.1)
    bConnected = False
    while not bConnected:
        line = None
        if bp35a1.any() != 0:
            line = bp35a1.readline()
            print('*d')
            if line is not None:
                if ure.match("EVENT 24", line.strip()):
                    print(">> PANA authentication NG!  ...scan retry")
                    utime.sleep(1)
                    for file_name in uos.listdir('/'):
                        if file_name == 'Wi-SUN_SCAN.txt':
                            uos.remove('/Wi-SUN_SCAN.txt')
                            channel = ''
                            panid = ''
                            macadr = ''
                            u.power_coefficient = 0
                            u.power_unit = 0.0
                    break
                elif ure.match("EVENT 25", line.strip()):
                    print(">> PANA authentication OK!")
                    bConnected = True
                    utime.sleep(1)
                gc.collect()
    if bConnected:
        break
show_status('PANA connected!')
gc.collect()

# ECHONET Lite 積算電力係数(D3)要求
if u.power_coefficient == 0:
    command = bytes('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(ipv6Addr, len(GET_COEFFICIENT)), 'utf-8')
    bp35a1.write(command)
    bp35a1.write(GET_COEFFICIENT)
    print('>> [GET_COEFFICIENT] cmd send')
    utime.sleep(0.5)
    while u.power_coefficient == 0:
        line = None
        if bp35a1.any() != 0:
            line = bp35a1.readline()
            u.read(line)
            if u.type == 'D3':
                with open('/Wi-SUN_SCAN.txt', 'a') as fc:
                    fc.write('COEFFICIENT:' + str(u.power_coefficient) + '\r\n')
        utime.sleep(0.1)
gc.collect()
show_status('Coefficient OK')

# ECHONET Lite 積算電力単位(E1)要求
if u.power_unit == 0.0:
    command = bytes('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(ipv6Addr, len(GET_TOTAL_POWER_UNIT)), 'utf-8')
    bp35a1.write(command)
    bp35a1.write(GET_TOTAL_POWER_UNIT)
    print('>> [GET_TOTAL_POWER_UNIT] cmd send')
    utime.sleep(0.5)
    while u.power_unit == 0.0:
        line = None
        if bp35a1.any() != 0:
            line = bp35a1.readline()
            u.read(line)
            if u.type == 'E1':
                with open('/Wi-SUN_SCAN.txt', 'a') as fu:
                    fu.write('UNIT:' + str(u.power_unit) + '\r\n')
        utime.sleep(0.1)
gc.collect()
show_status('Unit OK')

print('heapmemory= ' + str(gc.mem_free()))

# NTP時刻同期（失敗しても続行）
for _ntp_host in ('jp.pool.ntp.org', 'ntp.nict.jp', '133.243.238.243'):
    try:
        ntptime.host = _ntp_host
        ntptime.settime()
        print('>> RTC init OK via ' + _ntp_host)
        break
    except Exception as e:
        print('>> NTP failed (' + _ntp_host + '): ' + str(e))
else:
    print('>> NTP all failed, continuing without time sync')

# 画面初期化
draw_lcd()
print('>> Disp init OK')

# 時刻表示スレッド起動
_thread.start_new_thread(time_count, ())
print('>> Time Count thread ON')

# タイムカウンタ初期値設定
np_c = utime.time()
tp_c = utime.time()
tp_f = False
last_e7_time = utime.time()

# MQTT接続
mqtt = MQTTClient('m5stickC-Wi-SUN-HAT', '192.168.200.21', 1883)
mqtt.connect()

i = 0
collect_day = 0

# メインループ
while True:
    line = None
    if bp35a1.any() != 0:
        line = bp35a1.readline()
        if line is not None:
            if ure.match("EVENT 27", line.strip()):
                print('>> PANA session terminated (EVENT 27)! Restarting...')
                machine.reset()
            u.read(line)
        if u.type == 'E7':
            last_e7_time = utime.time()
            data_mute = False
            draw_w()
            t = localtime_jst()
            payload = '{}-{:02d}-{:02d} {:02d}:{:02d}:{:02d} {}'.format(
                t[0], t[1], t[2], t[3], t[4], t[5], u.instant_power[0])
            try:
                mqtt.publish(b'Home/Wi-Sun-Hat/Instant-Energy', payload.encode())
            except:
                try: mqtt.connect()
                except: pass
        elif u.type == 'EA72':
            tp_f = True

    if ((utime.time() - tp_c) >= (30 * 60)) or ((not tp_f) and ((utime.time() - tp_c) >= 10)):
        tp_c = utime.time()
        tp_f = False
        utime.sleep(0.5)
    elif (utime.time() - np_c) >= np_interval:
        i += 1
        if i % 5000 == 1:
            command = bytes('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(ipv6Addr, len(GET_TOTAL_POWER_30)), 'utf-8')
            bp35a1.write(command)
            bp35a1.write(GET_TOTAL_POWER_30)
            print('>> [積算電力計測値取得EA] cmd send')
            tp_c = utime.time()
            tp_f = False
            utime.sleep(0.5)
            line = readline()
            if line is not None:
                u.read(line)
        elif i % 5 == 2:
            collect_day += 10
            if collect_day > 30:
                collect_day = 10
                i = 2  # 次サイクルで i=3(E2取得) が実行されるよう調整
            POWER_W = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x61\x01\xE5\x01' + bytes([collect_day])
            command = bytes('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(ipv6Addr, len(POWER_W)), 'utf-8')
            bp35a1.write(command)
            bp35a1.write(POWER_W)
            print('>> [積算履歴収集日１の設定E5] cmd send day:' + str(collect_day))
            np_c = utime.time()
            utime.sleep(0.5)
            line = readline()
            if line is not None:
                u.read(line)
        elif i % 5 == 3:
            POWER_R = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x01\xE2\x00'
            command = bytes('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(ipv6Addr, len(POWER_R)), 'utf-8')
            bp35a1.write(command)
            bp35a1.write(POWER_R)
            print('>> [積算電力量計測値履歴１取得E2] cmd send')
            np_c = utime.time()
            utime.sleep(0.5)
            line = readline()
            if line is not None:
                u.read(line)
            if u.price[collect_day]:
                t = localtime_jst()
                payload = '{}-{:02d}-{:02d} {:02d}:{:02d}:{:02d} {}d {}'.format(
                    t[0], t[1], t[2], t[3], t[4], t[5], collect_day, u.price[collect_day])
                try:
                    mqtt.publish(b'Home/Wi-Sun-Hat/Accumulated-Cost', payload.encode())
                except:
                    try: mqtt.connect()
                    except: pass
        elif i % 5 == 4:
            POWER_R = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x01\xE8\x00'
            command = bytes('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(ipv6Addr, len(POWER_R)), 'utf-8')
            bp35a1.write(command)
            bp35a1.write(POWER_R)
            print('>> [瞬間電流計測値E8] cmd send')
            np_c = utime.time()
            utime.sleep(0.5)
            line = readline()
            if line is not None:
                u.read(line)
        else:
            command = bytes('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(ipv6Addr, len(GET_NOW_P)), 'utf-8')
            bp35a1.write(command)
            bp35a1.write(GET_NOW_P)
            print('>> [瞬間電力計測値] cmd send')
            np_c = utime.time()
            utime.sleep(0.5)

    if not u.instant_power[1] == '':
        if (utime.time() - u.instant_power[1]) >= TIMEOUT:
            if not data_mute:
                data_mute = True
                draw_w()

    if _rotation_changed:
        _rotation_changed = False
        _lcd_lock.acquire(True)
        try:
            lcd.set_rotation(_rotation)
            lcd.line(0, 22, 240, 22, LIGHTGREY)
        finally:
            _lcd_lock.release()
        draw_w()

    if utime.time() - last_e7_time > RESTART_TIMEOUT:
        print('>> No E7 for {}s, restarting...'.format(RESTART_TIMEOUT))
        machine.reset()

    utime.sleep(0.1)
    gc.collect()
