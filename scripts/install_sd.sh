#!/bin/bash
# RKLLM NPU WebUI - 文生图依赖一键安装
# 用法: bash scripts/install_sd.sh [venv路径]
#
# 说明:
#   - diffusers / ruamel.yaml 从 PyPI 安装
#   - rknnlite 不在 PyPI，从系统 dist-packages 复制（与 venv 同为 cp311-aarch64）
#   - 模型文件较大，不放入 git；请从 HuggingFace 下载后放到 SD_MODEL_DIR
set -e

VENV="${1:-/opt/rkllama/.venv}"
PY="$VENV/bin/python"
SITE="$VENV/lib/python3.11/site-packages"

echo "==> 安装 diffusers（PyPI）"
"$PY" -m pip install "diffusers>=0.30,<0.41"

echo "==> 安装 ruamel.yaml（rknnlite 依赖）"
"$PY" -m pip install ruamel.yaml

echo "==> 安装 rknnlite（不在 PyPI，从系统 dist-packages 复制）"
if [ -d /usr/lib/python3/dist-packages/rknnlite ]; then
    cp -r /usr/lib/python3/dist-packages/rknnlite "$SITE/rknnlite"
    cp -r /usr/lib/python3/dist-packages/rknnlite-*.egg-info "$SITE/" 2>/dev/null || true
    echo "    rknnlite 已复制到 venv"
else
    echo "!! 未找到系统 rknnlite (/usr/lib/python3/dist-packages/rknnlite)"
    echo "    请先从 rknn-toolkit2 发布包安装 rknnlite 2.3.0"
    exit 1
fi

echo "==> 校验导入"
"$PY" -c "import rknnlite; import diffusers; import torch; print('SD 依赖 OK')"

echo
echo "完成。模型文件请从以下地址下载后放置到 /opt/anything_v5："
echo "  https://huggingface.co/AKHYui/anything-v5-rknn-512"
echo "  目录结构：text_encoder/  unet/  vae_decoder/  tokenizer/  scheduler/"