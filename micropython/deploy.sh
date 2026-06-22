#!/bin/bash
set -e

SRC=.
FILES=(
    "boot.py       :/boot.py"
    "main.py       :/main.py"
    "wisun_udp.py  :/wisun_udp.py"
    "lib/st7789.py :/lib/st7789.py"
    "lib/axp192.py :/lib/axp192.py"
)
SECRETS=(
    "wisun_set_m.txt :/wisun_set_m.txt"
)

usage() {
    echo "Usage: $0 [options]"
    echo "  -a           全ファイルを転送してリセット"
    echo "  -m           main.py のみ転送（-l と併用可）"
    echo "  -l           lib/*.py のみ転送（-m と併用可）"
    echo "  -s           シークレット(wisun_set_m.txt)も転送"
    echo "  -n           転送後にリセットしない"
    echo "  -r           リセットのみ（転送なし）"
    echo "  -h           このヘルプを表示"
    exit 0
}

do_reset=true
only_main=false
only_lib=false
only_all=false
only_reset=false
with_secrets=false

if [ $# -eq 0 ]; then
    usage
fi

while getopts "amlsnrh" opt; do
    case $opt in
        a) only_all=true ;;
        m) only_main=true ;;
        l) only_lib=true ;;
        s) with_secrets=true ;;
        n) do_reset=false ;;
        r) only_reset=true ;;
        h) usage ;;
    esac
done

cd "$(dirname "$0")"

echo "=== M5StickC PLUS deploy ==="

if $only_reset; then
    echo "  reset..."
    mpremote reset
    echo "=== done ==="
    exit 0
fi

# /lib ディレクトリが存在しない場合だけ作成（エラーは無視）
mpremote exec "import uos; uos.mkdir('/lib')" 2>/dev/null || true

transfer() {
    local src="$1"
    local dst="$2"
    echo "  cp ${src} → ${dst}"
    mpremote cp "${src}" "${dst}"
}

if $only_all; then
    for entry in "${FILES[@]}"; do
        transfer $entry
    done
else
    if $only_main; then
        transfer main.py :/main.py
    fi
    if $only_lib; then
        transfer lib/st7789.py :/lib/st7789.py
        transfer lib/axp192.py :/lib/axp192.py
    fi
fi

if $with_secrets; then
    for entry in "${SECRETS[@]}"; do
        transfer $entry
    done
fi

if $do_reset; then
    echo "  reset..."
    mpremote reset
fi

echo "=== done ==="
