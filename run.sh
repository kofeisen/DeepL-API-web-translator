#!/bin/bash
echo "正在启动 DeepL Web 服务..."

# 检查虚拟环境是否存在
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate


# 设置环境变量并运行
export FLASK_APP=deepl_web.py
python -m flask run