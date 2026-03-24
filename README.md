---
title: Codex 注册机
summary: 用于整理项目说明、启动前准备、项目结构以及基础运行命令的 README 排版版本。
---

用于批量注册 OpenAI 账号。

---

## 启动前准备

启动前请确保本机开启代理。

> 注意：`CN` 和 `XG` 节点不可用。

## 项目结构

```text
.
├─ README.md              # 项目说明文档
├─ openai_register.py     # 主脚本，包含邮箱获取、OAuth 流程和核心注册逻辑
├─ accounts.json          # 账号数据存储文件
└─ sub2api_import.json    # 导入配置文件
```

### 结构说明

- `README.md`：项目的使用说明、注意事项和启动方式。
- `openai_register.py`：项目主脚本，负责临时邮箱、验证流程以及主注册逻辑。
- `accounts.json`：用于保存生成后的账号信息。
- `sub2api_import.json`：用于保存或导入相关配置数据。

## Quick Start

```bash
python openai_register.py --proxy http://127.0.0.1:7890
```

觉得有帮助的话，别忘了点个 Star 支持一下。

&nbsp;