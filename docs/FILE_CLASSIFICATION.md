# 📂 EuoraCraft-Launcher — 文件归属分类

> 分析目录: `E:\Projects\EuoraCraft-Launcher\EuoraCraft-Launcher`
> Git 仓库: **单体仓库**（无 submodule，162 个跟踪文件）

---

## 一、全局结论

| 项目 | 值 |
|------|-----|
| Git 仓库数 | **1** (单体) |
| Submodule 数 | **0** |
| 跟踪文件 | **162** |
| 忽略文件 | ~102,627 (主要是 `.venv/` 和 `node_modules/`) |
| 未跟踪(未忽略) | **10** (含 run_dev.py, ECL_Libs/Skins/*.png) |

> ⚠️ **整个项目是一个 monorepo。** `EuoraCraft-Launcher/`、`EuoraCraft-UI/`、`src-tauri/`、`python/` 等子目录全部属于同一个 Git 仓库，不存在跨仓库嵌套。

---

## 二、严格按子目录分类

### 🔵 模块 A — Python 后端（旧版 pywebview → 迁移中）
**目录: `EuoraCraft-Launcher/`** — 44 个跟踪文件

| 分类 | 文件 | 可拆? |
|------|------|-------|
| 入口 | `main.py` | ⚠️ 依赖 `src-tauri/` + `EuoraCraft-UI/` |
| 核心 | `ECL/__init__.py`, `ECL/launcher.py` | |
| Config | `ECL/Core/__init__.py`, `ECL/Core/config.py`, `ECL/Core/logger.py` | |
| 游戏 | `ECL/Game/__init__.py` | |
| │ 账号 | `ECL/Game/AccountManager.py`, `ECL/Game/MicrosoftAuth.py` | |
| │ Java | `ECL/Game/java.py` | |
| │ 核心 | `ECL/Game/Core/__init__.py`, `ECL/Game/Core/ECLauncherCore.py`, `ECL/Game/Core/InstancesManager.py` | |
| │ │ 下载 | `ECL/Game/Core/C_Downloader.py` | |
| │ │ 校验 | `ECL/Game/Core/C_FilesChecker.py` | |
| │ │ 游戏列表 | `ECL/Game/Core/C_GetGames.py` | |
| │ │ 库 | `ECL/Game/Core/C_Libs.py` | |
| │ │ 皮肤 | `ECL/Game/Core/C_Skin.py` | |
| UI (旧) | `ECL/ui/__init__.py`, `ECL/ui/ui.py` | ✅ 可拆（已迁移到 Tauri） |
| 测试 | `test/Core/*.py` (×6) | |
| 资源 | `resources/Skins/*.png` (×9) | |
| 元数据 | `pyproject.toml`, `requirements.txt`, `EuoraCraft-Launcher.pyproj`, `EuoraCraft-Launcher.spec` | |
| 文档 | `LICENSE`, `README.md`, `CHANGELOG.md`, `docs/ReadME.md` | |
| 忽略 | `.gitignore` | |

### 🔴 模块 B — Vue.js 前端（Tauri WebView）
**目录: `EuoraCraft-UI/`** — 87 个跟踪文件

| 分类 | 文件 | 可拆? |
|------|------|-------|
| 构建 | `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json` | ✅ **可拆为独立 UI 仓库**（依赖 `src-tauri/` 接口约定） |
| 包管理 | `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `postcss.config.js`, `tailwind.config.js` | |
| 入口 | `index.html`, `src/main.ts`, `src/App.vue` | |
| 路由 | `src/router/index.ts` | |
| 视图 | `src/views/Game.vue`, `src/views/Settings.vue`, `src/views/Versions.vue`, `src/views/Instances.vue` | |
| ├ 子视图 | `src/views/settings/AboutTab.vue`, `src/views/settings/GameTab.vue`, `src/views/settings/GeneralTab.vue` | |
| ├ 子视图 | `src/views/versions/ManageTab.vue`, `src/views/versions/ModsTab.vue`, `src/views/versions/VersionsTab.vue` | |
| ├ 工具 | `src/views/DevTools.vue` | |
| 组件 | `src/components/ui/Button.vue`, `Card.vue`, `GlassMessage.vue`, `Icon.vue`, `IconButton.vue`, `Info.vue`, `Input.vue`, `Modal.vue`, `Select.vue`, `Switch.vue`, `Tabs.vue` | |
| ├ 组件 | `src/components/ui/index.ts` | |
| ├ 布局 | `src/components/layout/SideBar.vue`, `src/components/layout/TitleBar.vue` | |
| ├ 弹窗 | `src/components/modals/ContentModal.vue`, `src/components/modals/LaunchProgressModal.vue` | |
| ├ 动画 | `src/components/animation/BlurText.vue`, `src/components/animation/MouseEffect.vue`, `src/components/animation/SplitText.vue` | |
| ├ 渲染 | `src/components/SkinRenderer.vue` | |
| Composables | `src/composables/index.ts`, `useAccountManager.ts`, `useAnimation.ts`, `useAvatarRenderer.ts`, `useBackground.ts`, `useFullscreenModal.ts`, `useGlassMessage.ts`, `useLaunchProgress.ts`, `useTheme.ts`, `useUserAgreement.ts`, `useVersionManager.ts` | |
| 样式 | `src/styles/main.css`, `base.css`, `layout.css`, `animations.css` | |
| ├ 视图样式 | `src/styles/views/Game.css`, `Settings.css`, `Versions.css` | |
| ├ 组件样式 | `src/styles/components/Button.css`, `ContentModal.css`, `GlassMessage.css`, `SideBar.css`, `SkinRenderer.css`, `TitleBar.css` | |
| 国际化 | `src/i18n/index.ts`, `src/i18n/locales/zh-CN.json`, `src/i18n/locales/en-US.json` | |
| 类型 | `src/types/api.ts`, `src/types/global.d.ts` | |
| API | `src/api/client.ts` | |
| 缓存 | `src/cache/index.ts`, `src/cache/composable.ts` | |
| 公共 | `public/favicon.ico`, `public/fonts/MapleMono[wght].ttf`, `public/fonts/MiSansVF.ttf`, `public/mouse-effect.html` | |
| 配置 | `jsrepo.config.ts`, `components.d.ts`, `.npmrc`, `.gitignore` | |
| 元数据 | `LICENSE`, `README.md`, `docs/API_INTERFACE.md` | |

### 🟢 模块 C — Rust / Tauri 核心
**目录: `src-tauri/`** — 15 个跟踪文件

| 分类 | 文件 | 可拆? |
|------|------|-------|
| 源码 | `src/main.rs`, `src/lib.rs` | ❌ **不可拆**（业务逻辑在此） |
| 构建 | `build.rs`, `Cargo.toml`, `Cargo.lock` | |
| 配置 | `tauri.conf.json` | |
| 能力 | `capabilities/default.json` | |
| 模式 | `gen/schemas/acl-manifests.json`, `capabilities.json`, `desktop-schema.json`, `windows-schema.json` | |
| 图标 | `icons/32x32.png`, `icons/128x128.png`, `icons/128x128@2x.png`, `icons/icon.ico` | |

### 🟣 模块 D — Python 侧车（pytauri 版）
**目录: `python/`** — 3 个跟踪文件

| 文件 | 说明 |
|------|------|
| `__init__.py` | 包定义 |
| `commands.py` | Tauri 命令绑定 |
| `launcher.py` | 启动逻辑 |

> ⚠️ 与模块 A 的 `EuoraCraft-Launcher/ECL/` 有功能重叠。模块 A 是旧的 pywebview 实现，模块 D 是新的 pytauri 侧车。两者正逐步合并。

### 🟡 模块 E — 资源 / 皮肤
**目录: `ECL_Libs/`** — 9 个跟踪文件

```
ECL_Libs/Skins/{Alex,Ari,Efe,Kai,Makena,Noor,Steve,Sunny,Zuri}.png
```

> 与模块 A 的 `resources/Skins/` 重复。建议清理一份。

### ⚪ 模块 F — 文档
**目录: `docs/`** — 1 个跟踪文件

```
docs/MIGRATION_PYTAURI.md
```

### ⚪ 模块 G — Rust 工具链配置
**目录: `.cargo/`** — 1 个跟踪文件

```
.cargo/config.toml
```

### ⚪ 根级元数据 (4 文件)

```
.gitignore
pyproject.toml
```

---

## 三、可拆分性评估

| 模块 | 能否独立成仓库? | 依赖关系 | 建议 |
|------|---------------|---------|------|
| **B. EuoraCraft-UI/** | ✅ **可以** | 依赖 `src-tauri/` 的接口约定 + 命令 API | 最常见做法 — 大型 Tauri 项目多分开管理 |
| **D. python/** | ⚠️ 有条件 | 依赖 `src-tauri/` 的 pytauri 绑定 | 与模块 A 合并前暂不适合 |
| **A. EuoraCraft-Launcher/** | ⚠️ 有条件 | 旧后端，正在被模块 D 替代 | 等迁移完成后再处理 |
| **C. src-tauri/** | ❌ **不可拆** | 项目核心，依赖所有模块 | 留在主仓库 |
| **E. ECL_Libs/** | ✅ 可拆 | 纯资源，无代码依赖 | 可作为独立资源包或 Git LFS |

---

## 四、当前结构示意

```
EuoraCraft-Launcher/  ← [整个是一个 Git 仓库]
├── EuoraCraft-Launcher/  ← Python 后端 (旧版, 44 files)
├── EuoraCraft-UI/        ← Vue 前端     (87 files)  ✅ 最值得拆
├── src-tauri/            ← Rust/Tauri   (15 files)  ❌ 核心, 不拆
├── python/               ← Python 侧车  (3 files)   ⚠️ 合并后处理
├── ECL_Libs/             ← 资源/皮肤    (9 files)   ✅ 可拆
├── .cargo/               ← Rust 配置    (1 file)
├── docs/                 ← 迁移文档     (1 file)
├── pyproject.toml        ← 根级元数据
└── .gitignore
```

---

## 五、备注

- 所有子目录共用一个 `.gitignore`（根级），部分子目录有各自的 `.gitignore` 作为补充
- 有 **10 个未跟踪文件**：`run_dev.py`、`ECL_Libs/Skins/*.png` (×9) — 可能是开发便利或遗漏跟踪
- 模块 A 和模块 D 有功能重叠，建议完成 `pywebview → pytauri` 迁移后清理
