#!/bin/bash

PORT=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1)

if [ -z "$PORT" ]; then
    echo "デバイスが見つかりません"
    exit 1
fi

echo "=== $PORT に接続 (終了: Ctrl+A → K) ==="
screen "$PORT" 115200
