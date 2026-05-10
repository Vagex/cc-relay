import json
import httpx
import uvicorn
import logging
import uuid
import hashlib
import traceback
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# ==========================================
# 0. 系統日誌設定 & 全域秘密記憶體
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CodexRelay")

ACTIVE_PROFILE_STATE = {
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "ollama",
    "model": "gemma4:26b"
}

GLOBAL_REASONING_STORE = {}       
GLOBAL_TOOL_REASONING_STORE = {}  

# ==========================================
# 1. 前端視圖層 (終極修復版 - 嚴格基於原版代碼擴充)
# ==========================================
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>Codex Relay Web 專業控制台</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.4); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(148, 163, 184, 0.7); }
        .chat-container { height: calc(100vh - 180px); }
        [v-cloak] { display: none; }
        
        .toast-enter-active, .toast-leave-active { transition: all 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        .toast-enter-from, .toast-leave-to { opacity: 0; transform: scale(0.7) translateY(30px); }
        
        /* 1. 模型名稱省略 */
        .model-badge {
            max-width: 180px; 
            display: inline-block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            vertical-align: middle;
        }

        /* 2. 非運行配置邊框 */
        .profile-card-inactive {
            border: 1px solid rgba(203, 213, 225, 0.6) !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }

        /* 3. config.toml 懸浮窗 (點擊自動複製) */
        .config-portal {
            display: none;
            position: absolute;
            bottom: 85px;
            left: 20px;
            right: 20px;
            background: #0f172a;
            color: #38bdf8;
            padding: 18px;
            border-radius: 20px;
            font-family: 'Fira Code', monospace;
            font-size: 11px;
            line-height: 1.5;
            z-index: 100;
            box-shadow: 0 25px 60px rgba(0,0,0,0.5);
            border: 1px solid rgba(56, 189, 248, 0.4);
            text-align: left;
            cursor: pointer;
        }
        .config-portal:hover { background: #1e293b; }
        .config-portal::after { 
            content: "📋 點擊內容自動複製到剪貼簿"; 
            display: block; 
            margin-top: 10px; 
            color: #94a3b8; 
            font-size: 10px; 
            text-align: center; 
            border-top: 1px dashed rgba(255,255,255,0.1); 
            padding-top: 8px; 
        }
        .status-bar-container:hover .config-portal { display: block; }
        
        /* 自定義磨砂玻璃漸層背景 */
        body {
            background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
            background-image: radial-gradient(at 0% 0%, hsla(253,16%,93%,1) 0, transparent 50%), 
                              radial-gradient(at 50% 0%, hsla(225,39%,90%,1) 0, transparent 50%), 
                              radial-gradient(at 100% 0%, hsla(339,49%,92%,1) 0, transparent 50%);
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
    </style>
</head>
<body class="text-slate-800 font-sans overflow-hidden">
    
    <div id="app" class="w-full max-w-[1400px] h-[92vh] flex bg-white/30 backdrop-blur-2xl border border-white/60 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] rounded-[2.5rem] overflow-hidden m-6" v-cloak>
        
        <transition name="toast">
            <div v-if="toast.show" class="fixed inset-0 z-[100] flex items-center justify-center pointer-events-none">
                <div class="px-8 py-5 rounded-3xl text-white font-extrabold text-lg flex items-center gap-4 backdrop-blur-2xl shadow-[0_20px_50px_rgba(0,0,0,0.2)] border border-white/20 transition-all" 
                     :class="toast.type === 'error' ? 'bg-rose-500/80 shadow-rose-500/30' : 'bg-emerald-500/80 shadow-emerald-500/30'">
                    <span class="text-3xl drop-shadow-md">{{ toast.type === 'error' ? '❌' : '✨' }}</span>
                    <span class="drop-shadow-sm tracking-wide">{{ toast.msg }}</span>
                </div>
            </div>
        </transition>

        <div class="w-[340px] bg-white/40 backdrop-blur-2xl border-r border-white/60 flex flex-col shadow-[4px_0_24px_rgba(0,0,0,0.02)] flex-shrink-0 z-20">
            <div class="p-5 border-b border-white/50 flex justify-between items-center bg-white/20">
                <h2 class="text-lg font-extrabold text-slate-700 flex items-center gap-1.5 drop-shadow-sm">🎛️ 配置中心</h2>
                <button @click="createNewProfile" class="bg-blue-500/10 hover:bg-blue-500/20 text-blue-700 border border-blue-200/50 px-4 py-1.5 rounded-full font-bold text-sm transition shadow-sm backdrop-blur-md">＋ 新增</button>
            </div>
            
            <div class="flex-1 overflow-y-auto p-4 space-y-4">
                <div v-for="(profile, index) in sortedProfiles" :key="profile.id"
                     draggable="true"
                     @dragstart="onDragStart(index, $event)"
                     @dragover.prevent="onDragOver(index)"
                     @dragleave.prevent="onDragLeave"
                     @drop.prevent="onDrop(index)"
                     @dragend="onDragEnd"
                     class="rounded-2xl transition-all duration-200 relative flex flex-col cursor-pointer overflow-hidden group"
                     :class="[
                        activeProfileId === profile.id 
                            ? 'bg-gradient-to-br from-blue-100/95 via-indigo-50/95 to-blue-100/95 backdrop-blur-2xl border-2 border-blue-400 ring-4 ring-blue-400/30 shadow-xl shadow-blue-500/15 z-10' 
                            : 'bg-white/40 border border-white/60 hover:bg-white/60 hover:shadow-md hover:border-white profile-card-inactive',
                        dragOverIndex === index ? 'border-dashed border-2 border-blue-500 bg-blue-50/50 scale-[1.02] shadow-lg' : '',
                        draggedIndex === index ? 'opacity-40 scale-95 shadow-none' : 'scale-100'
                     ]"
                     @click="selectProfile(profile.id)">
                    
                    <div class="absolute left-1 top-1/2 -translate-y-1/2 cursor-grab text-slate-400/50 hover:text-slate-600 opacity-0 group-hover:opacity-100 transition px-1 z-20" title="按住拖曳排序">⋮⋮</div>

                    <div class="p-4 pl-7 flex items-start gap-3">
                        <div class="text-3xl pt-0.5 drop-shadow-md">{{ profile.icon || '⚙️' }}</div>
                        <div class="flex-1 min-w-0">
                            <div :title="profile.name" class="font-bold text-[15px] text-slate-800 truncate">{{ profile.name }}</div>
                            <div :title="profile.baseUrl" class="text-xs truncate mt-1 font-medium" :class="activeProfileId === profile.id ? 'text-blue-600/80' : 'text-slate-500'">{{ profile.baseUrl || '尚未設定 URL' }}</div>
                            <div :title="profile.model" class="text-xs font-mono mt-1 px-2 py-0.5 rounded-md inline-block border model-badge" :class="activeProfileId === profile.id ? 'bg-blue-200/60 text-blue-800 border-blue-300/50' : 'bg-slate-200/50 text-slate-600 border-transparent'">{{ profile.model || '尚未選擇模型' }}
                            </div>
                        </div>
                    </div>
                    
                    <div class="px-4 py-2.5 border-t flex items-center justify-between" :class="activeProfileId === profile.id ? 'bg-blue-200/30 border-blue-300/50' : 'bg-white/30 border-white/50'">
                        <button @click.stop="enableProfile(profile.id)" class="text-xs px-4 py-1.5 rounded-full font-bold transition flex items-center gap-1.5 shadow-sm" 
                                :class="activeProfileId === profile.id ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white border-none' : 'bg-white/70 border border-slate-200 text-slate-600 hover:bg-white'">
                            {{ activeProfileId === profile.id ? '🟢 運行中' : '⚪ 設為啟用' }}
                        </button>
                        <div class="flex gap-1 rounded-full p-0.5 border" :class="activeProfileId === profile.id ? 'bg-white/40 border-blue-300/30' : 'bg-white/50 border-white/60'">
                            <button @click.stop="testProfile(profile)" class="p-1.5 text-slate-500 hover:text-emerald-600 hover:bg-emerald-100 rounded-full transition" title="測試連線">⚡</button>
                            <button @click.stop="editProfile(profile.id)" class="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-blue-100 rounded-full transition" title="編輯配置">✏️</button>
                            <button @click.stop="deleteProfile(profile.id)" class="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-rose-100 rounded-full transition" title="刪除">🗑️</button>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="p-4 border-t border-white/50 bg-white/20 backdrop-blur-xl flex flex-col gap-3 relative status-bar-container">
                
                <div class="config-portal" @click="copyConfig">
                    <span class="text-white font-bold border-b border-blue-500/30 mb-2 block pb-1 text-[10px] uppercase">Codex config.toml (Click to Copy)</span>
                    model = "relay-auto"<br><br>
                    model_provider = "local-relay"<br><br>
                    [model_providers.local-relay]<br>
                    name = "Local Relay"<br>
                    base_url = "http://127.0.0.1:4446/relay/v1"<br>
                    wire_api = "responses"
                </div>

                <div class="flex gap-2">
                    <button @click="exportConfig" class="flex-1 bg-white/60 hover:bg-white border border-slate-200 text-slate-700 py-2 rounded-xl text-sm font-bold shadow-sm transition flex justify-center items-center gap-1.5">
                        📤 匯出配置
                    </button>
                    <button @click="$refs.fileInput.click()" class="flex-1 bg-white/60 hover:bg-white border border-slate-200 text-slate-700 py-2 rounded-xl text-sm font-bold shadow-sm transition flex justify-center items-center gap-1.5">
                        📥 匯入備份
                    </button>
                    <input type="file" ref="fileInput" @change="importConfig" accept=".json" class="hidden">
                </div>
                
                <div class="py-2 px-3 text-xs text-center rounded-xl font-medium flex items-center justify-center gap-2 shadow-inner border border-white/50 cursor-help" :class="syncStatus === 'Synced' ? 'text-emerald-700 bg-emerald-100/50' : 'text-slate-500 bg-slate-200/50'">
                    <span class="relative flex h-2 w-2" v-if="syncStatus === 'Synced'">
                      <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                    </span>
                    {{ syncStatus === 'Synced' ? 'Codex 已連結 (滑鼠移入看配置)' : '🔄 等待握手同步...' }}
                </div>
            </div>
        </div>

        <div class="flex-1 flex flex-col relative min-w-0 bg-transparent border-l border-white/40">
            <div class="h-16 bg-white/30 backdrop-blur-xl border-b border-white/50 flex items-center justify-between px-8 shadow-sm z-10">
                <div class="font-medium text-slate-700 flex items-center gap-3">
                    <div class="h-10 w-10 bg-white/80 rounded-full shadow-sm flex items-center justify-center text-xl border border-white/60">{{ activeProfile?.icon || '🤖' }}</div>
                    <div class="flex flex-col">
                        <span class="text-xs text-slate-500 font-bold uppercase tracking-wider">Active Engine</span>
                        <span class="text-sm font-bold text-blue-700 drop-shadow-sm">{{ activeProfile?.model || '未設定' }}</span>
                    </div>
                </div>
                <button @click="isEditing = !isEditing" class="text-white bg-slate-800/90 hover:bg-slate-900 backdrop-blur-md px-6 py-2.5 rounded-full text-sm font-bold shadow-lg transition flex items-center gap-2">
                    {{ isEditing ? '💬 返回終端對話' : '⚙️ 編輯當前配置' }}
                </button>
            </div>

            <div class="flex-1 overflow-hidden relative">
                <div v-if="isEditing && activeProfile" class="absolute inset-0 z-20 p-8 overflow-y-auto flex items-center justify-center">
                    <div class="w-full max-w-3xl space-y-6 bg-white/70 backdrop-blur-3xl p-10 rounded-[2rem] shadow-2xl border border-white/80">
                        <h3 class="text-2xl font-extrabold border-b border-slate-300/60 pb-5 text-slate-800 flex items-center gap-3">
                            <span class="text-4xl drop-shadow-md">{{ activeProfile.icon || '⚙️' }}</span> 
                            <span>API 核心參數設定</span>
                        </h3>
                        
                        <div class="grid grid-cols-2 gap-6">
                            <div>
                                <label class="block text-sm font-extrabold text-slate-700 mb-2">雲端/本地供應商</label>
                                <select v-model="activeProfile.provider" @change="applyPreset" class="w-full bg-white/90 backdrop-blur-md border-2 border-slate-300/60 hover:border-slate-400 shadow-sm rounded-xl p-3.5 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 font-bold text-slate-800 transition cursor-pointer">
                                    <option v-for="(p, key) in presets" :key="key" :value="key">{{ p.icon }} {{ p.name }}</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-sm font-extrabold text-slate-700 mb-2">配置名稱</label>
                                <input v-model="activeProfile.name" class="w-full bg-white/90 backdrop-blur-md border-2 border-slate-300/60 hover:border-slate-400 shadow-sm rounded-xl p-3.5 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition font-bold text-slate-800">
                            </div>
                        </div>

                        <div>
                            <label class="block text-sm font-extrabold text-slate-700 mb-2">Base URL (API 端點)</label>
                            <input v-model.trim="activeProfile.baseUrl" class="w-full bg-blue-50/80 backdrop-blur-md border-2 border-blue-300/80 hover:border-blue-400 shadow-sm rounded-xl p-3.5 font-mono text-sm text-blue-800 outline-none focus:border-blue-600 focus:ring-4 focus:ring-blue-500/20 transition font-bold">
                        </div>
                        
                        <div>
                            <label class="block text-sm font-extrabold text-slate-700 mb-2 flex justify-between">
                                <span>API Key (密鑰)</span>
                                <button @click="showFullKey = !showFullKey" class="text-blue-600 hover:text-blue-800 text-xs transition">
                                    {{ showFullKey ? '🙈 隱藏' : '👁️ 顯示完整' }}
                                </button>
                            </label>
                            <input v-model.trim="activeProfile.apiKey" :type="showFullKey ? 'text' : 'password'" placeholder="sk-..." class="w-full bg-white/90 backdrop-blur-md border-2 border-slate-300/60 hover:border-slate-400 shadow-sm rounded-xl p-3.5 font-mono text-sm outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition font-bold text-slate-800">
                        </div>
                        
                        <div class="p-6 bg-slate-100/60 backdrop-blur-xl rounded-2xl border-2 border-slate-200 shadow-inner">
                            <label class="block text-sm font-extrabold text-slate-800 mb-3">部署模型 (Model ID)</label>
                            <div class="relative flex gap-3">
                                <input v-model.trim="activeProfile.model" @focus="showModelDropdown = fetchedModels.length > 0" class="flex-1 bg-white/90 backdrop-blur-sm border-2 border-slate-300/60 hover:border-slate-400 shadow-sm rounded-xl p-3.5 font-mono text-sm outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition text-slate-800 font-bold" placeholder="手動輸入或點擊右側獲取線上清單...">
                                <button @click="fetchModels" :disabled="loadingModels" class="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white px-6 py-3.5 rounded-xl font-bold shadow-lg transition whitespace-nowrap flex items-center gap-2">
                                    {{ loadingModels ? '⏳ 請求中...' : '📡 獲取清單' }}
                                </button>
                                <div v-if="showModelDropdown" class="fixed inset-0 z-30" @click="showModelDropdown = false"></div>
                                <ul v-if="showModelDropdown" class="absolute left-0 top-[110%] w-full max-h-[300px] overflow-y-auto bg-white/95 backdrop-blur-3xl border border-white rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] z-40">
                                    <li class="px-5 py-3 bg-slate-100/80 backdrop-blur-md border-b border-slate-200/50 text-xs font-extrabold text-slate-500 sticky top-0 z-10 uppercase tracking-wider">A-Z 排序 (共 {{ fetchedModels.length }} 個)</li>
                                    <li v-for="m in fetchedModels" :key="m.id || m" @click="selectModel(m.id || m)" class="px-5 py-3.5 hover:bg-blue-50 cursor-pointer text-sm font-mono border-b border-slate-100 last:border-0 transition flex items-center gap-3 text-slate-700">
                                        <span class="text-blue-500 text-lg opacity-70">❖</span> {{ m.id || m }}
                                    </li>
                                </ul>
                            </div>
                        </div>
                        
                        <div class="pt-4">
                            <button @click="saveAndExit" class="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 shadow-xl shadow-emerald-500/20 text-white py-4 rounded-2xl font-extrabold text-lg transition flex justify-center items-center gap-2">
                                <span>💾</span> 儲存配置並返回
                            </button>
                        </div>
                    </div>
                </div>

                <div v-else class="absolute inset-0 flex flex-col bg-transparent">
                    <div id="chatBox" class="chat-container overflow-y-auto p-8 space-y-8">
                        <div v-for="(msg, i) in chatHistory" :key="i" class="flex flex-col">
                            <div :class="msg.role === 'user' 
                                ? 'self-end bg-gradient-to-br from-blue-600 to-indigo-600 text-white p-5 rounded-[2rem] rounded-tr-md max-w-[85%] shadow-xl shadow-blue-500/20 border border-blue-400/50 backdrop-blur-md' 
                                : 'self-start w-full max-w-4xl border border-white/60 p-6 bg-white/70 backdrop-blur-2xl rounded-[2rem] rounded-tl-md shadow-lg'">
                                <div class="font-extrabold text-xs opacity-80 mb-3 flex items-center gap-2 tracking-wide uppercase">
                                    {{ msg.role === 'user' ? '👤 終端指令' : activeProfile?.icon + ' ' + (activeProfile?.model || 'AI') }}
                                </div>
                                <div class="prose prose-sm md:prose-base max-w-none" :class="msg.role === 'user' ? 'prose-invert text-white' : 'text-slate-800'" v-html="renderMd(msg.content)"></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-6 bg-white/40 backdrop-blur-2xl border-t border-white/60 shadow-[0_-10px_40px_rgba(0,0,0,0.03)] z-10">
                        <div class="max-w-4xl mx-auto flex gap-4 relative">
                            <textarea v-model="input" @keydown.enter.prevent="send" rows="2" placeholder="輸入測試指令，按 Enter 發送..." class="flex-1 bg-white/90 backdrop-blur-md border-2 border-slate-300/50 hover:border-slate-400 rounded-2xl p-4 outline-none focus:ring-4 focus:ring-blue-500/20 focus:border-blue-500 transition resize-none text-base shadow-inner text-slate-800 font-medium"></textarea>
                            <button @click="send" :disabled="gen" class="bg-gradient-to-br from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white px-8 rounded-2xl font-extrabold shadow-xl shadow-blue-500/30 transition disabled:opacity-50 flex items-center justify-center min-w-[120px]">
                                <span v-if="gen" class="animate-spin text-2xl">⏳</span>
                                <span v-else class="text-lg tracking-wider">發送 🚀</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;
        createApp({
            setup() {
                const presets = {
                    custom: { name: '自定義節點', url: '', model: '', icon: '⚙️' },
                    deepseek: { name: 'DeepSeek 官方', url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', icon: '🐳' },
                    siliconflow: { name: '硅基流动 (SiliconFlow)', url: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3', icon: '🌊' },
                    openrouter: { name: 'OpenRouter', url: 'https://openrouter.ai/api/v1', model: 'anthropic/claude-3-haiku', icon: '🌌' },
                    kimi: { name: '月之暗面 Kimi', url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k', icon: '🌙' },
                    zhipu: { name: '智譜 GLM', url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-plus', icon: '🧠' },
                    aliyun: { name: '阿里百煉 Qwen', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', icon: '☁️' },
                    tencent: { name: '騰訊混元', url: 'https://api.hunyuan.cloud.tencent.com/v1', model: 'hunyuan-lite', icon: '🐧' },
                    baidu: { name: '百度千帆 (ERNIE)', url: 'https://qianfan.baidubce.com/v2', model: 'ernie-4.0-8k-latest', icon: '🐾' },
                    nvidia: { name: 'Nvidia NIM', url: 'https://integrate.api.nvidia.com/v1', model: 'meta/llama-3.1-405b-instruct', icon: '🖥️' },
                    groq: { name: 'Groq (光速推論)', url: 'https://api.groq.com/openai/v1', model: 'llama3-8b-8192', icon: '⚡' },
                    together: { name: 'Together AI', url: 'https://api.together.xyz/v1', model: 'meta-llama/Llama-3-70b-chat-hf', icon: '🤝' },
                    mistral: { name: 'Mistral AI', url: 'https://api.mistral.ai/v1', model: 'mistral-large-latest', icon: '🌪️' },
                    xai: { name: 'xAI (Grok)', url: 'https://api.x.ai/v1', model: 'grok-beta', icon: '✖️' },
                    github: { name: 'GitHub Models', url: 'https://models.inference.ai.azure.com', model: 'gpt-4o', icon: '🐙' },
                    ollama: { name: '本地 Ollama', url: 'http://127.0.0.1:11434/v1', model: '', icon: '🦙' },
                    ollama_docker: { name: 'Ollama (Docker 桌面版)', url: 'http://host.docker.internal:11434/v1', model: '', icon: '🐳' },
                    lmstudio: { name: '本地 LM Studio', url: 'http://localhost:1234/v1', model: '', icon: '🎛️' },
                    vllm: { name: '本地 vLLM', url: 'http://localhost:8000/v1', model: '', icon: '🚀' }
                };

                const profiles = ref([]); 
                const activeProfileId = ref(null); 
                const isEditing = ref(false);
                const chatHistory = ref([]); 
                const input = ref(''); 
                const gen = ref(false);
                const fetchedModels = ref([]); 
                const loadingModels = ref(false); 
                const showModelDropdown = ref(false);
                const syncStatus = ref('');
                const fileInput = ref(null);
                const showFullKey = ref(false);
                const toast = ref({ show: false, msg: '', type: 'success' });

                const copyConfig = () => {
                    const text = 'model = "relay-auto"\n\nmodel_provider = "local-relay"\n\n[model_providers.local-relay]\nname = "Local Relay"\nbase_url = "http://127.0.0.1:4446/relay/v1"\nwire_api = "responses"';
                    navigator.clipboard.writeText(text).then(() => {
                        showToast('✅ 配置已成功複製到剪貼簿！');
                    });
                };

                const sortedProfiles = computed(() => {
                    if (!profiles.value.length) return [];
                    return [...profiles.value].sort((a, b) => {
                        if (a.id === activeProfileId.value) return -1;
                        if (b.id === activeProfileId.value) return 1;
                        return 0;
                    });
                });

                const showToast = (msg, type = 'success') => {
                    toast.value = { show: true, msg, type };
                    setTimeout(() => toast.value.show = false, 3000);
                };

                const draggedIndex = ref(null);
                const dragOverIndex = ref(null);

                const onDragStart = (index, event) => {
                    draggedIndex.value = index;
                    if(event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
                };
                const onDragOver = (index) => { dragOverIndex.value = index; };
                const onDragLeave = () => { dragOverIndex.value = null; };
                const onDragEnd = () => { draggedIndex.value = null; dragOverIndex.value = null; };
                const onDrop = (index) => {
                    if (draggedIndex.value !== null && draggedIndex.value !== index) {
                        const items = [...profiles.value];
                        const [draggedItem] = items.splice(draggedIndex.value, 1);
                        items.splice(index, 0, draggedItem);
                        profiles.value = items;
                        showToast('✅ 節點順序已保存', 'success');
                    }
                    dragOverIndex.value = null;
                    draggedIndex.value = null;
                };

                const exportConfig = () => {
                    try {
                        const data = { version: "1.0", activeId: activeProfileId.value, profiles: profiles.value };
                        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `codex_relay_backup_${new Date().toISOString().slice(0,10)}.json`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                        showToast('📤 配置已成功匯出檔案', 'success');
                    } catch (e) { showToast('❌ 匯出失敗', 'error'); }
                };

                const importConfig = (event) => {
                    const file = event.target.files[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        try {
                            const data = JSON.parse(e.target.result);
                            if (data.profiles && Array.isArray(data.profiles)) {
                                data.profiles.forEach(p => {
                                    if(!p.provider) p.provider = 'custom';
                                    if(!p.icon) p.icon = presets[p.provider]?.icon || '⚙️';
                                });
                                profiles.value = data.profiles;
                                activeProfileId.value = data.activeId || (data.profiles[0] ? data.profiles[0].id : null);
                                showToast('📥 備份配置已成功還原！', 'success');
                                sync();
                            } else { showToast('❌ 檔案格式不正確', 'error'); }
                        } catch (err) { showToast('❌ 解析檔案失敗', 'error'); }
                        event.target.value = '';
                    };
                    reader.readAsText(file);
                };

                const activeProfile = computed(() => profiles.value.find(p => p.id === activeProfileId.value));
                
                onMounted(() => {
                    const saved = localStorage.getItem('codex_profiles');
                    if (saved) { 
                        profiles.value = JSON.parse(saved); 
                        profiles.value.forEach(p => {
                            if(!p.provider) p.provider = 'custom';
                            if(!p.icon) p.icon = presets[p.provider]?.icon || '⚙️';
                        });
                        activeProfileId.value = localStorage.getItem('codex_active_id'); 
                    } else { 
                        createNewProfile(); 
                    }
                    sync();
                });

                watch([profiles, activeProfileId], () => {
                    localStorage.setItem('codex_profiles', JSON.stringify(profiles.value));
                    localStorage.setItem('codex_active_id', activeProfileId.value);
                    sync();
                }, { deep: true });

                const sync = async () => {
                    if (!activeProfile.value) return;
                    try {
                        const cleanKey = activeProfile.value.apiKey ? activeProfile.value.apiKey.trim() : '';
                        await fetch('/relay/v1/internal/sync', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ base_url: activeProfile.value.baseUrl.trim(), api_key: cleanKey, model: activeProfile.value.model.trim() })
                        });
                        syncStatus.value = 'Synced';
                    } catch(e) { syncStatus.value = 'Error'; }
                };

                const createNewProfile = () => {
                    const id = Date.now().toString();
                    profiles.value.unshift({ id, name: '未命名節點', provider: 'custom', baseUrl: '', apiKey: '', model: '', icon: '⚙️' });
                    activeProfileId.value = id; 
                    isEditing.value = true;
                };

                const selectProfile = (id) => { activeProfileId.value = id; };

                const enableProfile = (id) => {
                    activeProfileId.value = id;
                    showToast(`已切換驅動引擎：${activeProfile.value.name}`);
                };

                const editProfile = (id) => { activeProfileId.value = id; isEditing.value = true; };

                const testProfile = async (p) => {
                    showToast(`測試連線中...`, 'success');
                    try {
                        const cleanKey = p.apiKey ? p.apiKey.trim() : '';
                        const res = await fetch('/relay/v1/models', { headers: { 'X-Upstream-Base': p.baseUrl.trim(), 'Authorization': `Bearer ${cleanKey}` }});
                        if(res.ok) showToast(`✅ [${p.name}] 連線成功！`, 'success');
                        else showToast(`❌ 連線失敗 (HTTP ${res.status})`, 'error');
                    } catch(e) { showToast(`❌ 網路錯誤，請檢查 URL`, 'error'); }
                };

                const applyPreset = () => {
                    const p = presets[activeProfile.value.provider];
                    if(p) { 
                        activeProfile.value.baseUrl = p.url; 
                        activeProfile.value.icon = p.icon;
                        if(p.model) activeProfile.value.model = p.model; 
                        
                        const currentName = activeProfile.value.name || '';
                        const isDefaultName = currentName === '' || 
                                              currentName === '未命名節點' || 
                                              currentName === '新配置' || 
                                              currentName.includes('節點');
                        const isAnyPresetName = Object.values(presets).some(preset => preset.name === currentName);

                        if (isDefaultName || isAnyPresetName) {
                            activeProfile.value.name = p.name;
                        }
                    }
                };

                const fetchModels = async () => {
                    loadingModels.value = true;
                    try {
                        const cleanKey = activeProfile.value.apiKey ? activeProfile.value.apiKey.trim() : '';
                        const res = await fetch('/relay/v1/models', { headers: { 'X-Upstream-Base': activeProfile.value.baseUrl.trim(), 'Authorization': `Bearer ${cleanKey}` }});
                        const d = await res.json(); 
                        let rawModels = d.data || d.models || d;
                        fetchedModels.value = rawModels.sort((a, b) => {
                            const nameA = (a.id || a).toLowerCase();
                            const nameB = (b.id || b).toLowerCase();
                            return nameA.localeCompare(nameB);
                        });
                        
                        if(fetchedModels.value.length > 0) {
                            showModelDropdown.value = true;
                            showToast(`成功獲取 ${fetchedModels.value.length} 個模型`, 'success');
                        } else {
                            showToast(`獲取成功，但清單為空`, 'error');
                        }
                    } catch(e) { 
                        showToast(`獲取失敗，請檢查 API Key`, 'error'); 
                    } finally { 
                        loadingModels.value = false; 
                    }
                };

                const selectModel = (modelId) => {
                    activeProfile.value.model = modelId;
                    showModelDropdown.value = false;
                };

                const saveAndExit = () => {
                    isEditing.value = false;
                    showToast('配置已儲存並啟用 ✨');
                };

                const send = async () => {
                    if(!input.value.trim() || gen.value) return;
                    const txt = input.value; input.value = ''; gen.value = true;
                    chatHistory.value.push({ role: 'user', content: txt }); 
                    chatHistory.value.push({ role: 'assistant', content: '' });
                    const idx = chatHistory.value.length - 1;
                    try {
                        const cleanKey = activeProfile.value.apiKey ? activeProfile.value.apiKey.trim() : '';
                        const res = await fetch('/relay/v1/chat/completions', {
                            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Upstream-Base': activeProfile.value.baseUrl.trim(), 'Authorization': `Bearer ${cleanKey}` },
                            body: JSON.stringify({ model: activeProfile.value.model.trim(), messages: chatHistory.value.slice(0, -1), stream: true })
                        });
                        const reader = res.body.getReader(); const decoder = new TextDecoder();
                        while(true) {
                            const {done, value} = await reader.read(); if(done) break;
                            decoder.decode(value).split('\n').forEach(l => {
                                if(l.startsWith('data: ') && l !== 'data: [DONE]') {
                                    try {
                                        const d = JSON.parse(l.substring(6)).choices[0].delta;
                                        chatHistory.value[idx].content += d.content || '';
                                        nextTick(() => { const b = document.getElementById('chatBox'); b.scrollTop = b.scrollHeight; });
                                    } catch(e){}
                                }
                            });
                        }
                    } catch(e) { chatHistory.value[idx].content = '錯誤: ' + e.message; } finally { gen.value = false; }
                };

                return { 
                    presets, profiles, activeProfileId, activeProfile, isEditing, 
                    chatHistory, input, gen, fetchedModels, loadingModels, syncStatus, 
                    showModelDropdown, toast, showToast, fileInput, sortedProfiles,
                    copyConfig, exportConfig, importConfig, showFullKey,
                    draggedIndex, dragOverIndex, onDragStart, onDragOver, onDragLeave, onDragEnd, onDrop,
                    createNewProfile, selectProfile, enableProfile, editProfile, testProfile,
                    deleteProfile: (id) => { profiles.value = profiles.value.filter(p => p.id !== id); if(activeProfileId.value === id) activeProfileId.value = profiles.value[0]?.id; }, 
                    applyPreset, fetchModels, selectModel, saveAndExit, send, 
                    renderMd: (t) => marked.parse(t) 
                };
            }
        }).mount('#app');
    </script>
</body>
</html>
"""

# ==========================================
# 2. 後端核心邏輯 (FastAPI & HTTPX)
# ==========================================
app = FastAPI()

class SyncPayload(BaseModel):
    base_url: str
    api_key: str
    model: str

def sse_message(event_name: str, payload: dict) -> bytes:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")

def value_to_text(v) -> str:
    if v is None: return ""
    if isinstance(v, str): return v
    if isinstance(v, list):
        return "".join([p.get("text", "") for p in v if isinstance(p, dict) and "text" in p])
    if isinstance(v, dict):
        return v.get("text", "")
    return str(v)

def convert_tool(tool: dict) -> dict:
    if "function" in tool: return tool
    if tool.get("type") == "function":
        func = {}
        for k in ["name", "description", "parameters", "strict"]:
            if k in tool: func[k] = tool[k]
        return {"type": "function", "function": func}
    return tool

@app.get("/", response_class=HTMLResponse)
async def get_index(): return HTML_CONTENT

@app.post("/relay/v1/internal/sync")
async def sync_state(payload: SyncPayload):
    global ACTIVE_PROFILE_STATE
    try: data = payload.model_dump()
    except AttributeError: data = payload.dict()
    ACTIVE_PROFILE_STATE.update(data) 
    logger.info(f"🔄 同步成功: {ACTIVE_PROFILE_STATE['model']}")
    return {"status": "success"}

@app.get("/relay/v1/models")
async def proxy_models(request: Request):
    base_url = request.headers.get("X-Upstream-Base", "").rstrip('/')
    auth = request.headers.get("Authorization", "")
    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        try:
            res = await client.get(f"{base_url}/models", headers={"Authorization": auth})
            return res.json()
        except: return {"data": []}

async def stream_generator(upstream_url: str, headers: dict, payload: dict, is_codex_app: bool):
    res_id = f"res_{uuid.uuid4().hex[:8]}"
    msg_item_id = f"msg_{uuid.uuid4().hex[:8]}"
    model_name = payload.get("model", "unknown")
    
    async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
        try:
            payload["stream"] = True 
            async with client.stream("POST", upstream_url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    err = (await response.aread()).decode(errors="ignore")
                    logger.error(f"❌ 上游錯誤: {err}")
                    yield sse_message("response.failed", {"error": err})
                    yield b"data: [DONE]\n\n"
                    return

                if is_codex_app:
                    yield sse_message("response.created", {
                        "type": "response.created",
                        "response": {"id": res_id, "status": "in_progress", "model": model_name}
                    })

                accumulated_text = ""
                accumulated_reasoning = "" 
                tool_calls = {} 
                emitted_message_item = False
                stream_done = False

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "): continue
                    raw_data = line[6:]
                    if raw_data.strip() == "[DONE]":
                        stream_done = True
                        break
                    
                    try:
                        chunk = json.loads(raw_data)
                        choices = chunk.get("choices", [])
                        if not choices: continue
                        
                        delta = choices[0].get("delta", {})
                        
                        if delta.get("reasoning_content"):
                            accumulated_reasoning += delta["reasoning_content"]

                        content = delta.get("content") or ""

                        if is_codex_app:
                            if content:
                                if not emitted_message_item:
                                    yield sse_message("response.output_item.added", {
                                        "type": "response.output_item.added", "output_index": 0,
                                        "item": {"type": "message", "id": msg_item_id, "role": "assistant", "status": "in_progress", "content": []}
                                    })
                                    emitted_message_item = True
                                
                                accumulated_text += content
                                yield sse_message("response.output_text.delta", {
                                    "type": "response.output_text.delta", "item_id": msg_item_id, "output_index": 0, "delta": content
                                })
                            
                            for tc in delta.get("tool_calls", []):
                                idx = tc.get("index", 0)
                                if idx not in tool_calls:
                                    tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                                if tc.get("id"): tool_calls[idx]["id"] = tc["id"]
                                if tc.get("function"):
                                    if tc["function"].get("name"): tool_calls[idx]["name"] += tc["function"]["name"]
                                    if tc["function"].get("arguments"): tool_calls[idx]["arguments"] += tc["function"]["arguments"]
                        else:
                            yield f"{line}\n\n".encode("utf-8")
                    except Exception as e:
                        continue

                if is_codex_app and stream_done:
                    if accumulated_reasoning:
                        if accumulated_text:
                            text_hash = hashlib.md5(accumulated_text.encode('utf-8')).hexdigest()
                            GLOBAL_REASONING_STORE[text_hash] = accumulated_reasoning
                        for tc in tool_calls.values():
                            if tc["id"]:
                                GLOBAL_TOOL_REASONING_STORE[tc["id"]] = accumulated_reasoning

                    output_items = []
                    
                    if emitted_message_item:
                        yield sse_message("response.output_item.done", {
                            "type": "response.output_item.done", "output_index": 0,
                            "item": {"type": "message", "id": msg_item_id, "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": accumulated_text}]}
                        })
                        output_items.append({
                            "type": "message", "id": msg_item_id, "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": accumulated_text}]
                        })

                    base_index = 1 if emitted_message_item else 0
                    for rel_idx, (idx, tc) in enumerate(sorted(tool_calls.items())):
                        fc_item_id = f"fc_{uuid.uuid4().hex[:8]}"
                        out_idx = base_index + rel_idx
                        
                        yield sse_message("response.output_item.added", {
                            "type": "response.output_item.added", "output_index": out_idx,
                            "item": {"type": "function_call", "id": fc_item_id, "call_id": tc["id"], "name": tc["name"], "arguments": "", "status": "in_progress"}
                        })
                        
                        if tc["arguments"]:
                            yield sse_message("response.function_call_arguments.delta", {
                                "type": "response.function_call_arguments.delta", "item_id": fc_item_id, "output_index": out_idx, "delta": tc["arguments"]
                            })
                            
                        yield sse_message("response.output_item.done", {
                            "type": "response.output_item.done", "output_index": out_idx,
                            "item": {"type": "function_call", "id": fc_item_id, "call_id": tc["id"], "name": tc["name"], "arguments": tc["arguments"], "status": "completed"}
                        })
                        
                        output_items.append({
                            "type": "function_call", "id": fc_item_id, "call_id": tc["id"], "name": tc["name"], "arguments": tc["arguments"], "status": "completed"
                        })

                    yield sse_message("response.completed", {
                        "type": "response.completed", "response": {"id": res_id, "status": "completed", "model": model_name, "output": output_items}
                    })
                
                yield b"data: [DONE]\n\n"
                logger.info("✅ 串流結束，完美轉發文字與工具！")

        except Exception as e:
            logger.error(f"💥 崩潰: {str(e)}")
            yield b"data: [DONE]\n\n"

@app.post("/relay/v1/chat/completions")
@app.post("/relay/v1/responses")
@app.post("/v1/chat/completions")
@app.post("/v1/responses")
async def main_proxy(request: Request):
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    is_from_web = "X-Upstream-Base" in request.headers
    
    if is_from_web:
        base_url = request.headers.get("X-Upstream-Base", "").rstrip('/')
        auth = request.headers.get("Authorization", "")
        model = body.get("model")
    else:
        global ACTIVE_PROFILE_STATE
        base_url = ACTIVE_PROFILE_STATE["base_url"]
        auth = f"Bearer {ACTIVE_PROFILE_STATE['api_key']}"
        model = ACTIVE_PROFILE_STATE["model"]
        
        instructions = body.pop("instructions", None)
        history = body.pop("messages", [])
        current_input = body.pop("input", None)
        
        all_items = []
        if isinstance(history, list): all_items.extend(history)
        if isinstance(current_input, list): all_items.extend(current_input)
        elif isinstance(current_input, str): all_items.append({"role": "user", "content": current_input})

        msgs = []
        if instructions: 
            strict_prompt = str(instructions) + "\n\n[CRITICAL]: Directly execute the user's request. NEVER output internal reasoning, preambles, or conversational filler like 'Let me think' or 'Sure'."
            msgs.append({"role": "system", "content": strict_prompt})

        i = 0
        while i < len(all_items):
            item = all_items[i]
            if not isinstance(item, dict):
                i += 1
                continue
                
            item_type = item.get("type", "")
            
            if item_type == "function_call":
                grouped_tools = []
                reasoning = None
                while i < len(all_items):
                    cur = all_items[i]
                    if not isinstance(cur, dict) or cur.get("type") != "function_call":
                        break
                    call_id = cur.get("call_id", "")
                    if call_id in GLOBAL_TOOL_REASONING_STORE:
                        reasoning = GLOBAL_TOOL_REASONING_STORE[call_id]

                    args = cur.get("arguments", "{}")
                    if isinstance(args, dict):
                        args = json.dumps(args, ensure_ascii=False)
                    elif not isinstance(args, str):
                        args = str(args)

                    grouped_tools.append({
                        "id": call_id,
                        "type": "function",
                        "function": {"name": str(cur.get("name", "")), "arguments": args}
                    })
                    i += 1
                
                # 修復點：將 None 改為 ""，避免 DeepSeek 報錯
                msg_obj = {"role": "assistant", "content": "", "tool_calls": grouped_tools}
                if reasoning:
                    msg_obj["reasoning_content"] = reasoning
                msgs.append(msg_obj)
                continue
                
            elif item_type == "function_call_output":
                output_val = item.get("output", "")
                if isinstance(output_val, dict):
                    output_val = json.dumps(output_val, ensure_ascii=False)
                else:
                    output_val = str(output_val)
                    
                msgs.append({"role": "tool", "content": output_val, "tool_call_id": str(item.get("call_id", ""))})
                
            else:
                role = item.get("role", "user")
                if role == "developer": role = "system"
                
                content_str = value_to_text(item.get("content"))
                
                msg_obj = {"role": str(role), "content": content_str}
                if role == "assistant" and content_str:
                    text_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
                    if text_hash in GLOBAL_REASONING_STORE:
                        msg_obj["reasoning_content"] = GLOBAL_REASONING_STORE[text_hash]

                msgs.append(msg_obj)
                
            i += 1

        # ==========================================
        # 修復邏輯：清理「斷層」的 tool_calls
        # (解決 insufficient tool messages following tool_calls 報錯)
        # ==========================================
        valid_msgs = []
        pending_tcs = {} 

        for m in msgs:
            role = m.get("role")
            if role == "assistant" and m.get("tool_calls"):
                valid_msgs.append(m)
                for tc in m["tool_calls"]:
                    pending_tcs[tc["id"]] = m
            elif role == "tool":
                tc_id = m.get("tool_call_id")
                if tc_id in pending_tcs:
                    del pending_tcs[tc_id]
                    valid_msgs.append(m)
            else:
                if pending_tcs:
                    for t_id, ast_m in pending_tcs.items():
                        ast_m["tool_calls"] = [tc for tc in ast_m.get("tool_calls", []) if tc["id"] != t_id]
                        if not ast_m["tool_calls"]:
                            ast_m.pop("tool_calls", None)
                            if not ast_m.get("content"):
                                ast_m["content"] = "[工具調用已中斷]"
                    pending_tcs.clear()
                valid_msgs.append(m)

        if pending_tcs:
            for t_id, ast_m in pending_tcs.items():
                ast_m["tool_calls"] = [tc for tc in ast_m.get("tool_calls", []) if tc["id"] != t_id]
                if not ast_m["tool_calls"]:
                    ast_m.pop("tool_calls", None)
                    if not ast_m.get("content"):
                        ast_m["content"] = "[工具調用已中斷]"
            pending_tcs.clear()

        msgs = [m for m in valid_msgs if m.get("content") or m.get("tool_calls")]
        # ==========================================

        if not msgs: msgs.append({"role": "user", "content": "hello"})
        body["messages"] = msgs

        raw_tools = body.pop("tools", [])
        if raw_tools:
            converted_tools = []
            for t in raw_tools:
                t_type = t.get("type")
                if t_type == "function": converted_tools.append(convert_tool(t))
                elif t_type == "namespace":
                    for sub in t.get("tools", []):
                        if sub.get("type") == "function": converted_tools.append(convert_tool(sub))
            if converted_tools:
                body["tools"] = converted_tools

        body["model"] = model

        for garbage_key in [
            "prompt", "input", "instructions", "tool_choice", 
            "workspace_context", "files", "prompt_cache_key", 
            "reasoning", "include", "client_metadata", 
            "truncation_strategy", "parallel_tool_calls"
        ]:
            body.pop(garbage_key, None)

    headers = {
        "Authorization": auth,
        "HTTP-Referer": "http://127.0.0.1:4446",
        "X-Title": "Codex Web Relay",
        "Content-Type": "application/json"
    }
    
    logger.info(f"🚀 轉發至: {base_url} | 模型: {model}")
    return StreamingResponse(
        stream_generator(f"{base_url}/chat/completions", headers, body, not is_from_web),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    try:
        print("=====================================================")
        print("🚀 Codex Web Relay (魔法玻璃旗艦版) 啟動成功！")
        print("👉 請在瀏覽器開啟: http://127.0.0.1:4446")
        print("=====================================================")
        uvicorn.run(app, host="0.0.0.0", port=4446, log_level="warning")
    except Exception as e:
        print("\n" + "!"*60)
        print("❌ 發生致命錯誤，導致伺服器崩潰！")
        print("!"*60)
        print(f"錯誤訊息: {str(e)}")
        
        if "10048" in str(e) or "address already in use" in str(e).lower():
            print("\n💡 診斷結果：【4446 通訊埠已被佔用】")
            print("這代表你之前運行的 Python 腳本雖然關閉了視窗，但程式還在系統背景偷跑！")
            print("👉 解決方法：")
            print("   1. 打開 Windows 工作管理員 (快捷鍵：Ctrl + Shift + Esc)")
            print("   2. 在「詳細資料」或「處理程序」中找到所有的 `python.exe`")
            print("   3. 右鍵點擊它們並選擇【結束任務】")
            print("   4. 再次點擊本腳本重新執行即可。")
        else:
            print("\n🔍 詳細追蹤日誌 (Traceback):")
            traceback.print_exc()
            
        print("\n" + "="*60)
        input("請按 Enter 鍵關閉此視窗...")