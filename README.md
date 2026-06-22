# M5StickC PLUS Wi-SUN HAT

M5StickC PLUS と ROHM 製 Wi-SUN 通信モジュール「BP35A1」を使って、家庭用スマートメーターから電力データを取得・表示するプログラムです。

- **ファームウェア**: 標準 MicroPython v1.28.0 (Generic ESP32)
- **ハードウェア**: M5StickC PLUS + Wi-SUN HATキット（BP35A1）

---

## 機能

- 瞬間電力消費量（W）をリアルタイム表示（大フォント・右寄せ）
- 10日・20日・30日分の積算電力コスト（円）を表示
- 日時表示（NTP 同期）
- MQTT でデータ送信
- 電力が警告値を超えると表示が赤色になり、バックライトが点灯
- データ受信が途絶えると表示を消灯（TIMEOUT 秒後）

---

## ディレクトリ構成

```
m5stickc_wisun_hat/
├── micropython/          # MicroPython 用ファイル一式
│   ├── deploy.sh         # デバイスへのファイル転送スクリプト
│   ├── monitor.sh        # シリアルモニタ起動スクリプト
│   ├── boot.py           # 起動直後に実行（mpremote 割り込み用）
│   ├── main.py           # メインアプリ
│   ├── wisun_udp.py      # WiSUN UDP データ解析
│   ├── wisun_set_m.txt   # 認証情報設定ファイル（gitignore 対象）
│   └── lib/
│       ├── st7789.py     # ST7789V2 LCD ドライバ
│       └── axp192.py     # AXP192 電源管理 IC ドライバ
└── uiflow/               # 旧 UIFlow 版（参考用）
```

---

## セットアップ

### 必要ツール

```bash
pip install esptool mpremote
```

### MicroPython ファームウェア書き込み

[MicroPython 公式](https://micropython.org/download/ESP32_GENERIC/) から `ESP32_GENERIC-*.bin` をダウンロード。

```bash
# フラッシュ全消去
esptool.py --port /dev/ttyUSB0 --baud 115200 erase_flash

# ファームウェア書き込み
esptool.py --port /dev/ttyUSB0 --baud 115200 write_flash -z 0x1000 ESP32_GENERIC-*.bin
```

> WSL 環境では `usbipd-win` で USB デバイスをアタッチすると `/dev/ttyUSB0` として認識されます。

### 設定ファイルの準備

`micropython/wisun_set_m.txt` を作成し、以下の内容を記入します：

```
AMPERE_RED:0.7
AMPERE_LIMIT:50
TIMEOUT:30
BRID:<32文字のB-rootID>
BRPSWD:<12文字のB-rootパスワード>
ESP_NOW:0
WIFI_SSID:<WiFi SSID>
WIFI_PASS:<WiFiパスワード>
```

> このファイルは認証情報を含むため `.gitignore` に登録されています。

### ファイル転送

```bash
cd micropython

# 初回: /lib ディレクトリを作成
mpremote exec "import uos; uos.mkdir('/lib')"

# 全ファイルを転送（wisun_set_m.txt を含む）
./deploy.sh -a -s
```

---

## deploy.sh の使い方

```bash
cd micropython

./deploy.sh          # 引数なし → ヘルプ表示
./deploy.sh -a       # 全ファイル転送 + リセット
./deploy.sh -m       # main.py のみ転送 + リセット（最もよく使う）
./deploy.sh -l       # lib/*.py のみ転送 + リセット
./deploy.sh -m -l    # main.py と lib/*.py を転送 + リセット
./deploy.sh -s       # -a/-m/-l と組み合わせ: wisun_set_m.txt も転送
./deploy.sh -n       # 転送後にリセットしない
./deploy.sh -r       # リセットのみ
```

---

## monitor.sh の使い方

```bash
cd micropython
./monitor.sh
# → /dev/ttyUSB0 または /dev/ttyACM0 を自動検出して screen を起動
```

終了: `Ctrl+A` → `K`

---

## MQTT データ仕様

MQTT ブローカーのアドレスは `main.py` 内の `MQTTClient(...)` で設定します。

| トピック | 内容 | 更新タイミング |
|----------|------|----------------|
| `Home/Wi-Sun-Hat/Instant-Energy` | 瞬間電力 (W) | E7 受信時（数十秒ごと） |
| `Home/Wi-Sun-Hat/Accumulated-Cost` | 積算コスト (円) | E2 受信時（10d/20d/30d 順に） |

**ペイロード例:**
```
# Instant-Energy
2024-06-21 14:30:00 1234

# Accumulated-Cost
2024-06-21 14:30:00 10d 3850
```

受信確認:
```bash
mosquitto_sub -h <ブローカーIP> -t 'Home/Wi-Sun-Hat/#'
```

---

## ボタン操作

| ボタン | 操作 |
|--------|------|
| ボタン A（前面・M5 ロゴ） | バックライト ON/OFF の切り替え |
| ボタン B（側面） | 表示の上下反転（設置向きに合わせて） |

---

## ハードウェアメモ

| 項目 | 詳細 |
|------|------|
| LCD | ST7789V2、240×135px（横長） |
| WiSUN UART | TX=GPIO0, RX=GPIO26, 115200bps（HAT rev0.2） |
| ボタン A | GPIO37（入力専用ピン・PULL_UP 不可） |
| ボタン B | GPIO39（入力専用ピン・PULL_UP 不可） |
