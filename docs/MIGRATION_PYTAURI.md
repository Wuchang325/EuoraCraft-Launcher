# pytauri 迁移指南

## 架构变化

```
旧 (pywebview):                   新 (pytauri):
┌──────────────────────┐          ┌──────────────────────────┐
│ Python (主进程)        │          │ Rust (Tauri 二进制)       │
│ ├── pywebview        │          │ ├── Webview 窗口          │
│ ├── ECL 核心逻辑      │          │ ├── Python (PyO3 嵌入)    │
│ ├── Api (JS 桥)      │          │ │  ├── Commands (IPC)    │
│ └── Vue 前端 (嵌入)   │          │ │  └── ECL 核心逻辑       │
└──────────────────────┘          │ └── Vue 前端 (Tauri 资产) │
                                  └──────────────────────────┘
```

## 主要变更

### 1. 前端 API 调用

**旧 (pywebview):**
```typescript
const result = await window.pywebview.api.getLauncherConfig()
```

**新 (pytauri):**
```typescript
import { invoke } from '@tauri-apps/api/core'
const result = await invoke('get_launcher_config')
```

### 2. 窗口控制

**旧:**
```typescript
window.pywebview.api.minimize_window()
```

**新:**
```typescript
import { getCurrentWindow } from '@tauri-apps/api/window'
await getCurrentWindow().minimize()
```

### 3. 文件对话框

**旧:**
```typescript
const result = await window.pywebview.api.selectDirectory()
```

**新:**
```typescript
import { open } from '@tauri-apps/plugin-dialog'
const selected = await open({ multiple: false, directory: true })
```

### 4. Python 命令

**旧 (ui.py):**
```python
class Api:
    def get_launcher_config(self) -> dict:
        ...
```

**新 (commands.py):**
```python
from pydantic import BaseModel
from pytauri import Commands

commands = Commands()

@commands.command()
async def get_launcher_config() -> ConfigResponse:
    ...
```

## 开发工作流

### 前置要求

1. **Rust 工具链** (https://rustup.rs)
   ```bash
   rustup default stable
   ```

2. **Python 3.11+** 并安装依赖
   ```bash
   pip install pytauri>=0.8 colorama requests ...
   ```

3. **Node.js 18+** 并安装前端依赖
   ```bash
   cd EuoraCraft-UI
   pnpm install
   ```

### 运行开发模式

```bash
# 终端 1: 启动 Vite 开发服务器
cd EuoraCraft-UI
pnpm dev

# 终端 2: 启动 Tauri 开发应用
cd src-tauri
cargo tauri dev
```

### 构建发布

```bash
cd src-tauri
cargo tauri build
# 输出: src-tauri/target/release/EuoraCraft Launcher.exe
```

## 项目文件结构

```
EuoraCraft-Launcher/
├── python/                    # Python 后端 (pytauri)
│   ├── __init__.py
│   ├── launcher.py           # 入口点 (Rust 调用)
│   ├── commands.py           # IPC 命令 (替换旧的 ui.py Api)
│   └── ECL/                  # 符号链接: -> ../EuoraCraft-Launcher/ECL/
├── src-tauri/                 # Rust/Tauri 项目
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── capabilities/
│   ├── icons/
│   └── src/
│       ├── lib.rs            # PyO3 扩展模块
│       └── main.rs           # 二进制入口
├── EuoraCraft-UI/            # Vue 前端 (更新为 Tauri API)
│   └── src/
│       ├── api/client.ts     # 替换: pywebview → Tauri invoke
│       └── ...
├── EuoraCraft-Launcher/      # 旧 Python 后端 (保留作为库)
└── pyproject.toml            # 项目配置
```
