# cc-anti — Claude Code ↔ Antigravity 对话导出工具

[English](./README_EN.md)

将 Claude Code 和 Antigravity 的对话历史互相转换，提供可视化 Web 管理界面。

![Python 3](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey)

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| **CC → 项目目录** | 将 Claude Code 对话导出为 `.cc_history.md`，放到项目根目录 |
| **AG → CC** | 将 Antigravity brain artifacts 生成 CC 可读的 JSONL 会话 |
| **AG ♻️ 恢复** | 将 Antigravity brain artifacts 导出到项目根目录（`ag_brain/`） |
| **Web UI** | 内置可视化界面，双栏浏览、预览、一键操作 |

## 🚀 快速开始

### 前提条件

- Python 3.8+
- 安装过 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 和/或 [Antigravity (Gemini)](https://gemini.google.com/)

### 运行

```bash
python3 cc-anti.py
```

工具将在 `http://localhost:8766` 启动 Web 界面，并自动在浏览器中打开。

## 📖 使用说明

### Web 界面操作

1. **左栏** — 浏览 Claude Code 所有项目和会话
2. **右栏** — 浏览 Antigravity 所有对话
3. **中间按钮**：
   - 📤 **导出到项目目录** — 选中 CC 会话，导出 Markdown 到项目根目录
   - ⬅ **导入到 CC** — 选中 AG 对话，将制品生成为 CC 会话
   - ♻️ **恢复到项目目录** — 选中 AG 对话，将制品文件复制到项目目录
4. **预览面板** — 点击任意会话/对话，右侧实时预览内容

### 数据路径

| 来源 | 默认路径 |
|------|----------|
| Claude Code 项目 | `~/.claude/projects/` |
| Antigravity 对话 | `~/.gemini/antigravity/conversations/` |
| Antigravity Brain | `~/.gemini/antigravity/brain/` |

## 🏗️ 项目结构

```
cc-ag/
├── cc-anti.py      # 主程序（单文件，含后端 + 嵌入式前端）
├── exports/        # 导出文件存放目录
├── README.md       # 中文说明
└── README_EN.md    # English README
```

## ⚠️ 局限性

- **Antigravity `.pb` 文件** — Protobuf 格式未公开，无法直接解析完整对话内容，只能导出 brain artifacts（Markdown/文本制品）
- **导入到 CC** — 生成的会话可通过 `/resume` 查看，但不包含原始工具调用和思考过程
- **仅限本地** — 工具读取本地文件系统，不涉及网络请求

## 📄 License

MIT
