"""
RKLLM NPU WebUI - 前端页面
内联 HTML/JS/CSS 单页应用（Tailwind + marked + highlight.js + KaTeX）。
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["frontend"])

html_content = r"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
        <title>RKLLM Multi-Session Chat</title>
        <script src="/static/tailwind.min.js"></script>
        <script src="/static/marked.min.js"></script>
        <link rel="stylesheet" href="/static/github-dark.min.css">
        <script src="/static/highlight.min.js"></script>
        <link rel="stylesheet" href="/static/katex.min.css">
        <script src="/static/katex.min.js"></script>
        <script src="/static/auto-render.min.js"></script>
        <style>
            html, body { height: 100%; height: 100dvh; }
            @supports (-webkit-touch-callout: none) { body { height: -webkit-fill-available; } }
            ::-webkit-scrollbar { width: 6px; }
            ::-webkit-scrollbar-track { background: transparent; }
            ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
            ::-webkit-scrollbar-thumb:hover { background: #6b7280; }
            .prose pre { padding: 0; background-color: transparent; margin: 0; }
            .prose code { background-color: #374151; padding: 0.1rem 0.3rem; border-radius: 0.25rem; font-size: 0.85em; }
            .prose pre code { padding: 0.8rem; display: block; overflow-x: auto; font-size: 0.85em; line-height: 1.4; }
            .safe-area-bottom { padding-bottom: max(0.75rem, env(safe-area-inset-bottom)); }
            .sidebar-transition { transition: transform 0.3s ease-in-out; }
            .drawer-right { transition: transform 0.3s ease-in-out; }
            /* 系统提示词弹窗样式 */
            .modal-overlay { transition: opacity 0.2s ease-in-out; }
            .modal-content { transition: transform 0.2s ease-in-out, opacity 0.2s ease-in-out; }
            .modal-hidden { opacity: 0; pointer-events: none; }
            .modal-hidden .modal-content { transform: scale(0.95); opacity: 0; }
        </style>
    </head>
    <body class="bg-gray-900 text-gray-100 h-full overflow-hidden flex font-sans">
        
        <!-- 登录遮罩层 -->
        <div id="loginOverlay" class="fixed inset-0 bg-gray-900 z-50 flex items-center justify-center">
            <div class="bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm p-8 border border-gray-700">
                <div class="text-center mb-6">
                    <svg class="w-12 h-12 mx-auto text-blue-500 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <h2 class="text-xl font-bold text-white">RKLLM NPU WebUI</h2>
                    <p class="text-sm text-gray-400 mt-1">请输入密码登录</p>
                </div>
                <div class="space-y-4">
                    <input id="loginUsername" type="text" placeholder="用户名"
                        class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <input id="loginPassword" type="password" placeholder="密码"
                        class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        onkeydown="if(event.key==='Enter')doLogin()">
                    <div class="flex items-center gap-2">
                        <input id="loginCaptcha" type="text" placeholder="验证码" maxlength="4"
                            class="w-full flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase tracking-widest"
                            onkeydown="if(event.key==='Enter')doLogin()">
                        <img id="captchaImg" src="" onclick="refreshCaptcha()" title="看不清？点击刷新"
                            class="h-11 w-24 rounded-lg border border-gray-600 bg-gray-700 cursor-pointer object-cover shrink-0" alt="验证码">
                    </div>
                    <p id="loginError" class="text-red-400 text-sm text-center hidden"></p>
                    <button onclick="doLogin()" id="loginBtn"
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-3 font-medium transition-colors">
                        登 录
                    </button>
                </div>
            </div>
        </div>

        <!-- 修改密码弹窗 -->
        <div id="changePwdModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm border border-gray-700">
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <h3 class="text-lg font-bold text-white">修改密码</h3>
                    <button onclick="closeChangePasswordModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                <div class="p-4 space-y-4">
                    <div>
                        <label class="text-xs text-gray-400 mb-1 block">原密码</label>
                        <input id="oldPassword" type="password" placeholder="输入当前密码"
                            class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-400 mb-1 block">新密码</label>
                        <input id="newPassword" type="password" placeholder="至少4个字符"
                            class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-400 mb-1 block">确认新密码</label>
                        <input id="confirmPassword" type="password" placeholder="再次输入新密码"
                            class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            onkeydown="if(event.key==='Enter')doChangePassword()">
                    </div>
                    <p id="changePwdError" class="text-red-400 text-sm text-center hidden"></p>
                    <p id="changePwdSuccess" class="text-green-400 text-sm text-center hidden"></p>
                    <div class="flex gap-3">
                        <button onclick="closeChangePasswordModal()"
                            class="flex-1 px-4 py-2.5 text-gray-300 hover:text-white hover:bg-gray-700 rounded-lg transition-colors text-sm border border-gray-600">
                            取消
                        </button>
                        <button onclick="doChangePassword()" id="changePwdBtn"
                            class="flex-1 px-4 py-2.5 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors text-sm font-medium">
                            确认修改
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- 系统提示词弹窗 -->
        <div id="systemPromptModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col border border-gray-700">
                <!-- 弹窗头部 -->
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <div>
                        <h3 class="text-lg font-bold text-white">💡 系统提示词设置</h3>
                        <p class="text-xs text-gray-400 mt-1">设置 AI 助手的角色和行为规则，会自动带入每次对话</p>
                    </div>
                    <button onclick="closeSystemPromptModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                
                <!-- 预设快捷按钮（动态加载） -->
                <div id="presetButtons" class="px-4 pt-3 pb-1 flex flex-wrap gap-2">
                    <span class="text-xs text-gray-400 mr-1 self-center">加载中...</span>
                </div>
                
<!-- 文本编辑区 -->
                <div class="flex-1 p-4 min-h-0">
                    <textarea id="systemPromptInput" 
                        class="w-full h-48 bg-gray-900 border border-gray-600 rounded-xl p-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                        placeholder="输入系统提示词，例如：你是一个专业的中文写作助手，擅长润色文章、纠正语法错误..."
                        oninput="updatePromptCount()"></textarea>
                    <div class="flex justify-between items-center mt-2">
                        <span id="promptCount" class="text-xs text-gray-500">0 / 2000 字符</span>
                        <span class="text-xs text-gray-500">建议简洁明了，过长可能影响对话质量</span>
                    </div>
                </div>
                
                <!-- 弹窗底部按钮 -->
                <div class="flex justify-end gap-3 p-4 border-t border-gray-700">
                    <button onclick="closeSystemPromptModal()" 
                        class="px-4 py-2 text-gray-300 hover:text-white hover:bg-gray-700 rounded-lg transition-colors text-sm">
                        取消
                    </button>
                    <button onclick="saveSystemPrompt()" 
                        class="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm font-medium shadow-sm">
                        ✅ 保存提示词
                    </button>
                </div>
            </div>
        </div>

        <!-- 提示词管理弹窗 -->
        <div id="promptManagerModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col border border-gray-700">
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <div>
                        <h3 class="text-lg font-bold text-white">提示词管理</h3>
                        <p class="text-xs text-gray-400 mt-1">管理自定义提示词，点击「使用」设为当前提示词</p>
                    </div>
                    <button onclick="closePromptManagerModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                <div class="p-4 border-b border-gray-700">
                    <button onclick="showNewPromptForm()" class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors">+ 新建提示词</button>
                </div>
                <div id="promptList" class="flex-1 overflow-y-auto p-4 space-y-2"></div>
                <div id="promptEditForm" class="hidden p-4 border-t border-gray-700 bg-gray-750 space-y-3">
                    <input id="promptEditName" type="text" placeholder="提示词名称" class="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500" maxlength="30">
                    <textarea id="promptEditContent" rows="4" placeholder="提示词内容" class="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"></textarea>
                    <div class="flex gap-2">
                        <button id="promptSaveBtn" onclick="savePromptEdit()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors">保存</button>
                        <button onclick="cancelPromptEdit()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg text-sm transition-colors">取消</button>
                        <span id="promptEditId" class="hidden"></span>
                    </div>
                </div>
            </div>
        </div>

        <!-- 模型挂载弹窗 -->
        <div id="modelManagerModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col border border-gray-700">
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <div>
                        <h3 class="text-lg font-bold text-white">模型挂载</h3>
                        <p class="text-xs text-gray-400 mt-1">管理可用的本地模型，切换模型后重新加载引擎生效</p>
                    </div>
                    <button onclick="closeModelManagerModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                <div class="p-4 border-b border-gray-700">
                    <button onclick="showNewModelForm()" class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors">+ 新建模型</button>
                </div>
                <div id="modelList" class="flex-1 overflow-y-auto p-4 space-y-2"></div>
                <div id="modelEditForm" class="hidden p-4 border-t border-gray-700 bg-gray-750 space-y-3">
                    <div class="flex gap-2">
                        <input id="modelEditId" type="text" placeholder="模型标识 (字母/数字/点/下划线/连字符)" class="w-1/2 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500" maxlength="64">
                        <input id="modelEditName" type="text" placeholder="模型名称" class="w-1/2 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500" maxlength="50">
                    </div>
                    <input id="modelEditPath" type="text" placeholder="模型文件路径, 如 /opt/models/xxx.rkllm" class="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <div class="flex gap-2">
                        <input id="modelEditCtx" type="number" min="1" max="16384" placeholder="总上下文 (1-16384)" class="w-1/2 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <input id="modelEditMaxTok" type="number" min="1" max="16384" placeholder="单次回复量 tokens (≤总上下文)" class="w-1/2 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    <div class="flex gap-2">
                        <input id="modelEditTemp" type="number" step="0.05" min="0.1" max="2" placeholder="温度 (默认0.85)" class="w-1/3 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <input id="modelEditTopP" type="number" step="0.05" min="0" max="1" placeholder="Top-P (默认0.9)" class="w-1/3 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <input id="modelEditRepPen" type="number" step="0.05" min="1" max="2" placeholder="重复惩罚 (默认1.25)" class="w-1/3 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    <div class="flex items-center gap-4">
                        <select id="modelEditEngine" class="bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="rkllm">rkllm (NPU 引擎)</option>
                            <option value="llama">llama.cpp 引擎</option>
                        </select>
                        <label class="flex items-center text-xs text-gray-400 gap-2">
                            <input id="modelEditSkip" type="checkbox" class="accent-blue-500"> 跳过文件存在校验
                        </label>
                    </div>
                    <p id="modelEditErr" class="text-red-400 text-sm hidden"></p>
                    <div class="flex gap-2">
                        <button id="modelSaveBtn" onclick="saveModelEdit()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors">保存</button>
                        <button onclick="cancelModelEdit()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg text-sm transition-colors">取消</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- 知识库弹窗 -->
        <div id="knowledgeModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col border border-gray-700">
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <div>
                        <h3 id="kbModalTitle" class="text-lg font-bold text-white">知识库</h3>
                        <p id="kbModalSub" class="text-xs text-gray-400 mt-1">管理知识库文档，绑定到会话后自动检索注入</p>
                    </div>
                    <button onclick="closeKnowledgeModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>

                <!-- 主视图: 知识库列表 -->
                <div id="kbMainView" class="flex-1 flex flex-col min-h-0">
                    <div class="p-4 border-b border-gray-700">
                        <button onclick="showKbForm()" class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors">+ 新建知识库</button>
                    </div>
                    <div id="kbList" class="flex-1 overflow-y-auto p-4 space-y-2"></div>
                    <div id="kbForm" class="hidden p-4 border-t border-gray-700 bg-gray-750 space-y-3">
                        <input id="kbName" type="text" placeholder="知识库名称" class="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500" maxlength="50">
                        <input id="kbDesc" type="text" placeholder="描述 (可选)" class="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500" maxlength="200">
                        <label class="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
                            <input id="kbFullInject" type="checkbox" class="accent-purple-500">
                            <span>全量注入模式（适合角色人格/完整设定类语料：绑定后每轮整份注入对话，不走检索）</span>
                        </label>
                        <p id="kbFormErr" class="text-red-400 text-sm hidden"></p>
                        <div class="flex gap-2">
                            <button id="kbSaveBtn" onclick="saveKb()" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors">保存</button>
                            <button onclick="cancelKbForm()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg text-sm transition-colors">取消</button>
                        </div>
                    </div>
                </div>

                <!-- 文档管理视图 -->
                <div id="kbDocView" class="hidden flex-1 flex flex-col min-h-0">
                    <div class="p-4 border-b border-gray-700 space-y-3">
                        <div class="flex items-center justify-between gap-2">
                            <button onclick="backKbList()" class="text-xs px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg transition-colors border border-gray-600">← 返回</button>
                            <span id="kbDocTitle" class="text-sm text-gray-300"></span>
                            <input type="file" id="kbFileInput" accept=".txt,.md" class="hidden" onchange="uploadKbFile()">
                            <button onclick="document.getElementById('kbFileInput').click()" class="text-xs px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors">上传 txt/md</button>
                        </div>
                        <div class="flex gap-2 items-start">
                            <textarea id="kbPaste" rows="2" placeholder="粘贴文本内容，直接入库..." class="flex-1 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"></textarea>
                            <button onclick="pasteKbText()" class="px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm transition-colors shrink-0">入库</button>
                        </div>
                        <div class="flex gap-2 items-start">
                            <input id="kbTestQuery" type="text" placeholder="输入测试问题，检索最相关的知识片段..." class="flex-1 bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500">
                            <button onclick="testKbQuery()" class="px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm transition-colors shrink-0">检索测试</button>
                        </div>
                        <div id="kbTestResult" class="text-xs space-y-1.5"></div>
                    </div>
                    <div id="kbDocList" class="flex-1 overflow-y-auto p-4 space-y-2"></div>
                </div>
            </div>
        </div>

        <!-- 驱动挂载弹窗 -->
        <div id="driverModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[85vh] flex flex-col border border-gray-700">
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <div>
                        <h3 class="text-lg font-bold text-white">驱动挂载</h3>
                        <p class="text-xs text-gray-400 mt-1">配置 RKNN rkllm 引擎的可执行文件（llm_demo）路径</p>
                    </div>
                    <button onclick="closeDriverModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                <div class="p-4 space-y-3">
                    <label class="text-xs text-gray-400 block">llm_demo 可执行文件路径</label>
                    <input id="driverPath" type="text" placeholder="/usr/local/bin/llm_demo" class="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 text-sm text-gray-100 font-mono focus:outline-none focus:ring-2 focus:ring-orange-500">
                    <label class="flex items-center text-xs text-gray-400 gap-2">
                        <input id="driverSkip" type="checkbox" class="accent-orange-500"> 跳过可执行性校验
                    </label>
                    <p class="text-xs text-gray-500">填写绝对路径或 PATH 中的命令名。保存后下次启动引擎时生效，当前引擎不会自动重启。</p>
                    <p id="driverErr" class="text-red-400 text-sm hidden"></p>
                    <p id="driverSuccess" class="text-green-400 text-sm hidden"></p>
                    <div class="flex gap-2">
                        <button onclick="saveDriver()" class="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg text-sm font-medium transition-colors">保存</button>
                        <button onclick="closeDriverModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg text-sm transition-colors">关闭</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- 会话三点下拉菜单 -->
        <div id="sessionMenuBackdrop" class="fixed inset-0 z-40 hidden" onclick="closeSessionMenu()"></div>
        <div id="sessionMenu" class="hidden fixed z-50 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[180px]">
            <div id="sessionMenuTitle" class="px-3 py-2 text-xs text-gray-400 border-b border-gray-700 truncate"></div>
            <button onclick="sessionMenuKb()" class="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-gray-200 hover:bg-gray-700 text-left transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-purple-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                <span>选择知识库</span>
            </button>
        </div>

        <!-- 知识库绑定弹窗 -->
        <div id="kbBindModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm max-h-[85vh] flex flex-col border border-gray-700">
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <div class="min-w-0">
                        <h3 class="text-lg font-bold text-white">绑定知识库</h3>
                        <p id="kbBindSessionTitle" class="text-xs text-gray-400 mt-1 truncate">会话</p>
                    </div>
                    <button onclick="closeKbBindModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                <div id="kbBindList" class="flex-1 overflow-y-auto p-4 space-y-2"></div>
                <div class="p-4 border-t border-gray-700">
                    <button onclick="saveKbBind()" class="w-full bg-purple-600 hover:bg-purple-700 text-white rounded-lg py-2.5 text-sm font-medium transition-colors">保存</button>
                </div>
            </div>
        </div>

        <!-- 移动端侧边栏遮罩 -->
        <div id="mobileOverlay" class="fixed inset-0 bg-black/50 z-20 hidden md:hidden" onclick="toggleSidebar()"></div>

        <!-- 右侧设置抽屉 -->
        <div id="rightDrawerOverlay" class="fixed inset-0 bg-black/50 z-40 hidden" onclick="closeRightDrawer()"></div>
        <div id="rightDrawer" class="fixed inset-y-0 right-0 w-64 bg-gray-800 border-l border-gray-700 flex flex-col z-50 transform translate-x-full drawer-right shadow-2xl">
            <div class="p-4 border-b border-gray-700 flex justify-between items-center">
                <h2 class="text-lg font-bold text-gray-200">设置</h2>
                <button onclick="closeRightDrawer()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div class="flex-1 p-4 space-y-3">
                <button onclick="closeRightDrawer(); openChangePasswordModal()" class="w-full flex items-center space-x-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors border border-gray-600 hover:border-yellow-500/50 text-left">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-yellow-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0110 0v4"></path></svg>
                    <span class="text-gray-200 font-medium">修改密码</span>
                </button>
                <button onclick="closeRightDrawer(); openPromptManagerModal()" class="w-full flex items-center space-x-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors border border-gray-600 hover:border-cyan-500/50 text-left"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg><span class="text-gray-200 font-medium">提示词管理</span></button>
                <button onclick="closeRightDrawer(); openModelManagerModal()" class="w-full flex items-center space-x-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors border border-gray-600 hover:border-green-500/50 text-left"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg><span class="text-gray-200 font-medium">模型挂载</span></button>
                <button onclick="closeRightDrawer(); openKnowledgeModal()" class="w-full flex items-center space-x-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors border border-gray-600 hover:border-purple-500/50 text-left"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-purple-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg><span class="text-gray-200 font-medium">知识库</span></button>
                <button onclick="closeRightDrawer(); openDriverModal()" class="w-full flex items-center space-x-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors border border-gray-600 hover:border-orange-500/50 text-left"><svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-orange-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="6" rx="2"></rect><rect x="3" y="14" width="18" height="6" rx="2"></rect><line x1="7" y1="7" x2="7" y2="7.01"></line><line x1="7" y1="17" x2="7" y2="17.01"></line></svg><span class="text-gray-200 font-medium">驱动挂载</span></button>
                <button onclick="closeRightDrawer(); doLogout()" class="w-full flex items-center space-x-3 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl transition-colors border border-gray-600 hover:border-red-500/50 text-left">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                    <span class="text-gray-200 font-medium">退出登录</span>
                </button>
            </div>
        </div>

        
        <!-- 左侧会话侧边栏 -->
        <aside id="sidebar" class="fixed md:static inset-y-0 left-0 w-64 bg-gray-800 border-r border-gray-700 flex flex-col z-30 transform -translate-x-full md:translate-x-0 sidebar-transition shrink-0">
            <div class="p-4 border-b border-gray-700 flex justify-between items-center">
                <h2 class="text-lg font-bold text-gray-200">所有对话</h2>
                <button onclick="toggleSidebar()" class="md:hidden text-gray-400 hover:text-white">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div class="p-3">
                <button onclick="createNewSession()" class="w-full flex items-center justify-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2.5 transition-colors shadow-sm">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                    <span>新建聊天</span>
                </button>
            </div>
            <div id="sessionList" class="flex-1 overflow-y-auto p-2 space-y-1"></div>
        </aside>

        <!-- 右侧主聊天区域 -->
        <div class="flex-1 flex flex-col min-w-0 h-full relative">
            <header class="bg-gray-800 border-b border-gray-700 p-3 sm:p-4 flex justify-between items-center shadow-md z-10 shrink-0">
                <div class="flex items-center space-x-2 sm:space-x-3">
                    <button onclick="toggleSidebar()" class="md:hidden text-gray-400 hover:text-white mr-1">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
                    </button>
                    <div id="statusDot" class="w-3 h-3 bg-yellow-500 rounded-full animate-pulse shrink-0" title="正在准备引擎"></div>
                    <div class="relative w-36 sm:w-48">
                        <select id="modelSelect" onchange="handleModelSwitch()" class="block appearance-none w-full bg-gray-700 border border-gray-600 text-white py-1.5 pl-3 pr-8 rounded-lg shadow focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-medium cursor-pointer truncate">
                            <option value="">加载中...</option>
                        </select>
                        <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-300">
                            <svg class="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/></svg>
                        </div>
                    </div>

                    <!-- ========== 新增：系统提示词按钮 ========== -->
                    <button onclick="openSystemPromptModal()" id="systemPromptBtn" class="p-1.5 sm:p-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors border border-gray-600 hover:border-blue-500/50" title="系统提示词设置">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="3"></circle>
                            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                        </svg>
                    </button>
                </div>
                
                <div class="flex items-center space-x-2">
                    <button onclick="exportChat()" class="text-gray-400 hover:text-white p-2 rounded-lg transition-colors" title="导出当前对话">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    </button>
                    <button onclick="toggleRightDrawer()" class="text-gray-400 hover:text-white p-1.5 sm:px-3 sm:py-1.5 rounded-lg font-medium transition-colors flex items-center text-sm border border-gray-600 hover:border-blue-500/50" title="设置">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 sm:mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>
                        <span class="hidden sm:inline">更多</span>
                    </button>
                    <button onclick="resetChat()" id="resetBtn" class="bg-red-500 hover:bg-red-600 text-white p-1.5 sm:px-3 sm:py-1.5 rounded-lg font-medium transition-colors flex items-center shadow-sm text-sm" title="强制重启底层进程">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 sm:mr-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" /></svg>
                        <span class="hidden sm:inline">重启引擎</span>
                    </button>
                </div>
            </header>

            <main id="chatBox" class="flex-1 min-h-0 overflow-y-auto p-3 sm:p-6 md:p-8 space-y-4 sm:space-y-6 scroll-smooth"></main>

            <footer class="bg-gray-800 p-3 sm:p-4 border-t border-gray-700 shrink-0 safe-area-bottom w-full">
                <div class="max-w-4xl mx-auto relative flex items-end bg-gray-700 rounded-xl overflow-hidden border border-gray-600 focus-within:ring-2 focus-within:ring-blue-500 transition-shadow">
                    <textarea id="userInput" rows="1" class="w-full bg-transparent text-white text-base pl-4 pr-12 py-3 focus:outline-none resize-none overflow-y-auto max-h-32 min-h-[48px]" placeholder="输入问题，Enter 发送..."></textarea>
                    <button onclick="sendMessage()" id="sendBtn" class="absolute right-2 bottom-2 p-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-transform active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 transform rotate-90" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" /></svg>
                    </button>
                </div>
            </footer>
        </div>

        <script>
            // --- 全局变量 ---
            let sessions = [];
            let currentSessionId = null;
            let isGenerating = false;
            let currentSystemPrompt = "";
            
            // --- 提示词库 (从 API 加载) ---
            let customPrompts = [];

            async function loadCustomPrompts() {
                try {
                    const res = await fetch('/api/prompts');
                    const data = await res.json();
                    customPrompts = data.prompts || [];
                    renderPresetButtons();
                } catch(e) {
                    console.error("加载提示词库失败:", e);
                }
            }

            function renderPresetButtons() {
                const container = document.getElementById('presetButtons');
                if (!container) return;
                let html = '<span class="text-xs text-gray-400 mr-1 self-center">快速预设:</span>';
                for (const p of customPrompts) {
                    html += '<button onclick="usePresetPrompt(' + p.id + ')" class="text-xs px-2 py-1 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 rounded-full border border-blue-500/30 transition-colors" title="' + escapeHtml(p.name) + '">' + escapeHtml(p.name) + '</button>';
                }
                container.innerHTML = html;
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // --- DOM 元素 ---
            const chatBox = document.getElementById('chatBox');
            const userInput = document.getElementById('userInput');
            const sendBtn = document.getElementById('sendBtn');
            const modelSelect = document.getElementById('modelSelect');
            const statusDot = document.getElementById('statusDot');
            const sessionList = document.getElementById('sessionList');
            const sidebar = document.getElementById('sidebar');
            const mobileOverlay = document.getElementById('mobileOverlay');
            const systemPromptModal = document.getElementById('systemPromptModal');
            const systemPromptInput = document.getElementById('systemPromptInput');

            // --- 侧边栏切换 ---
            function toggleSidebar() {
                sidebar.classList.toggle('-translate-x-full');
                mobileOverlay.classList.toggle('hidden');
            }

            // --- 右侧设置抽屉 ---
            const rightDrawer = document.getElementById('rightDrawer');
            const rightDrawerOverlay = document.getElementById('rightDrawerOverlay');

            function toggleRightDrawer() {
                rightDrawer.classList.toggle('translate-x-full');
                rightDrawerOverlay.classList.toggle('hidden');
            }

            function closeRightDrawer() {
                rightDrawer.classList.add('translate-x-full');
                rightDrawerOverlay.classList.add('hidden');
            }

            // --- 系统提示词相关函数 ---
            async function loadSystemPrompt() {
                try {
                    const res = await fetch('/api/system-prompt');
                    const data = await res.json();
                    currentSystemPrompt = data.content;
                    updatePromptCount();
                } catch(e) {
                    console.error("加载系统提示词失败:", e);
                }
            }
            
            function openSystemPromptModal() {
                systemPromptInput.value = currentSystemPrompt;
                updatePromptCount();
                systemPromptModal.classList.remove('modal-hidden');
            }
            
            function closeSystemPromptModal() {
                systemPromptModal.classList.add('modal-hidden');
            }
            
            function updatePromptCount() {
                const len = systemPromptInput.value.length;
                document.getElementById('promptCount').textContent = `${len} / 2000 字符`;
            }
            
            async function saveSystemPrompt() {
                const content = systemPromptInput.value.trim();
                try {
                    const res = await fetch('/api/system-prompt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        currentSystemPrompt = content;
                        closeSystemPromptModal();
                        // 显示保存成功提示
                        const toast = document.createElement('div');
                        toast.className = 'fixed top-4 right-4 bg-green-600 text-white px-4 py-2 rounded-lg shadow-lg z-50 animate-pulse';
                        toast.textContent = '✅ 系统提示词已保存';
                        document.body.appendChild(toast);
                        setTimeout(() => toast.remove(), 2000);
                    }
                } catch(e) {
                    alert('保存失败: ' + e.message);
                }
            }
            
            function usePresetPrompt(id) {
                const p = customPrompts.find(p => p.id === id);
                if (p) {
                    systemPromptInput.value = p.content;
                    updatePromptCount();
                }
            }
            
            function clearPrompt() {
                systemPromptInput.value = '';
                updatePromptCount();
            }

            // 点击弹窗外部关闭
            systemPromptModal.addEventListener('click', function(e) {
                if (e.target === systemPromptModal) {
                    closeSystemPromptModal();
                }
            });

            // ===== 提示词管理函数 =====
            let editingPromptId = null;
            const promptManagerModal = document.getElementById('promptManagerModal');
            const promptEditForm = document.getElementById('promptEditForm');
            const promptEditName = document.getElementById('promptEditName');
            const promptEditContent = document.getElementById('promptEditContent');
            const promptEditId = document.getElementById('promptEditId');
            const promptSaveBtn = document.getElementById('promptSaveBtn');

            if (promptManagerModal) {
                promptManagerModal.addEventListener('click', function(e) {
                    if (e.target === promptManagerModal) closePromptManagerModal();
                });
            }

            function openPromptManagerModal() {
                loadPromptList();
                promptManagerModal.classList.remove('modal-hidden');
            }
            function closePromptManagerModal() {
                promptManagerModal.classList.add('modal-hidden');
                cancelPromptEdit();
            }

            async function loadPromptList() {
                try {
                    const res = await fetch('/api/prompts');
                    const data = await res.json();
                    customPrompts = data.prompts || [];
                    renderPromptList();
                } catch(e) {
                    console.error("加载提示词失败:", e);
                }
            }

            function renderPromptList() {
                const container = document.getElementById('promptList');
                if (!container) return;
                if (customPrompts.length === 0) {
                    container.innerHTML = '<div class="text-gray-500 text-sm text-center py-8">暂无自定义提示词</div>';
                    return;
                }
                let html = '';
                for (const p of customPrompts) {
                    const preview = p.content.length > 60 ? p.content.substring(0, 60) + '...' : p.content;
                    html += '<div class="bg-gray-700/50 rounded-xl p-3 border border-gray-600 hover:border-cyan-500/50 transition-colors">';
                    html += '<div class="flex justify-between items-start mb-1">';
                    html += '<span class="text-gray-100 font-medium text-sm">' + escapeHtml(p.name) + '</span>';
                    html += '<div class="flex gap-1 shrink-0">';
                    html += '<button onclick="usePrompt(' + p.id + ')" class="text-xs px-2 py-1 bg-cyan-600/30 hover:bg-cyan-600/50 text-cyan-300 rounded border border-cyan-500/30 transition-colors">使用</button>';
                    html += '<button onclick="editPrompt(' + p.id + ')" class="text-xs px-2 py-1 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 rounded border border-blue-500/30 transition-colors">编辑</button>';
                    html += '<button onclick="deletePrompt(' + p.id + ')" class="text-xs px-2 py-1 bg-red-600/30 hover:bg-red-600/50 text-red-300 rounded border border-red-500/30 transition-colors">删除</button>';
                    html += '</div></div>';
                    html += '<div class="text-gray-400 text-xs mt-1">' + escapeHtml(preview) + '</div>';
                    html += '</div>';
                }
                container.innerHTML = html;
            }

            async function usePrompt(id) {
                try {
                    const res = await fetch('/api/prompts/' + id + '/use', { method: 'POST' });
                    const data = await res.json();
                    if (data.status === 'success') {
                        currentSystemPrompt = customPrompts.find(p => p.id === id)?.content || '';
                        showToast(data.message || '已激活');
                        closePromptManagerModal();
                    }
                } catch(e) {
                    alert('激活失败: ' + e.message);
                }
            }

            function showNewPromptForm() {
                editingPromptId = null;
                promptEditId.textContent = '';
                promptEditName.value = '';
                promptEditContent.value = '';
                promptSaveBtn.textContent = '创建';
                promptEditForm.classList.remove('hidden');
            }

            function editPrompt(id) {
                const p = customPrompts.find(p => p.id === id);
                if (!p) return;
                editingPromptId = id;
                promptEditId.textContent = id;
                promptEditName.value = p.name;
                promptEditContent.value = p.content;
                promptSaveBtn.textContent = '更新';
                promptEditForm.classList.remove('hidden');
            }

            function cancelPromptEdit() {
                editingPromptId = null;
                promptEditForm.classList.add('hidden');
            }

            async function savePromptEdit() {
                const name = promptEditName.value.trim();
                const content = promptEditContent.value.trim();
                if (!name || !content) { alert('名称和内容不能为空'); return; }
                try {
                    if (editingPromptId) {
                        const res = await fetch('/api/prompts/' + editingPromptId, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ name, content })
                        });
                        const data = await res.json();
                        if (data.status === 'success') showToast('提示词已更新');
                    } else {
                        const res = await fetch('/api/prompts', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ name, content })
                        });
                        const data = await res.json();
                        if (data.status === 'success') showToast('提示词已创建');
                    }
                    cancelPromptEdit();
                    await loadPromptList();
                    await loadCustomPrompts();
                } catch(e) {
                    alert('保存失败: ' + e.message);
                }
            }

            async function deletePrompt(id) {
                const p = customPrompts.find(p => p.id === id);
                if (!confirm('确定要删除提示词 \"' + (p?.name || '') + '\" 吗？')) return;
                try {
                    const res = await fetch('/api/prompts/' + id, { method: 'DELETE' });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast('已删除');
                        await loadPromptList();
                        await loadCustomPrompts();
                    }
                } catch(e) {
                    alert('删除失败: ' + e.message);
                }
            }

            function showToast(msg) {
                const toast = document.createElement('div');
                toast.className = 'fixed top-4 right-4 bg-green-600 text-white px-4 py-2 rounded-lg shadow-lg z-50 transition-opacity';
                toast.textContent = msg;
                document.body.appendChild(toast);
                setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 2000);
            }

            // ===== 模型挂载函数 =====
            let models = [];
            let editingModelId = null;
            const modelManagerModal = document.getElementById('modelManagerModal');
            const modelEditForm = document.getElementById('modelEditForm');

            if (modelManagerModal) {
                modelManagerModal.addEventListener('click', function(e) {
                    if (e.target === modelManagerModal) closeModelManagerModal();
                });
            }

            function openModelManagerModal() {
                loadModelList();
                modelManagerModal.classList.remove('modal-hidden');
            }
            function closeModelManagerModal() {
                modelManagerModal.classList.add('modal-hidden');
                cancelModelEdit();
            }

            async function loadModelList() {
                try {
                    const res = await fetch('/api/models');
                    const data = await res.json();
                    models = data.models || [];
                    renderModelList(data.current);
                } catch(e) {
                    console.error("加载模型失败:", e);
                }
            }

            function renderModelList(currentId) {
                const container = document.getElementById('modelList');
                if (!container) return;
                if (models.length === 0) {
                    container.innerHTML = '<div class="text-gray-500 text-sm text-center py-8">暂无挂载模型，点击「新建模型」添加</div>';
                    return;
                }
                let html = '';
                for (const m of models) {
                    const isCurrent = m.model_id === currentId;
                    const engineLabel = m.engine === 'llama' ? 'llama.cpp' : 'rkllm';
                    html += '<div class="bg-gray-700/50 rounded-xl p-3 border border-gray-600 hover:border-blue-500/50 transition-colors">';
                    html += '<div class="flex justify-between items-start mb-1">';
                    html += '<div class="flex items-center gap-2 min-w-0">';
                    html += '<span class="text-gray-100 font-medium text-sm truncate">' + escapeHtml(m.name) + '</span>';
                    if (isCurrent) html += '<span class="text-[10px] px-1.5 py-0.5 bg-blue-600/40 text-blue-300 rounded border border-blue-500/40 shrink-0">当前</span>';
                    html += '</div>';
                    html += '<div class="flex gap-1 shrink-0">';
                    html += '<button onclick="editModel(\'' + m.model_id + '\')" class="text-xs px-2 py-1 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 rounded border border-blue-500/30 transition-colors">编辑</button>';
                    html += '<button onclick="deleteModel(\'' + m.model_id + '\')" class="text-xs px-2 py-1 bg-red-600/30 hover:bg-red-600/50 text-red-300 rounded border border-red-500/30 transition-colors">删除</button>';
                    html += '</div></div>';
                    html += '<div class="text-gray-400 text-xs mt-1 font-mono truncate">' + escapeHtml(m.path) + '</div>';
                    html += '<div class="flex flex-wrap gap-2 mt-1.5 text-xs text-gray-400">';
                    html += '<span class="text-cyan-300/80 bg-cyan-600/20 px-1.5 py-0.5 rounded border border-cyan-500/20">' + engineLabel + '</span>';
                    html += '<span>上下文: ' + m.ctx_max + '</span><span>单次回复: ' + m.max_tokens + ' tokens</span>';
                    if (m.temperature != null) html += '<span>温度: ' + m.temperature + '</span>';
                    if (m.top_p != null) html += '<span>Top-P: ' + m.top_p + '</span>';
                    if (m.repeat_penalty != null) html += '<span>重复惩罚: ' + m.repeat_penalty + '</span>';
                    html += '</div>';
                    html += '</div>';
                }
                container.innerHTML = html;
            }

            function showNewModelForm() {
                editingModelId = null;
                document.getElementById('modelEditId').value = '';
                document.getElementById('modelEditName').value = '';
                document.getElementById('modelEditPath').value = '';
                document.getElementById('modelEditCtx').value = '4096';
                document.getElementById('modelEditMaxTok').value = '1024';
                document.getElementById('modelEditTemp').value = '0.85';
                document.getElementById('modelEditTopP').value = '0.9';
                document.getElementById('modelEditRepPen').value = '1.25';
                document.getElementById('modelEditEngine').value = 'rkllm';
                document.getElementById('modelEditSkip').checked = false;
                document.getElementById('modelEditErr').classList.add('hidden');
                document.getElementById('modelSaveBtn').textContent = '新建';
                modelEditForm.classList.remove('hidden');
            }

            function editModel(id) {
                const m = models.find(x => x.model_id === id);
                if (!m) return;
                editingModelId = id;
                document.getElementById('modelEditId').value = m.model_id;
                document.getElementById('modelEditName').value = m.name;
                document.getElementById('modelEditPath').value = m.path;
                document.getElementById('modelEditCtx').value = m.ctx_max;
                document.getElementById('modelEditMaxTok').value = m.max_tokens;
                document.getElementById('modelEditTemp').value = m.temperature != null ? m.temperature : '';
                document.getElementById('modelEditTopP').value = m.top_p != null ? m.top_p : '';
                document.getElementById('modelEditRepPen').value = m.repeat_penalty != null ? m.repeat_penalty : '';
                document.getElementById('modelEditEngine').value = m.engine || 'rkllm';
                document.getElementById('modelEditSkip').checked = false;
                document.getElementById('modelEditErr').classList.add('hidden');
                document.getElementById('modelSaveBtn').textContent = '保存修改';
                modelEditForm.classList.remove('hidden');
            }

            function cancelModelEdit() {
                editingModelId = null;
                modelEditForm.classList.add('hidden');
            }

            async function saveModelEdit() {
                const model_id = document.getElementById('modelEditId').value.trim();
                const name = document.getElementById('modelEditName').value.trim();
                const path = document.getElementById('modelEditPath').value.trim();
                const ctx_max = parseInt(document.getElementById('modelEditCtx').value, 10);
                const max_tokens = parseInt(document.getElementById('modelEditMaxTok').value, 10);
                const temperature = parseFloat(document.getElementById('modelEditTemp').value);
                const top_p = parseFloat(document.getElementById('modelEditTopP').value);
                const repeat_penalty = parseFloat(document.getElementById('modelEditRepPen').value);
                const engine = document.getElementById('modelEditEngine').value;
                const skip_check = document.getElementById('modelEditSkip').checked;
                const errEl = document.getElementById('modelEditErr');

                if (!model_id || !name || !path) { errEl.textContent = '标识、名称、路径不能为空'; errEl.classList.remove('hidden'); return; }
                if (!ctx_max || ctx_max < 1 || ctx_max > 16384) { errEl.textContent = '总上下文必须在 1-16384 之间'; errEl.classList.remove('hidden'); return; }
                if (!max_tokens || max_tokens < 1 || max_tokens > ctx_max) { errEl.textContent = '单次回复量必须在 1-' + ctx_max + ' 之间'; errEl.classList.remove('hidden'); return; }
                if (!isNaN(temperature) && (temperature < 0.1 || temperature > 2)) { errEl.textContent = '温度必须在 0.1-2.0 之间'; errEl.classList.remove('hidden'); return; }
                if (!isNaN(top_p) && (top_p < 0 || top_p > 1)) { errEl.textContent = 'Top-P 必须在 0-1 之间'; errEl.classList.remove('hidden'); return; }
                if (!isNaN(repeat_penalty) && (repeat_penalty < 1 || repeat_penalty > 2)) { errEl.textContent = '重复惩罚必须在 1.0-2.0 之间'; errEl.classList.remove('hidden'); return; }

                const body = {
                    model_id, name, path, ctx_max, max_tokens, engine, skip_check,
                    temperature: isNaN(temperature) ? null : temperature,
                    top_p: isNaN(top_p) ? null : top_p,
                    repeat_penalty: isNaN(repeat_penalty) ? null : repeat_penalty
                };
                try {
                    let res;
                    if (editingModelId) {
                        res = await fetch('/api/models/' + encodeURIComponent(editingModelId), {
                            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
                        });
                    } else {
                        res = await fetch('/api/models', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
                        });
                    }
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast(editingModelId ? '模型已更新' : '模型已挂载');
                        cancelModelEdit();
                        await loadModelList();
                        await initModels();
                    } else {
                        errEl.textContent = data.message || '保存失败';
                        errEl.classList.remove('hidden');
                    }
                } catch(e) {
                    errEl.textContent = '保存失败: ' + e.message;
                    errEl.classList.remove('hidden');
                }
            }

            async function deleteModel(id) {
                const m = models.find(x => x.model_id === id);
                if (!confirm('确定要删除模型 "' + (m?.name || id) + '" 吗？')) return;
                try {
                    const res = await fetch('/api/models/' + encodeURIComponent(id), { method: 'DELETE' });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast('已删除');
                        await loadModelList();
                        await initModels();
                    } else {
                        alert(data.message || '删除失败');
                    }
                } catch(e) {
                    alert('删除失败: ' + e.message);
                }
            }

            // ===== 知识库函数 =====
            let kbs = [];
            let currentKbId = null;
            let editingKbId = null;
            const knowledgeModal = document.getElementById('knowledgeModal');
            const kbMainView = document.getElementById('kbMainView');
            const kbDocView = document.getElementById('kbDocView');

            if (knowledgeModal) {
                knowledgeModal.addEventListener('click', function(e) {
                    if (e.target === knowledgeModal) closeKnowledgeModal();
                });
            }

            function openKnowledgeModal() {
                loadKbs();
                showKbMainView();
                knowledgeModal.classList.remove('modal-hidden');
            }
            function closeKnowledgeModal() {
                knowledgeModal.classList.add('modal-hidden');
                cancelKbForm();
            }
            function showKbMainView() {
                currentKbId = null;
                kbDocView.classList.add('hidden');
                kbMainView.classList.remove('hidden');
                document.getElementById('kbModalTitle').textContent = '知识库';
                document.getElementById('kbModalSub').textContent = '管理知识库文档，绑定到会话后自动检索注入';
            }
            function showKbDocView(kbId) {
                currentKbId = kbId;
                const kb = kbs.find(k => k.id === kbId);
                document.getElementById('kbModalTitle').textContent = '文档管理';
                document.getElementById('kbModalSub').textContent = kb ? '知识库: ' + kb.name : '';
                kbMainView.classList.add('hidden');
                kbDocView.classList.remove('hidden');
                document.getElementById('kbTestResult').innerHTML = '';
                loadKbDocs();
            }
            function backKbList() {
                showKbMainView();
                loadKbs();
            }

            async function loadKbs() {
                try {
                    const res = await fetch('/api/kbs');
                    const data = await res.json();
                    kbs = data.kbs || [];
                    renderKbList();
                } catch(e) {
                    console.error("加载知识库失败:", e);
                }
            }

            function renderKbList() {
                const c = document.getElementById('kbList');
                if (!c) return;
                if (kbs.length === 0) {
                    c.innerHTML = '<div class="text-gray-500 text-sm text-center py-8">暂无知识库，点击「新建知识库」创建</div>';
                    return;
                }
                let html = '';
                for (const k of kbs) {
                    html += '<div class="bg-gray-700/50 rounded-xl p-3 border border-gray-600 hover:border-purple-500/50 transition-colors">';
                    html += '<div class="flex justify-between items-start mb-1">';
                    html += '<div class="min-w-0"><span class="text-gray-100 font-medium text-sm">' + escapeHtml(k.name) + '</span>';
                    if (k.full_inject) html += '<span class="text-[10px] px-1.5 py-0.5 ml-1 bg-purple-600/30 text-purple-300 rounded border border-purple-500/30 align-middle">全量注入</span>';
                    if (k.description) html += '<div class="text-gray-400 text-xs mt-0.5 truncate">' + escapeHtml(k.description) + '</div>';
                    html += '</div>';
                    html += '<div class="flex gap-1 shrink-0">';
                    html += '<button onclick="showKbDocView(' + k.id + ')" class="text-xs px-2 py-1 bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 rounded border border-purple-500/30 transition-colors">文档</button>';
                    html += '<button onclick="editKb(' + k.id + ')" class="text-xs px-2 py-1 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 rounded border border-blue-500/30 transition-colors">编辑</button>';
                    html += '<button onclick="deleteKb(' + k.id + ')" class="text-xs px-2 py-1 bg-red-600/30 hover:bg-red-600/50 text-red-300 rounded border border-red-500/30 transition-colors">删除</button>';
                    html += '</div></div>';
                    html += '<div class="text-gray-500 text-xs mt-1">文档 ' + k.doc_count + ' 篇</div>';
                    html += '</div>';
                }
                c.innerHTML = html;
            }

            function showKbForm(id) {
                editingKbId = id || null;
                const k = id ? kbs.find(x => x.id === id) : null;
                document.getElementById('kbName').value = k ? k.name : '';
                document.getElementById('kbDesc').value = k ? (k.description || '') : '';
                document.getElementById('kbFullInject').checked = k ? !!k.full_inject : false;
                document.getElementById('kbFormErr').classList.add('hidden');
                document.getElementById('kbForm').classList.remove('hidden');
            }
            function editKb(id) { showKbForm(id); }
            function cancelKbForm() {
                editingKbId = null;
                document.getElementById('kbForm').classList.add('hidden');
            }

            async function saveKb() {
                const name = document.getElementById('kbName').value.trim();
                const description = document.getElementById('kbDesc').value.trim();
                const full_inject = document.getElementById('kbFullInject').checked;
                const errEl = document.getElementById('kbFormErr');
                if (!name) { errEl.textContent = '名称不能为空'; errEl.classList.remove('hidden'); return; }
                try {
                    let res;
                    if (editingKbId) {
                        res = await fetch('/api/kbs/' + editingKbId, {
                            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description, full_inject })
                        });
                    } else {
                        res = await fetch('/api/kbs', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description, full_inject })
                        });
                    }
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast(editingKbId ? '知识库已更新' : '知识库已创建');
                        cancelKbForm();
                        await loadKbs();
                    } else {
                        errEl.textContent = data.message || '保存失败';
                        errEl.classList.remove('hidden');
                    }
                } catch(e) {
                    errEl.textContent = '保存失败: ' + e.message;
                    errEl.classList.remove('hidden');
                }
            }

            async function deleteKb(id) {
                const k = kbs.find(x => x.id === id);
                if (!confirm('确定删除知识库 "' + (k?.name || '') + '" 及其全部文档？')) return;
                try {
                    const res = await fetch('/api/kbs/' + id, { method: 'DELETE' });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast('已删除');
                        await loadKbs();
                    } else {
                        alert(data.message || '删除失败');
                    }
                } catch(e) {
                    alert('删除失败: ' + e.message);
                }
            }

            async function loadKbDocs() {
                try {
                    const res = await fetch('/api/kbs/' + currentKbId + '/documents');
                    const data = await res.json();
                    renderKbDocs(data.documents || []);
                } catch(e) {
                    console.error("加载文档失败:", e);
                }
            }

            function renderKbDocs(docs) {
                const c = document.getElementById('kbDocList');
                document.getElementById('kbDocTitle').textContent = '共 ' + docs.length + ' 篇文档';
                if (docs.length === 0) {
                    c.innerHTML = '<div class="text-gray-500 text-sm text-center py-8">暂无文档，上传文件或粘贴文本入库</div>';
                    return;
                }
                let html = '';
                for (const d of docs) {
                    html += '<div class="bg-gray-700/50 rounded-xl p-3 border border-gray-600 flex justify-between items-center gap-2">';
                    html += '<div class="min-w-0"><div class="text-gray-100 text-sm truncate">' + escapeHtml(d.filename) + '</div>';
                    html += '<div class="text-gray-500 text-xs mt-0.5">' + d.chunk_count + ' 个分片 · ' + d.created_at + '</div></div>';
                    html += '<button onclick="deleteKbDoc(' + d.id + ')" class="text-xs px-2 py-1 bg-red-600/30 hover:bg-red-600/50 text-red-300 rounded border border-red-500/30 transition-colors shrink-0">删除</button>';
                    html += '</div>';
                }
                c.innerHTML = html;
            }

            async function uploadKbFile() {
                const input = document.getElementById('kbFileInput');
                const file = input.files[0];
                if (!file) return;
                const fd = new FormData();
                fd.append('file', file);
                try {
                    const res = await fetch('/api/kbs/' + currentKbId + '/documents', { method: 'POST', body: fd });
                    const data = await res.json();
                    if (data.status === 'success') showToast('已入库 ' + data.chunk_count + ' 个分片');
                    else alert(data.message || '上传失败');
                    input.value = '';
                    await loadKbDocs();
                    await loadKbs();
                } catch(e) {
                    alert('上传失败: ' + e.message);
                }
            }

            async function pasteKbText() {
                const content = document.getElementById('kbPaste').value.trim();
                if (!content) { alert('请输入文本'); return; }
                const filename = 'paste_' + Date.now() + '.txt';
                try {
                    const res = await fetch('/api/kbs/' + currentKbId + '/documents/text', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename, content })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast('已入库 ' + data.chunk_count + ' 个分片');
                        document.getElementById('kbPaste').value = '';
                    } else {
                        alert(data.message || '入库失败');
                    }
                    await loadKbDocs();
                    await loadKbs();
                } catch(e) {
                    alert('入库失败: ' + e.message);
                }
            }

            async function deleteKbDoc(id) {
                if (!confirm('删除该文档及其向量分片？')) return;
                try {
                    const res = await fetch('/api/kbs/' + currentKbId + '/documents/' + id, { method: 'DELETE' });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast('已删除');
                        await loadKbDocs();
                        await loadKbs();
                    } else {
                        alert(data.message || '删除失败');
                    }
                } catch(e) {
                    alert('删除失败: ' + e.message);
                }
            }

            async function testKbQuery() {
                const q = document.getElementById('kbTestQuery').value.trim();
                if (!q) { alert('请输入测试问题'); return; }
                const box = document.getElementById('kbTestResult');
                box.innerHTML = '<span class="text-gray-500">检索中...</span>';
                try {
                    const res = await fetch('/api/kbs/' + currentKbId + '/test', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: q, top_k: 3 })
                    });
                    const data = await res.json();
                    if (data.status !== 'success') { box.innerHTML = '<span class="text-red-400">' + (data.message || '失败') + '</span>'; return; }
                    if (!data.hits.length) { box.innerHTML = '<span class="text-gray-500">无命中</span>'; return; }
                    let html = '';
                    data.hits.forEach((h, i) => {
                        html += '<div class="border border-gray-700 rounded p-2"><div class="text-gray-500">#' + (i + 1) + ' · dist=' + h.distance + '</div><div class="text-gray-300">' + escapeHtml(h.content) + '</div></div>';
                    });
                    box.innerHTML = html;
                } catch(e) {
                    box.innerHTML = '<span class="text-red-400">检索失败</span>';
                }
            }

            // ===== 会话三点菜单 + 知识库绑定 =====
            let sessionMenuFor = null;
            let kbBindSessionId = null;
            let kbBindSelected = null;
            const sessionMenuEl = document.getElementById('sessionMenu');
            const sessionMenuBackdrop = document.getElementById('sessionMenuBackdrop');
            const kbBindModalEl = document.getElementById('kbBindModal');

            if (kbBindModalEl) {
                kbBindModalEl.addEventListener('click', function(e) {
                    if (e.target === kbBindModalEl) closeKbBindModal();
                });
            }

            function openSessionMenu(id, e) {
                e.stopPropagation();
                sessionMenuFor = id;
                const sess = sessions.find(s => s.id === id);
                document.getElementById('sessionMenuTitle').textContent = sess ? sess.title : '';
                let x = e.clientX, y = e.clientY;
                if (x + 190 > window.innerWidth) x = window.innerWidth - 200;
                if (y + 110 > window.innerHeight) y = window.innerHeight - 120;
                sessionMenuEl.style.left = x + 'px';
                sessionMenuEl.style.top = y + 'px';
                sessionMenuEl.classList.remove('hidden');
                sessionMenuBackdrop.classList.remove('hidden');
            }

            function closeSessionMenu() {
                sessionMenuFor = null;
                if (sessionMenuEl) sessionMenuEl.classList.add('hidden');
                if (sessionMenuBackdrop) sessionMenuBackdrop.classList.add('hidden');
            }

            function sessionMenuKb() {
                const id = sessionMenuFor;
                closeSessionMenu();
                if (id) openKbBindModal(id);
            }

            function openKbBindModal(sessionId) {
                kbBindSessionId = sessionId;
                const sess = sessions.find(s => s.id === sessionId);
                document.getElementById('kbBindSessionTitle').textContent = sess ? sess.title : '';
                kbBindSelected = sess && sess.kb_id ? sess.kb_id : null;
                renderKbBindList();
                kbBindModalEl.classList.remove('modal-hidden');
            }

            function closeKbBindModal() {
                kbBindModalEl.classList.add('modal-hidden');
            }

            function renderKbBindList() {
                const c = document.getElementById('kbBindList');
                if (!c) return;
                let html = '<label class="flex items-center gap-2 px-3 py-2.5 bg-gray-700/50 rounded-xl border border-gray-600 cursor-pointer hover:border-purple-500/50 transition-colors">';
                html += '<input type="radio" name="kbbind" value="" ' + (kbBindSelected === null ? 'checked' : '') + ' onchange="selectKbBind(null)" class="accent-purple-500">';
                html += '<span class="text-sm text-gray-200">不绑定知识库</span></label>';
                if (kbs.length === 0) {
                    html += '<div class="text-gray-500 text-sm text-center py-4">暂无知识库，请先到 设置→知识库 创建</div>';
                }
                for (const k of kbs) {
                    html += '<label class="flex items-center gap-2 px-3 py-2.5 bg-gray-700/50 rounded-xl border border-gray-600 cursor-pointer hover:border-purple-500/50 transition-colors">';
                    html += '<input type="radio" name="kbbind" value="' + k.id + '" ' + (kbBindSelected === k.id ? 'checked' : '') + ' onchange="selectKbBind(' + k.id + ')" class="accent-purple-500">';
                    html += '<span class="text-sm text-gray-200 truncate flex-1">' + escapeHtml(k.name) + '</span>';
                    if (k.full_inject) html += '<span class="text-[10px] px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded border border-purple-500/30 shrink-0">全量注入</span>';
                    if (k.doc_count === 0) html += '<span class="text-[10px] text-gray-500 shrink-0">空</span>';
                    html += '</label>';
                }
                c.innerHTML = html;
            }

            function selectKbBind(id) {
                kbBindSelected = id;
            }

            async function saveKbBind() {
                if (!kbBindSessionId) return;
                try {
                    const res = await fetch('/api/sessions/' + kbBindSessionId + '/kb', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kb_id: kbBindSelected })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast(kbBindSelected ? '已绑定知识库' : '已取消绑定');
                        const sess = sessions.find(s => s.id === kbBindSessionId);
                        if (sess) sess.kb_id = kbBindSelected;
                        closeKbBindModal();
                        renderSidebar();
                    } else {
                        alert(data.message || '绑定失败');
                    }
                } catch(e) {
                    alert('绑定失败: ' + e.message);
                }
            }

            // ===== 驱动挂载函数 =====
            const driverModal = document.getElementById('driverModal');

            if (driverModal) {
                driverModal.addEventListener('click', function(e) {
                    if (e.target === driverModal) closeDriverModal();
                });
            }

            async function openDriverModal() {
                document.getElementById('driverErr').classList.add('hidden');
                document.getElementById('driverSuccess').classList.add('hidden');
                document.getElementById('driverSkip').checked = false;
                try {
                    const res = await fetch('/api/driver');
                    const data = await res.json();
                    document.getElementById('driverPath').value = data.path || '';
                } catch(e) {
                    document.getElementById('driverPath').value = '';
                }
                driverModal.classList.remove('modal-hidden');
            }
            function closeDriverModal() {
                driverModal.classList.add('modal-hidden');
            }

            async function saveDriver() {
                const path = document.getElementById('driverPath').value.trim();
                const skip_check = document.getElementById('driverSkip').checked;
                const errEl = document.getElementById('driverErr');
                const okEl = document.getElementById('driverSuccess');
                errEl.classList.add('hidden');
                okEl.classList.add('hidden');
                if (!path) {
                    errEl.textContent = '路径不能为空';
                    errEl.classList.remove('hidden');
                    return;
                }
                try {
                    const res = await fetch('/api/driver', {
                        method: 'PUT', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path, skip_check })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        okEl.textContent = '已保存，下次启动引擎生效';
                        okEl.classList.remove('hidden');
                    } else {
                        errEl.textContent = data.message || '保存失败';
                        errEl.classList.remove('hidden');
                    }
                } catch(e) {
                    errEl.textContent = '保存失败: ' + e.message;
                    errEl.classList.remove('hidden');
                }
            }

            // --- 登录/退出函数 ---
            let captchaId = '';

            async function refreshCaptcha() {
                const img = document.getElementById('captchaImg');
                const input = document.getElementById('loginCaptcha');
                if (img) img.src = '';
                if (input) input.value = '';
                try {
                    const res = await fetch('/api/auth/captcha');
                    const data = await res.json();
                    captchaId = data.id || '';
                    if (img && data.image) img.src = data.image;
                } catch(e) {
                    captchaId = '';
                }
            }

            async function doLogin() {
                const username = document.getElementById('loginUsername').value.trim();
                const password = document.getElementById('loginPassword').value;
                const captcha = document.getElementById('loginCaptcha').value.trim();
                const btn = document.getElementById('loginBtn');
                const err = document.getElementById('loginError');
                
                if (!username || !password) {
                    err.textContent = '请输入用户名和密码';
                    err.classList.remove('hidden');
                    return;
                }
                if (!captcha) {
                    err.textContent = '请输入验证码';
                    err.classList.remove('hidden');
                    return;
                }
                
                btn.disabled = true;
                btn.textContent = '登录中...';
                err.classList.add('hidden');
                
                try {
                    const res = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password, captcha_id: captchaId, captcha })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        document.getElementById('loginOverlay').classList.add('hidden');
                        await initModels();
                        await loadSessions();
                        await loadSystemPrompt();
                        await loadCustomPrompts();
                        await loadKbs();
                    } else {
                        err.textContent = data.message || '登录失败';
                        err.classList.remove('hidden');
                        refreshCaptcha();
                    }
                } catch(e) {
                    err.textContent = '网络错误，请重试';
                    err.classList.remove('hidden');
                    refreshCaptcha();
                } finally {
                    btn.disabled = false;
                    btn.textContent = '登 录';
                }
            }
            
            async function doLogout() {
                await fetch('/api/auth/logout', { method: 'POST' });
                chatBox.innerHTML = '';
                sessionList.innerHTML = '';
                currentSessionId = null;
                sessions = [];
                document.getElementById('loginOverlay').classList.remove('hidden');
                document.getElementById('loginPassword').value = '';
                refreshCaptcha();
            }
            
            // --- 修改密码函数 ---
            function openChangePasswordModal() {
                document.getElementById('oldPassword').value = '';
                document.getElementById('newPassword').value = '';
                document.getElementById('confirmPassword').value = '';
                document.getElementById('changePwdError').classList.add('hidden');
                document.getElementById('changePwdSuccess').classList.add('hidden');
                document.getElementById('changePwdModal').classList.remove('modal-hidden');
                document.getElementById('oldPassword').focus();
            }
            
            function closeChangePasswordModal() {
                document.getElementById('changePwdModal').classList.add('modal-hidden');
            }
            
            async function doChangePassword() {
                const oldPwd = document.getElementById('oldPassword').value;
                const newPwd = document.getElementById('newPassword').value;
                const confirmPwd = document.getElementById('confirmPassword').value;
                const btn = document.getElementById('changePwdBtn');
                const err = document.getElementById('changePwdError');
                const succ = document.getElementById('changePwdSuccess');
                
                err.classList.add('hidden');
                succ.classList.add('hidden');
                
                if (!oldPwd || !newPwd) {
                    err.textContent = '请填写所有密码字段';
                    err.classList.remove('hidden');
                    return;
                }
                if (newPwd.length < 4) {
                    err.textContent = '新密码至少需要4个字符';
                    err.classList.remove('hidden');
                    return;
                }
                if (newPwd !== confirmPwd) {
                    err.textContent = '两次输入的新密码不一致';
                    err.classList.remove('hidden');
                    return;
                }
                if (oldPwd === newPwd) {
                    err.textContent = '新密码不能与原密码相同';
                    err.classList.remove('hidden');
                    return;
                }
                
                btn.disabled = true;
                btn.textContent = '修改中...';
                
                try {
                    const res = await fetch('/api/auth/change-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        succ.textContent = '密码修改成功！';
                        succ.classList.remove('hidden');
                        setTimeout(() => closeChangePasswordModal(), 1500);
                    } else {
                        err.textContent = data.message || '修改失败';
                        err.classList.remove('hidden');
                    }
                } catch(e) {
                    err.textContent = '网络错误，请重试';
                    err.classList.remove('hidden');
                } finally {
                    btn.disabled = false;
                    btn.textContent = '确认修改';
                }
            }
            
            // 点击弹窗外部关闭
            document.getElementById('changePwdModal').addEventListener('click', function(e) {
                if (e.target === document.getElementById('changePwdModal')) {
                    closeChangePasswordModal();
                }
            });
            
            // --- 其他函数保持不变 ---
            function cleanOutputText(text) {
                if (!text) return text;
                return text.replace(/(robot:|user:)\s*/gi, '').trimStart();
            }

            async function loadSessions() {
                try {
                    const res = await fetch('/api/sessions');
                    sessions = await res.json();
                    
                    if (sessions.length === 0) {
                        await createNewSession();
                    } else {
                        if (!currentSessionId || !sessions.find(s => s.id === currentSessionId)) {
                            currentSessionId = sessions[0].id;
                        }
                        renderSidebar();
                        await switchSession(currentSessionId);
                    }
                } catch(e) {
                    console.error("加载会话列表失败:", e);
                }
            }

            async function createNewSession() {
                if (isGenerating) return alert("正在生成回复中，请稍后再试");
                try {
                    const res = await fetch('/api/sessions', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: "新的聊天" })
                    });
                    const newSession = await res.json();
                    sessions.unshift(newSession);
                    currentSessionId = newSession.id;
                    renderSidebar();
                    renderChat([]);
                    if(window.innerWidth < 768) toggleSidebar();
                } catch(e) {
                    console.error("创建会话失败:", e);
                }
            }

            async function deleteSession(id, e) {
                e.stopPropagation();
                if (isGenerating) return;
                try {
                    await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
                    sessions = sessions.filter(s => s.id !== id);
                    if (currentSessionId === id) {
                        currentSessionId = sessions.length > 0 ? sessions[0].id : null;
                    }
                    if (sessions.length === 0) {
                        await createNewSession();
                    } else {
                        renderSidebar();
                        await switchSession(currentSessionId);
                    }
                } catch(e) {
                    console.error("删除会话失败:", e);
                }
            }

            async function switchSession(id) {
                if (isGenerating || !id) return;
                currentSessionId = id;
                renderSidebar();
                try {
                    const res = await fetch(`/api/sessions/${id}/messages`);
                    const messages = await res.json();
                    renderChat(messages);
                } catch(e) {
                    console.error("加载会话历史失败:", e);
                }
                if(window.innerWidth < 768 && !sidebar.classList.contains('-translate-x-full')) {
                    toggleSidebar();
                }
            }

            function renderSidebar() {
                sessionList.innerHTML = '';
                sessions.forEach(session => {
                    const isActive = session.id === currentSessionId;
                    const div = document.createElement('div');
                    div.className = `group flex justify-between items-center px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${isActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700/50 hover:text-gray-200'}`;
                    div.onclick = () => switchSession(session.id);
                    div.innerHTML = `
                        <div class="flex items-center space-x-2 truncate flex-1 pr-2">
                            <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                            <span class="truncate text-sm font-medium">${escapeHtml(session.title)}</span>
                            ${session.kb_id ? '<svg class="w-3.5 h-3.5 shrink-0 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="已绑定知识库"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>' : ''}
                        </div>
                        <div class="flex items-center gap-0.5 shrink-0">
                            <button onclick="openSessionMenu('${session.id}', event)" class="text-gray-500 hover:text-gray-200 opacity-60 group-hover:opacity-100 transition-opacity p-1" title="更多选项">
                                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="5" r="2"></circle><circle cx="12" cy="12" r="2"></circle><circle cx="12" cy="19" r="2"></circle></svg>
                            </button>
                            <button onclick="deleteSession('${session.id}', event)" class="text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity p-1">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                            </button>
                        </div>
                    `;
                    sessionList.appendChild(div);
                });
            }

            function renderChat(messages) {
                chatBox.innerHTML = '';
                if (!messages || messages.length === 0) {
                    showWelcomeMessage(`RKLLM 引擎已就绪`);
                    return;
                }

                // 切后台恢复：检查最后一条是否是 user（无 assistant 回复）
                const lastMsg = messages[messages.length - 1];
                if (lastMsg && lastMsg.role === 'user') {
                    const partialKey = '_partial_' + currentSessionId;
                    try {
                        const partial = localStorage.getItem(partialKey);
                        if (partial && partial.trim()) {
                            // 有未完成的回复，追加显示
                            const partialDiv = document.createElement('div');
                            partialDiv.className = 'flex justify-start';
                            const colDiv = document.createElement('div');
                            colDiv.className = 'flex flex-col items-start max-w-[95%] sm:max-w-[85%]';
                            const bubble = document.createElement('div');
                            bubble.className = 'rounded-2xl p-3 sm:p-4 prose prose-invert text-sm sm:text-base shadow-md bg-gray-700 text-gray-100 rounded-tl-sm';
                            renderMarkdown(bubble, cleanOutputText(partial));
                            // 添加恢复标记
                            const note = document.createElement('div');
                            note.className = 'speed-stats mt-1.5 text-xs text-amber-500 flex items-center space-x-1.5';
                            note.innerHTML = '<span>\u26a0 \u5207\u540e\u53f0\u4e2d\u65ad\uff0c\u5df2\u6062\u590d\u90e8\u5206\u5185\u5bb9</span>';
                            bubble.appendChild(note);
                            colDiv.appendChild(bubble);
                            partialDiv.appendChild(colDiv);
                            chatBox.appendChild(partialDiv);
                        }
                    } catch(e) {}
                }
                
                messages.forEach((msg, index) => {
                    const msgDiv = document.createElement('div');
                    msgDiv.className = `flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`;
                    
                    const colDiv = document.createElement('div');
                    colDiv.className = `flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} max-w-[95%] sm:max-w-[85%]`;
                    
                    const bubble = document.createElement('div');
                    bubble.className = `rounded-2xl p-3 sm:p-4 prose prose-invert text-sm sm:text-base shadow-md ${msg.role === 'user' ? 'bg-blue-600 text-white rounded-tr-sm' : 'bg-gray-700 text-gray-100 rounded-tl-sm'}`;
                    
                    // Show thinking drawer for assistant messages that have thinking content
                    if (msg.role === 'assistant' && msg.thinking) {
                        const details = _createThinkingDrawer(bubble);
                        const contentEl = details.querySelector('.thinking-content');
                        if (contentEl) contentEl.textContent = msg.thinking;
                    }
                    
                    const displayContent = msg.role === 'assistant' ? cleanOutputText(msg.content) : msg.content;
                    
                    if (msg.role === 'user') bubble.innerText = displayContent;
                    else renderMarkdown(bubble, displayContent);
                    
                    colDiv.appendChild(bubble);
                    
                    if (index === messages.length - 1 && msg.role === 'assistant') {
                        const actionDiv = document.createElement('div');
                        actionDiv.className = 'mt-1.5 flex justify-start pl-1 regenerate-btn-container';
                        actionDiv.innerHTML = `
                            <button onclick="regenerateLast()" class="group flex items-center space-x-1.5 text-xs text-gray-400 hover:text-blue-400 transition-colors px-2.5 py-1.5 bg-gray-800/80 hover:bg-gray-800 rounded-lg border border-gray-700 hover:border-blue-500/50 shadow-sm cursor-pointer" title="重新生成回复">
                                <svg class="w-3.5 h-3.5 group-active:rotate-180 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                <span>重新生成</span>
                            </button>
                        `;
                        colDiv.appendChild(actionDiv);
                    }
                    
                    msgDiv.appendChild(colDiv);
                    chatBox.appendChild(msgDiv);
                });
                // 显示速率统计（最后一个 AI 回复下）
                if (window._lastStats && window._lastStats.sessionId === currentSessionId) {
                    const s = window._lastStats;
                    const chars = s.chars;
                    const timeMs = s.timeMs;
                    const cps = (chars / (timeMs / 1000)).toFixed(1);
                    const tps = Math.round(chars * 0.6 / (timeMs / 1000));
                    const grayBubbles = chatBox.querySelectorAll('.bg-gray-700');
                    const lastBubble = grayBubbles.length > 0 ? grayBubbles[grayBubbles.length - 1] : null;
                    if (lastBubble) {
                        // 移除旧 stats（避免重复）
                        const oldStats = lastBubble.querySelector('.speed-stats');
                        if (oldStats) oldStats.remove();
                        const statsEl = document.createElement('div');
                        statsEl.className = 'speed-stats mt-1.5 text-xs text-gray-500 flex items-center space-x-1.5';
                        statsEl.innerHTML = '<span>\u23f1 ' + (timeMs / 1000).toFixed(1) + 's</span><span>\u2022</span><span>' + cps + ' \u5b57\u8282/s</span><span>\u2022</span><span>~' + tps + ' tok/s</span>';
                        lastBubble.appendChild(statsEl);
                    }
                }
                setTimeout(() => chatBox.scrollTop = chatBox.scrollHeight, 50);
            }

            marked.setOptions({
                highlight: function(code, lang) {
                    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                    return hljs.highlight(code, { language }).value;
                }, breaks: true
            });

            async function initModels() {
                try {
                    const res = await fetch('/api/models');
                    const data = await res.json();
                    modelSelect.innerHTML = '';
                    data.models.forEach(m => {
                        const opt = document.createElement('option');
                        opt.value = m.model_id; opt.textContent = m.name;
                        if(m.model_id === data.current) opt.selected = true;
                        modelSelect.appendChild(opt);
                    });
                    setTimeout(() => updateStatus('ready', 'NPU 引擎就绪'), 2000);
                } catch(e) {
                    updateStatus('error', '获取模型失败');
                }
            }
            
            // 切后台时保存最后状态
            document.addEventListener('visibilitychange', () => {
                if (document.hidden && isGenerating && currentSessionId) {
                    // 页面被隐藏前保存当前部分响应
                    const bubbles = chatBox.querySelectorAll('.bg-gray-700');
                    if (bubbles.length > 0) {
                        const lastHtml = bubbles[bubbles.length - 1].innerText || '';
                        if (lastHtml.trim()) {
                            try { localStorage.setItem('_partial_' + currentSessionId, lastHtml); } catch(e) {}
                        }
                    }
                }
            });

            window.addEventListener('DOMContentLoaded', async () => {
                // 先检查登录状态
                try {
                    const authRes = await fetch('/api/auth/status');
                    const authData = await authRes.json();
                    if (authData.authenticated) {
                        document.getElementById('loginOverlay').classList.add('hidden');
                        await initModels();
                        await loadSessions();
                        await loadSystemPrompt();
                        await loadCustomPrompts();
                        await loadKbs();
                    } else {
                        document.getElementById('loginOverlay').classList.remove('hidden');
                        refreshCaptcha();
                    }
                } catch(e) {
                    document.getElementById('loginOverlay').classList.remove('hidden');
                    refreshCaptcha();
                }
            });

            function updateStatus(status, text = '') {
                statusDot.className = 'w-3 h-3 rounded-full shrink-0 transition-colors duration-300';
                if (status === 'loading') { statusDot.classList.add('bg-yellow-500', 'animate-pulse'); modelSelect.disabled = true; }
                else if (status === 'ready') { statusDot.classList.add('bg-green-500', 'shadow-[0_0_8px_rgba(34,197,94,0.6)]'); modelSelect.disabled = false; }
                else if (status === 'error') { statusDot.classList.add('bg-red-500'); modelSelect.disabled = false; }
                if(text) statusDot.title = text;
            }

            async function handleModelSwitch() {
                if (isGenerating) return;
                const newModelId = modelSelect.value;
                const newModelName = modelSelect.options[modelSelect.selectedIndex].text;
                
                updateStatus('loading', '正在切换模型...');
                chatBox.innerHTML = `
                    <div class="flex justify-center mt-10">
                        <div class="text-center text-yellow-400 space-y-4 px-4">
                            <svg class="animate-spin w-12 h-12 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            <p class="text-sm sm:text-base font-medium">正在加载 ${newModelName}...</p>
                        </div>
                    </div>`;

                try {
                    const res = await fetch('/api/switch', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ model_id: newModelId })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        updateStatus('ready', '就绪');
                        await switchSession(currentSessionId);
                    } else throw new Error(data.message);
                } catch(e) {
                    updateStatus('error', '切换失败');
                    showWelcomeMessage(`模型切换失败: ${e.message}`, true);
                }
            }

            function showWelcomeMessage(text, isError = false) {
                const color = isError ? 'text-red-400' : 'text-gray-400';
                const icon = isError 
                    ? `<svg class="w-12 h-12 mx-auto text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`
                    : `<svg class="w-12 h-12 mx-auto text-blue-500 opacity-80" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>`;
                
                chatBox.innerHTML = `
                    <div class="flex justify-center mt-10 h-full items-center pb-20" id="welcomeMsg">
                        <div class="text-center space-y-4 px-4">
                            ${icon}
                            <h3 class="text-xl font-bold text-gray-200">欢迎使用 NPU 本地模型</h3>
                            <p class="text-sm ${color}">${text}</p>
                        </div>
                    </div>`;
            }

            function _createThinkingDrawer(parentBubble) {
                // 在 bubble 顶部插入 <details> 思考抽屉
                const details = document.createElement('details');
                details.className = 'thinking-drawer mb-2 border border-amber-700/40 rounded-lg bg-amber-900/15 overflow-hidden';
                details.open = false; // 默认折叠，加载完自动展示
                details.innerHTML = `
                    <summary class="cursor-pointer px-3 py-1.5 text-xs text-amber-400/80 hover:text-amber-300 font-medium select-none flex items-center space-x-1.5">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path></svg>
                        <span>💭 思考过程</span>
                    </summary>
                    <div class="thinking-content px-3 py-2 text-xs text-amber-300/70 leading-relaxed whitespace-pre-wrap border-t border-amber-700/30 bg-amber-900/10">等待中...</div>
                `;
                // 插入到 bubble 最前面
                if (parentBubble.firstChild) {
                    parentBubble.insertBefore(details, parentBubble.firstChild);
                } else {
                    parentBubble.appendChild(details);
                }
                return details;
            }

            function renderMarkdown(element, text) {
                const mathBlocks = [];
                let tempText = text.replace(/\$\$([\s\S]*?)\$\$/g, function(match) {
                    mathBlocks.push(match); return `MATHPLACEHOLDERBLOCK${mathBlocks.length - 1}END`;
                });
                tempText = tempText.replace(/\$([^\n\$]+?)\$/g, function(match) {
                    mathBlocks.push(match); return `MATHPLACEHOLDERINLINE${mathBlocks.length - 1}END`;
                });

                let html = marked.parse(tempText);
                html = html.replace(/MATHPLACEHOLDERBLOCK(\d+)END/g, (m, i) => mathBlocks[i]);
                html = html.replace(/MATHPLACEHOLDERINLINE(\d+)END/g, (m, i) => mathBlocks[i]);

                element.innerHTML = html;
                if (window.renderMathInElement) {
                    renderMathInElement(element, {
                        delimiters: [
                            {left: '$$', right: '$$', display: true}, {left: '\\[', right: '\\]', display: true},
                            {left: '$', right: '$', display: false}, {left: '\\(', right: '\\)', display: false}
                        ], throwOnError: false
                    });
                }
            }

            userInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
            });

            userInput.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 128) + 'px';
                if(this.value === '') this.style.height = 'auto';
            });

            function appendMessageBubble(role, content) {
                const welcome = document.getElementById('welcomeMsg');
                if(welcome) welcome.remove();
                
                const msgDiv = document.createElement('div');
                msgDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'}`;
                
                const colDiv = document.createElement('div');
                colDiv.className = `flex flex-col ${role === 'user' ? 'items-end' : 'items-start'} max-w-[95%] sm:max-w-[85%]`;

                const bubble = document.createElement('div');
                bubble.className = `rounded-2xl p-3 sm:p-4 prose prose-invert text-sm sm:text-base shadow-md ${role === 'user' ? 'bg-blue-600 text-white rounded-tr-sm' : 'bg-gray-700 text-gray-100 rounded-tl-sm'}`;
                
                const displayContent = role === 'assistant' ? cleanOutputText(content) : content;
                
                if (role === 'user') bubble.innerText = displayContent;
                else renderMarkdown(bubble, displayContent);
                
                colDiv.appendChild(bubble);
                msgDiv.appendChild(colDiv);
                chatBox.appendChild(msgDiv);
                
                setTimeout(() => chatBox.scrollTop = chatBox.scrollHeight, 50);
                return bubble;
            }

            async function triggerGeneration(queryText, isRegenerate = false) {
                if (isGenerating || statusDot.classList.contains('bg-yellow-500')) return;
                if (!currentSessionId) return;

                isGenerating = true; sendBtn.disabled = true; modelSelect.disabled = true;

                const oldBtns = chatBox.querySelectorAll('.regenerate-btn-container');
                oldBtns.forEach(btn => btn.remove());

                if (!isRegenerate) {
                    userInput.value = ''; userInput.style.height = 'auto';
                    if(window.innerWidth < 640) userInput.blur();
                    appendMessageBubble('user', queryText);
                } else {
                    const bubbles = chatBox.children;
                    if(bubbles.length > 0) {
                        const lastDiv = bubbles[bubbles.length-1];
                        if (lastDiv.querySelector('.bg-gray-700')) lastDiv.remove();
                    }
                }
                
                const assistantBubble = appendMessageBubble('assistant', '<span class="animate-pulse flex items-center space-x-2"><span>NPU 计算中</span><span class="flex space-x-1"><span class="w-1 h-1 bg-gray-400 rounded-full animate-bounce"></span><span class="w-1 h-1 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></span><span class="w-1 h-1 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.4s"></span></span></span>');
                let fullResponse = "";

                try {
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            session_id: currentSessionId, 
                            query: queryText,
                            regenerate: isRegenerate
                        })
                    });

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder("utf-8");
                    assistantBubble.innerHTML = ''; 

                    let buffer = '';
                    let thinkingBubble = null;
                    let responseBubble = null;
                    let thinkingText = '';
                    let showingThinking = false;
                    
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop();

                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                const dataStr = line.slice(6).trim();
                                if (dataStr === '[DONE]') break;
                                if (dataStr) {
                                    try {
                                        const data = JSON.parse(dataStr);
                                        const msgType = data.type || 'response';
                                        
                                        if (msgType === 'thinking') {
                                            thinkingText = data.content;
                                            showingThinking = true;
                                            thinkingBubble = _createThinkingDrawer(assistantBubble);
                                            const contentEl = thinkingBubble?.querySelector('.thinking-content');
                                            if (contentEl) contentEl.textContent = thinkingText;
                                            
                                        } else if (msgType === 'stats') {
                                            window._lastStats = {
                                                chars: data.chars || 0,
                                                timeMs: data.time_ms || 1,
                                                sessionId: currentSessionId
                                            };
                                            // 立即显示（不等 re-render）
                                            const s = window._lastStats;
                                            const cps2 = (s.chars / (s.timeMs / 1000)).toFixed(1);
                                            const tps2 = Math.round(s.chars * 0.6 / (s.timeMs / 1000));
                                            const se = document.createElement('div');
                                            se.className = 'speed-stats mt-1.5 text-xs text-gray-500 flex items-center space-x-1.5';
                                            se.innerHTML = '<span>\u23f1 ' + (s.timeMs / 1000).toFixed(1) + 's</span><span>\u2022</span><span>' + cps2 + ' \u5b57\u8282/s</span><span>\u2022</span><span>~' + tps2 + ' tok/s</span>';
                                            assistantBubble.appendChild(se);

                                        } else if (msgType === 'response') {
                                            fullResponse += data.content;
                                            // 切后台保护：持续存 localStorage
                                            try {
                                                localStorage.setItem('_partial_' + currentSessionId, fullResponse);
                                            } catch(e) {}
                                            renderMarkdown(assistantBubble, cleanOutputText(fullResponse));
                                            
                                        } else if (data.content !== undefined) {
                                            // 旧版兼容: 无 type 字段直接当作回复
                                            fullResponse += data.content;
                                            try {
                                                localStorage.setItem('_partial_' + currentSessionId, fullResponse);
                                            } catch(e) {}
                                            renderMarkdown(assistantBubble, cleanOutputText(fullResponse));
                                        }
                                        
                                        chatBox.scrollTop = chatBox.scrollHeight;
                                    } catch(e) { }
                                }
                            }
                        }
                    }


                    
                    // 清除切后台保护数据
                    try { localStorage.removeItem('_partial_' + currentSessionId); } catch(e) {}
                    const sessionRes = await fetch('/api/sessions');
                    sessions = await sessionRes.json();
                    renderSidebar();
                    
                    isGenerating = false;
                    await switchSession(currentSessionId);

                } catch (error) {
                    renderMarkdown(assistantBubble, "⚠️ 网络错误或 NPU 后端异常。");
                } finally {
                    isGenerating = false; sendBtn.disabled = false; modelSelect.disabled = false;
                }
            }

            async function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;
                triggerGeneration(text, false);
            }

            function regenerateLast() {
                triggerGeneration("", true);
            }

            async function resetChat() {
                if(isGenerating) return;
                updateStatus('loading', '正在重启 NPU 进程...');
                const modelName = modelSelect.options[modelSelect.selectedIndex].text;

                chatBox.innerHTML = `
                    <div class="flex justify-center mt-10">
                        <div class="text-center text-blue-400 space-y-4 px-4">
                            <svg class="animate-spin w-12 h-12 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            <p class="text-sm">正在强制清理 NPU 碎片并重启进程...</p>
                        </div>
                    </div>`;
                
                await fetch('/api/npu/restart', { method: 'POST' });
                
                updateStatus('ready', '就绪');
                await switchSession(currentSessionId); 
            }

            async function exportChat() {
                if (!currentSessionId) return;
                try {
                    const res = await fetch(`/api/sessions/${currentSessionId}/messages`);
                    const messages = await res.json();
                    if (messages.length === 0) return alert("当前聊天暂无数据可导出");
                    
                    const sessionInfo = sessions.find(s => s.id === currentSessionId);
                    const title = sessionInfo ? sessionInfo.title : "Chat";
                    
                    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(messages, null, 2));
                    const downloadAnchorNode = document.createElement('a');
                    downloadAnchorNode.setAttribute("href", dataStr);
                    downloadAnchorNode.setAttribute("download", `RKLLM_${title}_${Date.now()}.json`);
                    document.body.appendChild(downloadAnchorNode);
                    downloadAnchorNode.click();
                    downloadAnchorNode.remove();
                } catch(e) {
                    alert("导出失败");
                }
            }
        </script>
    </body>
    </html>
"""


@router.get("/")
async def get_ui():
    return HTMLResponse(content=html_content, headers={"Cache-Control": "no-store"})
