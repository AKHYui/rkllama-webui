# RKLLM NPU WebUI

面向瑞芯微 RK3588 系列开发板（Rock-5T 等）的 **RKLLM NPU 大模型 Web 界面**。基于 FastAPI + SQLite 构建，通过 `llm_demo`（RKNN rkllm 工具链的演示程序）驱动 NPU 上的 .rkllm 模型，提供多会话聊天、模型挂载、知识库（RAG）、驱动路径配置等功能。

> 本项目在开发板 Linux 上运行，Web 界面任意设备浏览器访问。

---

## 功能特性

- 💬 **多会话聊天**：创建/删除会话、会话历史、SSE 流式输出、重新生成、导出聊天记录
- 🔐 **登录认证**：默认账号 `admin` / `admin123`，支持修改密码，会话级 token 校验，登录随机验证码（防暴力破解）
- 🧩 **模型挂载**：模型不再写死，可在设置里增删改模型配置（文件路径、总上下文 ≤16K、单次回复量、**温度/核采样/重复惩罚**、引擎类型），保存时自动校验文件存在性
- ⚙️ **驱动挂载**：可在设置里修改 `llm_demo` 可执行文件路径，方便部署环境差异
- 📚 **知识库（RAG）**：上传 txt/md 或粘贴文本，`bge-small-zh` ONNX 向量化 + ChromaDB 检索，每个会话可绑定不同知识库，自动把检索片段注入对话
- 🎛️ **采样参数**：temperature / top_p / top_k / repeat_penalty 实时调整
- 🧠 **系统提示词**：全局系统提示词 + 自定义提示词库（预设/新建/编辑/删除/激活）
- ⚡ **引擎管理**：NPU 进程常驻、会话切换自动重启、一键强制重启引擎
- 🌐 **外部调用（OpenAI 兼容）**：提供 `/v1/chat/completions`、`/v1/models` 接口，在「更多 → 外部调用」创建 API-Key 后，可用 OpenAI SDK、Chatbox、LobeChat 等外部工具直接调用板子上的大模型

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11、FastAPI、uvicorn、starlette、slowapi（限流） |
| 存储 | SQLite（会话/消息/模型/知识库/设置） |
| 聊天 | SSE 流式输出，`llm_demo` 子进程 stdin/stdout 通信 |
| 向量库 | ChromaDB 1.4 + onnxruntime 1.24，模型 `BAAI/bge-small-zh-v1.5`（ONNX，512 维） |
| 前端 | 内联单页应用（Tailwind + marked + highlight.js + KaTeX），无构建步骤 |

## 目录结构

```
rkllama-webui/
├── main.py                 # 入口：组装 FastAPI、中间件、注册路由
├── config.py               # 全局配置：默认模型种子、采样参数、知识库参数、路径
├── database.py             # SQLite：建表、迁移、各实体 CRUD
├── npu.py                  # llm_demo 子进程管理（常驻、会话切换重启）
├── knowledge.py            # 向量模块：bge-small-zh 推理、分块、ChromaDB 检索
├── engine_llama.py         # llama.cpp 引擎（预留，需自行补齐 LLAMA_CLI 等配置）
├── frontend.py             # 前端单页应用（HTML/JS/CSS）
├── routes/
│   ├── auth.py             # 登录/登出/改密
│   ├── chat.py             # 聊天 SSE + 知识库注入
│   ├── models.py           # 模型列表/挂载 CRUD/切换/采样
│   ├── sessions.py         # 会话管理
│   ├── system_prompt.py    # 系统提示词
│   ├── prompts.py          # 提示词库
│   ├── knowledge.py        # 知识库 CRUD/文档入库/检索/绑定
│   └── driver.py           # llm_demo 路径配置
├── static/                 # 前端静态资源（tailwind/marked/katex 等）
└── requirements.txt        # 完整依赖（开发板 pip freeze 导出）
```

## 环境要求

- **硬件**：RK3588 系列开发板（Rock-5T 等），NPU 算力 ≥6 TOPS
- **系统**：aarch64 Linux（如 Radxa OS / Debian）
- **依赖**：
  - Python 3.11
  - `llm_demo`（rkllm-toolkit 演示程序，默认 `/usr/local/bin/llm_demo`，可在"驱动挂载"中修改）
  - .rkllm 格式模型文件（如 `Qwen3-4B-rk3588-w8a8-opt-1-hybrid-ratio-1.0.rkllm`）
  - （可选，启用知识库）`BAAI/bge-small-zh-v1.5` ONNX 模型

## 部署安装（开发板）

```bash
cd /opt/rkllama
# 1. 系统依赖（供部分源码包编译）
sudo apt update && sudo apt install -y build-essential python3-dev

# 2. 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 拉取代码（已在此目录时用 git pull）
git clone https://github.com/AKHYui/rkllama-webui.git .
git pull
```

### 知识库（RAG）环境准备（可选）

启用知识库需要向量模型。板子通常无法直连 HuggingFace，推荐走国内镜像：

```bash
source .venv/bin/activate

# 方式一：HF 镜像下载原始模型
mkdir -p /opt/rkllama/models
HF_ENDPOINT=https://hf-mirror.com python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='BAAI/bge-small-zh-v1.5', local_dir='/opt/rkllama/models/bge-small-zh')"

# 方式二：也可用 modelscope
# pip install modelscope && modelscope download --model=BAAI/bge-small-zh-v1.5 --local_dir /opt/rkllama/models/bge-small-zh
```

将模型导出为 ONNX（需 `onnx`、`onnxscript`，一次性操作）：

```bash
pip install onnx onnxscript optimum
# 使用 torch 旧版导出器（dynamo=False + opset 17），输出到 /opt/rkllama/models/bge-small-zh-onnx
# 目录需包含 model.onnx 和 tokenizer.json（实现见 knowledge.py 的加载逻辑）
```

> 未安装向量组件或模型时，知识库功能自动降级：文档入库会提示"向量库组件未安装或模型缺失"，其余功能不受影响。

## 运行

```bash
cd /opt/rkllama
source .venv/bin/activate
python main.py
```

- 服务监听 `0.0.0.0:8000`，浏览器访问 `http://<开发板IP>:8000`
- 默认登录：`admin` / `admin123`（建议登录后立即修改密码）
- 首次启动自动初始化 SQLite（含旧库迁移），并从 `config.MODELS` 导入默认模型

## llm_demo 采样参数补丁（模型级采样参数生效前提）

RKNN rkllm-toolkit 的 `llm_demo` 原版把采样参数**写死在代码里**（temperature=0.8、top_p=0.95、top_k=1、repeat_penalty=1.1、frequency/presence=0），命令行传参会被忽略。因此 WebUI 的模型级采样参数需要补丁版 `llm_demo`。

> ⚠️ **版本限制**：本仓库提供的 llm_demo 增加传参方案**仅支持 rknn-llm（https://github.com/airockchip/rknn-llm）的 v1.3.0 版本**。其他版本源码结构不同，需按对应版本自行适配补丁。

### 快速使用（已编译二进制）

`deploy/llm_demo` 是已编译好的补丁版可执行文件（基于 rknn-llm v1.3.0 编译），**仅在 ROCK5T 开发板（RK3588 / aarch64 Linux）上测试通过**。如需快速使用：

```bash
# 备份原二进制后直接替换
cp /usr/local/bin/llm_demo /usr/local/bin/llm_demo.orig
mv /usr/local/bin/llm_demo /usr/local/bin/llm_demo.running   # 服务运行中时先改名再放新文件
cp deploy/llm_demo /usr/local/bin/llm_demo
chmod +x /usr/local/bin/llm_demo
```

> 在其他硬件/系统上使用前，建议重新编译（见下方源码编译），以匹配你的运行环境。

### 源码编译

本仓库已提供补丁源码 `deploy/llm_demo.cpp`（新增可选参数解析，不传时行为与原版一致）。在开发板上重新编译替换：

```bash
# 定位 rkllm-toolkit 源码目录（本板在 /opt/rknn-llm-release-v1.3.0）
INCLUDE=/opt/rknn-llm-release-v1.3.0/rkllm-runtime/Linux/librkllm_api/include
LIB=/opt/rknn-llm-release-v1.3.0/rkllm-runtime/Linux/librkllm_api/aarch64

# 备份原二进制与源码
cp /usr/local/bin/llm_demo /usr/local/bin/llm_demo.orig
cp /opt/rknn-llm-release-v1.3.0/examples/rkllm_api_demo/deploy/src/llm_demo.cpp{,.orig}

# 用补丁版覆盖源码并编译
cp deploy/llm_demo.cpp /opt/rknn-llm-release-v1.3.0/examples/rkllm_api_demo/deploy/src/llm_demo.cpp
g++ -std=c++11 -O2 -o llm_demo \
    /opt/rknn-llm-release-v1.3.0/examples/rkllm_api_demo/deploy/src/llm_demo.cpp \
    -I"$INCLUDE" -L"$LIB" -lrkllmrt

# 替换（若服务正在运行会报 Text file busy，先 mv 再 cp）
mv /usr/local/bin/llm_demo /usr/local/bin/llm_demo.running
mv llm_demo /usr/local/bin/llm_demo
chmod +x /usr/local/bin/llm_demo
```

补丁后的参数协议：

```
llm_demo model_path max_new_tokens max_context_len \
        [temperature] [top_p] [top_k] [repeat_penalty] \
        [frequency_penalty] [presence_penalty]
```

- `frequency_penalty` / `presence_penalty`：RKLLM API **支持**（`RKLLMParam` 字段），原版 demo 写死为 0；补丁版已可从命令行传入，WebUI 默认传 0（全局 `SAMPLING_PARAMS` 可调）
- 未使用补丁版时，模型级采样参数不会真正生效（仍为 demo 内置值）

## 使用说明

### 聊天

- 左侧"新建聊天"创建会话；顶部下拉框切换模型
- 输入框回车发送，SSE 流式输出；回复下方可"重新生成"
- 右上角可导出当前会话（JSON）

### 模型挂载（更多 → 模型挂载）

- 增删改模型配置：标识、名称、文件路径、总上下文（1-16384）、单次回复量（≤总上下文）、**采样参数**（温度 0.1-2.0、Top-P 0-1、重复惩罚 1.0-2.0）、引擎类型
- 采样参数可选：留空则使用全局采样参数（config.SAMPLING_PARAMS）；新模型默认 温度0.85 / Top-P 0.9 / 重复惩罚1.25
- 每个模型的采样参数在引擎启动时自动携带，切换模型即生效
- 保存校验：总上下文不超过 16K、单次回复量不超过上下文、模型文件必须存在（可勾选"跳过文件存在校验"用于开发机）
- 当前正在使用的模型不可删除

> ⚠️ **重要**：RKNN 的 `llm_demo` 原版将采样参数写死（忽略命令行参数）。本仓库提供了补丁版源码 `deploy/llm_demo.cpp`，需重新编译替换后，上述模型级采样参数才能真正生效（见下文"llm_demo 补丁"）。

### 驱动挂载（更多 → 驱动挂载）

- 配置 `llm_demo` 可执行文件路径（绝对路径或 PATH 命令名）
- 保存时校验可执行性（可勾选跳过）；修改后重启引擎生效

### 知识库（更多 → 知识库）

1. 新建知识库 → 进入文档管理
2. 上传 txt/md 文件或粘贴文本入库（自动分块：约 400 字符 + 100 重叠）
3. 用"检索测试"验证召回效果
4. 在顶部"知识库"下拉绑定到当前会话
5. 之后该会话的提问会自动检索 top-3 片段并注入 `【知识库参考】` 上下文

### 采样参数与系统提示词

- 顶部 ⚙ 设置抽屉可改采样参数、系统提示词、提示词库
- 采样参数修改后会自动重启引擎生效

## 配置项（config.py）

| 项 | 默认值 | 说明 |
|---|---|---|
| `MODELS` | 7 个示例模型 | 首次启动写入数据库的种子数据，之后以数据库为准 |
| `SAMPLING_PARAMS` | temp=0.85, top_p=0.9, top_k=1, rp=1.25, freq=0, pres=0 | 全局采样参数；模型挂载未单独配置时使用 |
| `KB_CHUNK_SIZE` / `KB_CHUNK_OVERLAP` | 400 / 100 | 知识库分块大小与重叠 |
| `KB_TOP_K` | 3 | 检索注入片段数 |
| `EMBED_MODEL_DIR` | `/opt/rkllama/models/bge-small-zh-onnx` | 向量模型目录（Windows 开发机自动回退本地 `models/`） |
| `CHROMA_DIR` | `/opt/rkllama/chroma_db` | ChromaDB 持久化目录 |
| `DB_FILE` | `chat_history.db` | SQLite 文件（相对路径，随工作目录） |
| `SESSION_SECRET_FILE` | `/opt/rkllama/.session_secret` | Session 密钥文件（Windows 开发机自动回退本地） |

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/auth/captcha` | 获取登录验证码（返回 id + 图片） |
| POST | `/api/auth/login` `/api/auth/logout` | 登录/登出 |
| GET/POST | `/api/sessions` | 会话列表/创建 |
| GET/DELETE | `/api/sessions/{id}` | 会话详情/删除 |
| POST | `/api/chat` | 聊天（SSE） |
| GET/POST/PUT/DELETE | `/api/models` | 模型列表/挂载 CRUD |
| POST | `/api/switch` | 切换模型 |
| GET/POST | `/api/sampling` | 采样参数 |
| GET/POST | `/api/system-prompt` | 系统提示词 |
| GET/POST/PUT/DELETE | `/api/prompts` | 提示词库 |
| GET/POST/PUT/DELETE | `/api/kbs` | 知识库 CRUD |
| POST | `/api/kbs/{id}/documents` | 上传 txt/md |
| POST | `/api/kbs/{id}/documents/text` | 粘贴文本入库 |
| GET/DELETE | `/api/kbs/{id}/documents` | 文档列表/删除 |
| POST | `/api/kbs/{id}/test` | 检索测试 |
| GET/POST | `/api/sessions/{id}/kb` | 会话绑定知识库 |
| GET/PUT | `/api/driver` | llm_demo 路径 |
| POST | `/api/npu/restart` | 重启引擎（兼容旧别名 `/api/reset`） |

除登录接口外均需登录态（Session Cookie）。

## OpenAI 兼容接口（外部调用）

在 WebUI 右上角「更多 → 外部调用」中创建 API-Key，即可用 OpenAI 风格的接口从外部工具调用大模型。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/chat/completions` | 对话补全（支持 `stream: true` 流式 / 非流式） |
| GET | `/v1/models` | 列出可用模型 |

鉴权：`Authorization: Bearer <API-KEY>`（与 WebUI 登录态相互独立）。

```bash
# curl 示例
curl http://<开发板IP>:8000/v1/chat/completions \
  -H "Authorization: Bearer <你的API-KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-4b","messages":[{"role":"user","content":"你好"}]}'

# OpenAI Python SDK 示例
from openai import OpenAI
client = OpenAI(base_url="http://<开发板IP>:8000/v1", api_key="<你的API-KEY>")
resp = client.chat.completions.create(
    model="qwen3-4b",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
```

> ⚠️ **性能说明**：RKLLM 的 `llm_demo` 为有状态常驻进程，而 OpenAI 接口是无状态协议（每次请求带完整 `messages`）。因此每个 `/v1/chat/completions` 请求都会重启 NPU 引擎（清空 KV cache），首包含模型加载延迟（约 10–30 秒，视模型大小）。接口并发量固定为 1：上一个任务未结束时，后续请求会排队等待。

## 本地开发（Windows）

```bash
# 创建 Python 3.11 环境（任意目录，避免写入 C 盘）
conda create -p .conda python=3.11 -y
.conda\python.exe -m pip install fastapi uvicorn slowapi itsdangerous python-multipart
.conda\python.exe -m uvicorn main:app --port 8000
```

- Windows 开发机无 `llm_demo`、无向量组件：服务可正常启动，聊天会提示引擎未就绪，知识库入库会提示组件缺失——这是预期的降级行为
- 代码已对 Linux 路径做了 Windows 回退（静态目录、session 密钥、模型/向量目录）

## 常见问题

**Q1：日志出现 `onnxruntime ... GPU device discovery failed` 告警？**
无害噪音。RK3588 无 onnxruntime 可识别的 GPU 设备，自动回退 CPU 推理，不影响功能。

**Q2：知识库上传后检索无命中？**
先确认入库是否成功（应提示"已入库 N 个分片"）。可在文档管理用"检索测试"输入相关问题看召回结果。若提示"向量库组件未安装或模型缺失"，说明模型目录 `model.onnx`/`tokenizer.json` 未就绪。

**Q3：重启引擎 404？**
旧页面缓存的 `/api/reset` 已做兼容别名，后端 `/api/npu/restart` 与 `/api/reset` 均可用；如仍 404，强制刷新浏览器（Ctrl+Shift+R）。

**Q4：找不到 `llm_demo`？**
确认已安装 rkllm-toolkit，或到 更多 → 驱动挂载 配置正确路径后重启引擎。

**Q5：模型文件校验失败？**
模型路径为板子上 .rkllm 的绝对路径；在 Windows 开发机上可用"跳过文件存在校验"保存。

## 许可证

本项目仅供学习研究使用。RKLLM / rkllm-toolkit 相关资源归瑞芯微所有，请遵守其许可与使用规范。