import ure
import utime
from machine import PWM, Pin as _Pin

class udp_read:

    def __init__(self):
        self.power_coefficient  = 0         #積算電力量係数
        self.power_unit         = 0.0       #積算電力量単位
        self.instant_power      = [0 , '']   #瞬間電力値
        self.instant_amp_r      = ''        #瞬間電流値(R相)
        self.instant_amp_t      = ''        #瞬間電流値(T相)
        self.total_power        = [0 , '']   #積算電力量
        self.price              = {10:0, 20:0, 30:0}

    def calTepco(self, power):
        base = 1430
        money = base
        if power > 120:
            money += 120 * 19.88
        else:
            money += power * 19.88

        if power > 300:
            money += (300-120)*26.48
        elif power>120:
            money += (power-120)*26.48

        if power > 300:
            money += (power-300)*30.57
        
        return int(money)

    # UDPデータの解析関数
    def read(self, udp_line):
        self.type = ''
        if udp_line is None:
            return
        if ure.match('ERXUDP' , udp_line.strip()) :
            print(udp_line) ####テスト用
            cols = ''
            res = ''
            cols_header = ure.compile(' ')
            cols = cols_header.split(udp_line.strip())
            if len(cols) == 9 :
                res = cols[8]   # UDP受信データ部分

                esv = res[20:20+2]
                epc = res[24:24+2]
                if ure.match(esv,'71') and ure.match(epc,'E5'):
                    result = int(res[-2:], 16)
                    print('-- 積算電力履歴収集日１設定 E5 result --' + str(result))
                if ure.match(esv,'72') and ure.match(epc,'E2'):
                    days = int(res[30:30 + 2], 16)
                    power = int(res[32:32 + 8],16) * self.power_coefficient * self.power_unit
                    power2 = self.total_power[0] - power
                    _price = self.calTepco(int(power2))
                    self.price[days] = _price
                    print('-- 積算電力量計測値履歴１ E2 result -- days:' + str(days) + ' 料金:' + str(_price) + '円 計算電力量:' + str(power2) +'kWh')
                if ure.match(esv,'72') and ure.match(epc,'E8'):
                    r = int(res[-8:-4], 16)
                    if r == 0x7ffe:
                        r = 0
                    t = int(res[-4:], 16)
                    if t == 0x7ffe:
                        t = 0
                    print('-- 瞬間電力量 E8 result --' + str((r+t)/10.0) + 'A')

#                print(res) ####テスト用
                if ure.match('028801' , res[8:8+6]) and ure.match('72' , res[20:20+2]) :    # スマートメーター(028801)から来た応答(72)なら
                    if len(res) == 36 :
                        if ure.match('D3' , res[24:24+2]) : # D3なら積算電力量係数
                            self.type = 'D3'
                            self.power_coefficient = int(res[-8:], 16)
                            print('-- 積算電力量係数(coefficient) -- ' + str(self.power_coefficient))
                        if ure.match('E7' , res[24:24+2]) : # E7なら瞬時電力値（単独）
                            self.type = 'E7'
                            new_power = int(res[-8:] , 16)
                            if self.instant_power[0] + 200 < new_power:
                                _spk = PWM(_Pin(2), freq=1800, duty=512)
                                utime.sleep_ms(500)
                                _spk.deinit()
                                print("A")
                            if self.instant_power[0] - 200 > new_power:
                                _spk = PWM(_Pin(2), freq=1000, duty=512)
                                utime.sleep_ms(500)
                                _spk.deinit()
                                print("B")
                            self.instant_power[0] = new_power
                            #self.instant_power[0] = int(res[-8:] , 16)
                            self.instant_power[1] = utime.time()
                            print('-- 瞬時電力量 -- ' + str(self.instant_power[0]) + ' W  ' + str(self.instant_power[1]))
                    elif len(res) == 30 :
                        if ure.match('E1' , res[24:24+2]) : # E1なら積算電力量単位
                            self.type = 'E1'
                            if ure.match('00' , res[-2:]) :
                                PowerUnit = 1.0
                            elif ure.match('01' , res[-2:]) :
                                PowerUnit = 0.1
                            elif ure.match('02' , res[-2:]) :
                                PowerUnit = 0.01
                            elif ure.match('03' , res[-2:]) :
                                PowerUnit = 0.001
                            elif ure.match('04' , res[-2:]) :
                                PowerUnit = 0.0001
                            elif ure.match('0A' , res[-2:]) :
                                PowerUnit = 10.0
                            elif ure.match('0B' , res[-2:]) :
                                PowerUnit = 100.0
                            elif ure.match('0C' , res[-2:]) :
                                PowerUnit = 1000.0
                            elif ure.match('0D' , res[-2:]) :
                                PowerUnit = 10000.0
                            self.power_unit = PowerUnit
                            print('-- 積算電力量単位(power_unit) --' + str(self.power_unit))
                    elif len(res) == 48 :
                        if ure.match('E7' , res[24:24+2]) : # E7なら瞬時電力値（電流値とセットの場合）
                            self.type = 'E7'
                            self.instant_power[0] = int(res[-20:-12] , 16)
                            self.instant_power[1] = utime.time()
                            print('-- 瞬時電力値 -- ' + str(self.instant_power[0]) + ' W  ' + str(self.instant_power[1]))
                        if ure.match('E8' , res[36:36+2]) : # E8なら瞬時電流値（電力値とセットの場合）
                            self.instant_amp_r = int(res[-8:-8+4] , 16) * 0.1
                            self.instant_amp_t = int(res[-4:] , 16) * 0.1
                    elif len(res) == 50 :
                        if ure.match('EA' , res[24:24+2]) : # EAなら定時積算電力量 一斉同報ではなく要求分の応答
                            self.type = 'EA72'
                            date_YYYY_ea = int(res[-22:-22+4] , 16)
                            date_MM_ea = int(res[-18:-18+2] , 16)
                            date_DD_ea = int(res[-16:-16+2] , 16)
                            date_hh_ea = int(res[-14:-14+2] , 16)
                            date_mm_ea = int(res[-12:-12+2] , 16)
                            date_ss_ea = int(res[-10:-10+2] , 16)
                            self.total_power[0] = int(res[-8:] , 16) * self.power_coefficient * self.power_unit
                            self.total_power[1] = '%04d-%02d-%02d %02d:%02d:%02d'%(date_YYYY_ea, date_MM_ea, date_DD_ea, date_hh_ea, date_mm_ea, date_ss_ea)
                            print('-- 定時積算電力量 --' + str(self.total_power[0]) + ' kWh  ' + str(self.total_power[1]))
                elif ure.match('028801' , res[8:8+6]) and ure.match('73' , res[20:20+2]) :    # スマートメーター(028801)から来た一斉通知(73)なら
                    print('028801 73')
                    if len(res) == 76 :
                        if ure.match('EA' , res[24:24+2]) : # EAなら定時積算電力量 ※売電側も一緒に送られてくるので注意！
                            if self.power_coefficient != 0 and self.power_unit != 0.0 :
                                self.type = 'EA73'
                                date_YYYY_ea = int(res[28:28+4] , 16)
                                date_MM_ea = int(res[32:32+2] , 16)
                                date_DD_ea = int(res[34:34+2] , 16)
                                date_hh_ea = int(res[36:36+2] , 16)
                                date_mm_ea = int(res[38:38+2] , 16)
                                date_ss_ea = int(res[40:40+2] , 16)
                                self.total_power[0] = int(res[42:42+8] , 16) * self.power_coefficient * self.power_unit
                                self.total_power[1] = '%04d-%02d-%02d %02d:%02d:%02d'%(date_YYYY_ea, date_MM_ea, date_DD_ea, date_hh_ea, date_mm_ea, date_ss_ea)
                                print('--' + str(self.total_power[0]) + ' kWh  ' + str(self.total_power[1]))
