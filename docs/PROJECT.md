# 🚀 EuoraCraft Launcher — 项目文档

> 最后更新: 2026-06-05 19:35 CST

---

## 一、项目简介

**EuoraCraft Launcher** 是一个 Minecraft 启动器，支持版本管理、多账户登录、游戏启动与实例管理。

### 技术栈

| 层 | 技术 | 角色 |
|----|------|------|
| **UI** | Vue 3 + TypeScript + Vite | 用户界面 |
| **框架** | Tauri v2 | 跨平台桌面壳 |
| **后端** | Python (通过 pytauri/PyO3 嵌入) | 核心业务逻辑 |
| **桥接** | pytauri v0.8 | Rust ↔ Python IPC |
| **样式** | Tailwind CSS v4 + Naive UI | 组件库与主题 |

### 当前架构

```
┌──────────────────────────────────────────────┐
│  Tauri v2 (Rust 二进制)                        │
│  ├── WebView (Vue 3 前端)                     │
│  │   └── @tauri-apps/api (invoke IPC)         │
│  ├── Python (PyO3 嵌入)                       │
│  │   ├── python/commands.py (IPC 命令注册)     │
│  │   └── python/launcher.py (应用主入口)        │
│  └── Python 后端库                              │
│      └── python/ECL/                         │
└──────────────────────────────────────────────┘
```

---

## 二、主任务：完全迁移至 pytauri

### 背景

项目最初基于 **pywebview** 构建，Python 是主进程，前端通过 `window.pywebview.api.xxx()` 调用 Python 方法。

现在迁移到 **pytauri**（Tauri v2 + Python 嵌入），Rust 成为主进程，Python 作为子进程运行，IPC 通过 Tauri 的 `invoke()` 机制。

### ✅ 已完成

| 任务 | 状态 | 说明 |
|------|------|------|
| Rust/Tauri 项目结构 | ✅ | `src-tauri/` — main.rs + lib.rs + Cargo.toml |
| Python 侧车 | ✅ | `python/launcher.py` + `python/commands.py` |
| pytauri 命令注册 | ✅ | 40+ 个命令 (config, accounts, java, launch, skin...) |
| 前端 API 客户端 | ✅ | `EuoraCraft-UI/src/api/client.ts` — 全部使用 Tauri invoke |
| 前端旧 API 清除 | ✅ | 无 `window.pywebview` 残留调用 |
| 窗口控制 | ✅ | minimize/close/maximize 通过 Tauri API |
| 文件对话框 | ✅ | 使用 `@tauri-apps/plugin-dialog` |
| 皮肤模块 | ✅ | `get_avatar_data_url` 已迁移 |
| 用户协议 | ✅ | 读写 `user_agreement.json` |
| 配置管理 | ✅ | 全部 ConfigManager 方法已注册为命令 |
| 游戏启动 | ✅ | `launch_game`/`launch_instance`/状态轮询 |
| 版本管理 | ✅ | 扫描/安装/卸载 |
| 账户管理 | ✅ | 离线 + Microsoft 登录 |
| cargo check 通过 | ✅ | 项目编译验证成功 |

### ❌ 待完成

| # | 任务 | 优先级 | 详情 |
|---|------|--------|------|
| # | 任务 | 优先级 | 详情 | 状态 |
|---|------|--------|------|------|
| 1 | **清理旧代码** | 🔴 高 | `ECL/ui/ui.py` — 旧 pywebview Api 类（510 行），不再被调用 | ✅ 已删除 |
| 2 | **合并后端层** | 🔴 高 | `ECL/` 移至 `python/ECL/`，`sys.path.insert` 指向 `python/` 目录 | ✅ 已完成 |
| 3 | **清理旧入口** | 🟡 中 | `main.py` + `ECL/launcher.py` — 旧 pywebview 入口 | ✅ 已删除 |
| 4 | **移除旧依赖** | 🟡 中 | `requirements.txt` 中的 `pywebview`、`bottle` 等旧依赖 | ✅ 已删除 |
| 5 | **前端 API 对齐** | 🟡 中 | 缺 `get_window_position`/`set_window_position` — 低优先级，前端 Tauri API 可替代 | ⏳ 低优搁置 |
| 6 | **回退合并** | 🟢 低 | `blur` 值同步 `theme.blur_amount` | ✅ 已在 `update_background_config` 中实现 |
| 7 | **开发脚本更新** | 🟢 低 | `run_dev.py` 未纳入 Git 跟踪 | ⏳ 待确认 |
| 8 | **图标/资源路径** | 🟢 低 | 启动时从 `resources/Skins/` 复制到 `ECL_Libs/Skins/` | ✅ 已在 `launcher.py` 中实现 |
| 9 | **构建验证** | 🔴 高 | `cargo tauri build` 尚未测试 | ❌ 待测试 |
| 10 | **文档更新** | 🟢 低 | `docs/MIGRATION_PYTAURI.md` 需要更新为最终架构说明 | ❌ 待更新 |

### 功能覆盖检查

对照旧 `Api.__dir__()` 的方法列表，检查 pytauri `commands.py` 覆盖情况：

```
旧 Api 方法                           pytauri commands    状态
─────────────────────────────────    ──────────────────   ──────
minimize_window                     ✅ minimize_window    完成
close_window                        ✅ close_window       完成
get_window_position                 ❌ 未实现             低优搁置（前端 Tauri API）
set_window_position                 ❌ 未实现             低优搁置（前端 Tauri API）
get_launcher_config                 ✅ get_launcher_config 完成
get_background_config               ✅ get_background_config 完成
get_background_image                ✅ get_background_image 完成
update_background_config            ✅ update_background_config 完成（含 blur 同步）
update_background_image             ✅ update_background_image 完成
load_image_from_url                 ✅ load_image_from_url 完成
fetch_image_data_url                ❌ 未实现             缺失（图片代理）
get_avatar_data_url                 ✅ get_avatar_data_url 完成
load_image_from_local               ❌ 未实现             缺失
select_local_image                  ✅ select_local_image 完成
get_game_config                     ✅ get_game_config    完成
update_game_config                  ✅ update_game_config 完成
get_java_list                       ✅ get_java_list      完成
get_theme_config                    ✅ get_theme_config   完成
update_theme_config                 ✅ update_theme_config 完成
get_download_config                 ✅ get_download_config 完成
update_download_config              ✅ update_download_config 完成
get_mouse_effect_config             ✅ get_mouse_effect_config 完成
update_mouse_effect_config          ✅ update_mouse_effect_config 完成
get_locale_config                   ✅ get_locale_config  完成
update_locale_config                ✅ update_locale_config 完成
select_directory                    ✅ select_directory   完成
select_java_executable              ✅ select_java_executable 完成
scan_versions_in_path               ✅ scan_versions_in_path 完成
get_minecraft_versions              ✅ get_minecraft_versions 完成
get_fabric_versions                 ✅ get_fabric_versions 完成
install_version                     ❌ 未实现             缺失（待对接）
uninstall_version                   ✅ uninstall_version  完成
ping                                ✅ ping               完成
get_user_agreement_status           ✅ get_user_agreement_status 完成
save_user_agreement                 ✅ save_user_agreement 完成
clear_user_agreement                ✅ clear_user_agreement ✅ 新增
refresh_account_profile             ✅ refresh_account_profile ✅ 新增
get_accounts                        ✅ get_accounts       完成
get_current_account                 ✅ get_current_account 完成
add_offline_account                 ✅ add_offline_account 完成
start_microsoft_login               ✅ start_microsoft_login 完成
poll_microsoft_login                ✅ poll_microsoft_login 完成
complete_microsoft_login            ✅ complete_microsoft_login 完成
switch_account                      ✅ switch_account     完成
remove_account                      ✅ remove_account     完成
get_game_instances                  ✅ get_game_instances 完成
launch_instance                     ✅ launch_instance    完成
get_launch_status                   ✅ get_launch_status  完成
stop_instance                       ✅ stop_instance      完成
```

> **仍缺失 3 个方法：**
> - `get_window_position` / `set_window_position` — 低优先级，可通过 Tauri 窗口 API 在前端侧实现
> - `fetch_image_data_url` — 图片代理下载，用于绕过 CORS 加载网络图片
> - `load_image_from_local` — 验证本地图片文件合法性
> - `install_version` — 版本安装（旧版标记为"待对接"，实际上未实现过）

---

## 三、项目文件结构

```
EuoraCraft-Launcher/              ← Git 仓库根
│
├── python/                       ← Python 后端 (pytauri)
│   ├── ECL/                      ECL 核心模块
│   │   ├── Core/                 配置、日志
│   │   ├── Game/                 游戏引擎 (Java/账户/启动/皮肤)
│   │   └── ui/                   🗑️ 旧 Api (保留参考)
│   ├── commands.py               46+ IPC 命令
│   └── launcher.py               Rust 调用的主入口
│
├── src-tauri/                    ← Rust / Tauri 核心
│   ├── Cargo.toml                tauri v2 + pyo3 + pytauri v0.8
│   ├── tauri.conf.json           Tauri 配置
│   ├── src/main.rs               Rust 入口
│   ├── src/lib.rs                PyO3 扩展
│   ├── capabilities/             权限
│   ├── gen/schemas/              自动生成
│   └── icons/                    图标
│
├── EuoraCraft-UI/                ← Vue 3 前端 (独立仓库)
│   ├── src/                      源码
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json
│   └── ...
│
├── resources/Skins/              ← 默认皮肤源文件
├── scripts/                      ← 开发脚本
│   └── run_dev.py                直接 Python 运行
├── tests/                        ← 测试用例
├── docs/                         ← 文档
│   ├── PROJECT.md                本文件
│   ├── FILE_CLASSIFICATION.md    文件分类
│   └── MIGRATION_PYTAURI.md      迁移指南
├── archive/legacy/               ← 🗄️ 旧 pywebview 项目
│
├── .cargo/                       Rust 配置
├── .env.dev                      开发环境变量
├── .gitignore
├── pyproject.toml                Python 包配置
├── CHANGELOG.md
├── LICENSE
└── README.md
```

> 📌 `python/ECL/` 继承了原 `EuoraCraft-Launcher/ECL/` 的完整代码，
> 项目根部的 `EuoraCraft-Launcher/` 已归档至 `archive/legacy/`。
```

---

## 四、开发工作流

### 前置条件

| 工具 | 版本要求 |
|------|---------|
| Rust | stable (1.75+) |
| Python | 3.11+ |
| Node.js | 18+ |
| pnpm | latest |

### 运行开发模式

```bash
# 终端 1: 前端开发服务器
cd EuoraCraft-UI
pnpm install
pnpm dev

# 终端 2: Tauri 开发模式 (会自动连接前端 dev server)
cd src-tauri
cargo tauri dev
```

### 构建发布

```bash
cd src-tauri
cargo tauri build
# 输出: src-tauri/target/release/EuoraCraft Launcher.exe
```

### 快速 Python 调试 (无需 Rust)

```bash
python scripts/run_dev.py
```
需要先编译 `_pytauri_ext.pyd`（Rust 代码未改时只需编译一次）。

---

## 五、Git 历史

```
f7c879c 🎉 初始提交：pywebview 版本
11cf66e 🧹 清理冗余代码
cbd1948 🚀 迁移至 pytauri (Tauri v2 + Python)
fc46bbb 🔧 修复 Rust 依赖
758dab7 ✅ cargo check 通过
```

当前有未提交的修改（2026-06-05），包括 config、commands、前端等文件的进一步改进。
