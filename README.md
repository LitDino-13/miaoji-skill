# 妙计.Skill

模仿飞书妙记，做了一个给 Obsidian 用的「妙计」。

它不是会议软件，也不是云端转写服务，而是一个本地 Agent Skill：你把录音发给 Agent，Agent 调用本地 FunASR 转写，再把内容整理成 Obsidian 里的逐字稿和智能摘要。

适合这些场景：

- 面试录音复盘
- 会议录音整理
- 手机录音沉淀到知识库
- 把一段长音频变成可检索、可回听、可行动的 Markdown 笔记

## 安装

这是一个 Agent Skill，不只限于 Codex。只要你的 Agent 支持 `SKILL.md` 格式，就可以安装。

最简单的安装方式：把下面这段话直接复制给你的 Agent，让它根据自己的运行环境安装。

```text
请帮我安装这个 Agent Skill：

GitHub 仓库：https://github.com/LitDino-13/miaoji-skill
Skill 位置：仓库根目录，也就是包含 SKILL.md 的目录
安装名称：妙计.Skill

请按你当前 Agent 支持的方式安装：
1. 如果你有原生的 skill installer，请用 GitHub 仓库安装，并指定 path 为仓库根目录。
2. 如果没有原生安装器，请把这个仓库 clone 或下载到当前 Agent 的 skills 目录，目录名设为「妙计.Skill」。
3. 安装后请确认「妙计.Skill/SKILL.md」存在。

安装完成后，请提醒我重启或刷新当前 Agent，让新 skill 生效。
```

如果你使用的是 Codex，也可以自己在终端运行：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo LitDino-13/miaoji-skill \
  --path . \
  --name "妙计.Skill"
```

其他 Agent 的常见安装思路：

- 通用 Agent Skills 目录：安装到 `~/.agents/skills/妙计.Skill`。
- Codex：安装到 `~/.codex/skills/妙计.Skill`。
- Claude Code：安装到 `~/.claude/skills/妙计.Skill`。
- 其他 Agent：查看该 Agent 的 skills / capabilities / extensions 文档，把整个仓库根目录作为一个 skill 安装。

安装后重启或刷新你的 Agent，使新 skill 生效。

安装后可以这样调用：

```text
Use $妙计.Skill to transcribe this audio into my Obsidian vault.
```

## 它会做什么

妙计.Skill 的默认链路是：

1. 用户把音频文件发给 Agent，或提供本地音频路径。
2. Agent 调用本地 FunASR 完成语音识别。
3. 脚本输出结构化转写 JSON 和可读 Markdown。
4. Agent 或 finalizer 将结果整理为两篇 Obsidian 笔记：
   - `录音标题—逐字稿.md`
   - `录音标题 - 智能摘要.md`

当前版本只规定本地 FunASR 流程，不包含云端常驻服务。

模型权重不直接提交到 Git 仓库。默认模型总量约 2GB，直接提交会让仓库难以 clone 和维护，也可能触发 GitHub 单文件限制。仓库提供 `config/models.json` 和 `scripts/download_models.py`，用于在安装后下载安装到本地。

## 前置依赖

### 系统依赖

必须安装：

```bash
ffmpeg -version
ffprobe -version
python3 --version
```

`ffmpeg` 用于生成 Obsidian 内可播放的 MP3 文件，`ffprobe` 用于读取音频时长。

macOS 可用 Homebrew 安装：

```bash
brew install ffmpeg
```

### Python 依赖

进入你安装后的 skill 目录，也就是包含 `SKILL.md` 的目录。下面用 `SKILL_DIR` 表示这个目录：

```bash
SKILL_DIR="/path/to/installed/妙计.Skill"
cd "$SKILL_DIR"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install torch torchaudio funasr modelscope
```

常见示例：

- 通用 Agent Skills：`~/.agents/skills/妙计.Skill`
- Codex：`~/.codex/skills/妙计.Skill`
- Claude Code：`~/.claude/skills/妙计.Skill`

安装后检查：

```bash
.venv/bin/python scripts/check_funasr_dependencies.py
```

如果机器需要指定 CPU-only 或特定平台的 PyTorch，请以 PyTorch 官方安装命令为准，然后再安装 `funasr`、`modelscope`、`torchaudio`。

## 前置模型

默认使用 FunASR 自动下载 ModelScope 模型。首次运行会下载模型，之后复用本地缓存。

也可以在第一次转写前显式下载模型：

```bash
.venv/bin/python scripts/download_models.py
```

如果希望把模型下载到当前仓库的 `models/` 目录，便于后续离线使用：

```bash
.venv/bin/python scripts/download_models.py --models-dir ./models
```

`models/` 已被 `.gitignore` 排除，不会提交到公开仓库。

默认模型配置在 `config/defaults.json`，精确 ModelScope 模型 ID 记录在 `config/models.json`：

```json
{
  "asr_provider": "FunASR",
  "language": "zh",
  "audio_format": "mp3",
  "funasr": {
    "asr_model": "paraformer-zh",
    "vad_model": "fsmn-vad",
    "punc_model": "ct-punc",
    "spk_model": "cam++",
    "device": "cpu",
    "batch_size_s": 300
  }
}
```

模型含义：

- `paraformer-zh`：中文 ASR 主模型。
- `fsmn-vad`：语音活动检测，用于切分有效语音片段。
- `ct-punc`：标点恢复模型。
- `cam++`：说话人识别模型，用于生成 `Speaker N`。

当前模型清单：

```text
iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
iic/speech_fsmn_vad_zh-cn-16k-common-pytorch
iic/punc_ct-transformer_cn-en-common-vocab471067-large
iic/speech_campplus_sv_zh-cn_16k-common
```

说话人识别可关闭：

```bash
.venv/bin/python scripts/transcribe_audio_funasr.py "/path/to/audio.m4a" \
  --out-dir "/tmp/miaoji-skill-funasr" \
  --disable-speaker-diarization
```

关闭后速度和内存占用通常更低，但逐字稿不会区分不同说话人。

## Obsidian 配置

必须提供 Obsidian vault 路径。推荐使用环境变量：

```bash
export OBSIDIAN_VAULT="/absolute/path/to/your/ObsidianVault"
```

默认写入位置：

```text
40 Resources/录音转写/
```

默认音频附件位置：

```text
40 Resources/附件/录音原件/
```

finalizer 会把源音频转换为一个 MP3，并写入音频附件目录。逐字稿笔记中会嵌入这个 MP3：

```markdown
![[录音标题.mp3]]
```

### 安装配套 Obsidian 插件

妙计.Skill 生成的逐字稿本身是普通 Markdown；如果希望像“飞书妙记”一样点击时间戳并跳转播放，需要额外安装仓库内置的 Obsidian 插件：

```text
obsidian-plugin/audio-transcript-jumper/
```

这个插件会识别逐字稿中的独立时间戳行：

```markdown
Speaker 0 00:00
```

安装到你的 vault：

```bash
SKILL_DIR="/path/to/installed/妙计.Skill"
OBSIDIAN_VAULT="/absolute/path/to/your/ObsidianVault"

cd "$SKILL_DIR"
python3 scripts/install_obsidian_plugin.py --vault "$OBSIDIAN_VAULT"
```

如果已安装过旧版本，需要替换：

```bash
python3 scripts/install_obsidian_plugin.py --vault "$OBSIDIAN_VAULT" --overwrite
```

安装后在 Obsidian 中打开：

```text
Settings -> Community plugins -> Installed plugins -> Audio Transcript Jumper
```

然后启用插件。启用后：

- 逐字稿中的 `Speaker N MM:SS` 会渲染成蓝色时间戳按钮。
- 点击时间戳会让当前笔记顶部的同一个音频条跳转到对应时间点并继续播放。
- 切换到其他笔记或其他文件时，当前播放会自动暂停。
- `Speaker 0` 到 `Speaker 5` 会自动分配不同颜色；超过 6 个说话人时颜色循环复用。

如果不安装这个插件，妙计.Skill 仍然可以正常生成逐字稿和智能摘要，只是时间戳不会自动控制音频播放。

## 使用方式

### 1. 转写音频

```bash
.venv/bin/python scripts/transcribe_audio_funasr.py "/path/to/audio.m4a" \
  --out-dir "/tmp/miaoji-skill-funasr"
```

输出：

- `*.funasr.transcript.json`：结构化转写结果、说话人、时间戳、耗时。
- `*.funasr.transcript.md`：中间可读逐字稿。

### 2. 写入 Obsidian

```bash
.venv/bin/python scripts/finalize_to_obsidian.py \
  "/tmp/miaoji-skill-funasr/audio.funasr.transcript.json" \
  --source-audio "/path/to/audio.m4a" \
  --vault "$OBSIDIAN_VAULT" \
  --title "录音标题" \
  --category "会议" \
  --tag "录音转写"
```

默认不会覆盖已存在笔记。需要覆盖时显式加：

```bash
--overwrite
```

## 输出文档规范

### 逐字稿

文件名：

```text
录音标题—逐字稿.md
```

核心结构：

```markdown
---
type: interview-transcript
title: "录音标题—逐字稿"
category: "会议"
source_type: audio
audio: "40 Resources/附件/录音原件/录音标题.mp3"
duration: "36:25"
created: "2026-06-06"
review_status: "已整理"
participants:
  - Speaker 0
  - Speaker 1
tags:
  - 录音转写
---

# 录音标题—逐字稿

![[录音标题.mp3]]

## 智能纪要

## 说话人说明

## 整理说明

## 文字记录
```

时间戳行必须保持：

```markdown
Speaker 0 00:00

发言内容。
```

不要在每个时间戳后重复 `候选人`、`面试官` 等推断身份。身份说明只放在 `## 说话人说明`。

### 多说话人规则

- 保留所有 FunASR 返回的说话人编号。
- 统一写作 `Speaker 0`、`Speaker 1`、`Speaker 2`。
- 不把 `Speaker N` 自动替换成真实姓名，除非用户明确提供。
- 如果最多 6 人发言，Obsidian 插件可为 `Speaker 0` 到 `Speaker 5` 分配不同颜色。
- 超过 6 人时继续保留原始 `Speaker N`，颜色可以循环复用。

### 智能摘要

文件名：

```text
录音标题 - 智能摘要.md
```

核心结构：

- `## 总结`
- `## 后续计划`
- `## 待办`
- `## 智能章节`
- `## 关键决策`
- `## 金句时刻`
- `## 风险与待确认`
- `## 相关链接`

待办必须使用 Obsidian 原生任务格式：

```markdown
- [ ] 负责人：事项；截止时间：未明确。
```

不要用 Markdown 表格表达待办。

## 可选 Obsidian 插件

如果希望点击逐字稿时间戳后跳转到上方音频条播放，需要安装配套 Obsidian 插件。插件已经随仓库提供：

```text
obsidian-plugin/audio-transcript-jumper/
scripts/install_obsidian_plugin.py
```

插件约定：

- 识别独立段落中的 `Speaker N MM:SS`。
- 点击时间戳按钮后，控制当前笔记内嵌入的同一个音频播放器。
- 不应该为每个时间戳创建新的独立播放器。
- 当鼠标没有移动到顶部播放器区域时，播放器保持透明；鼠标悬停时显示。
- 切换到其他文档时，当前音频自动暂停。

没有插件时，笔记仍然可用，只是时间戳不能自动跳转播放。

## 安全和开源分发规则

- 不要提交 `.venv/`。
- 不要提交模型缓存。
- 不要提交真实 Obsidian vault 路径。
- 不要提交用户本地 `.obsidian/plugins/` 目录；只提交本仓库内 `obsidian-plugin/audio-transcript-jumper/` 的分发文件。
- 不要提交 API key、SSH key、`.env`、`.pem`。
- 不要把个人面试录音、逐字稿、摘要或生成结果放入公开仓库。
- 如果需要防止生成笔记中出现已知秘密，可设置：

```bash
export AUDIO_TO_OBSIDIAN_SECRET_PATTERNS="secret1,secret2"
```

## 验收清单

发布或修改 skill 前至少检查：

```bash
python3 -m py_compile scripts/check_funasr_dependencies.py
python3 -m py_compile scripts/download_models.py
python3 -m py_compile scripts/transcribe_audio_funasr.py
python3 -m py_compile scripts/finalize_to_obsidian.py
python3 -m py_compile scripts/install_obsidian_plugin.py
```

端到端验收：

1. `scripts/download_models.py` 可以下载或确认所需模型。
2. 一段短音频可以生成 `*.funasr.transcript.json`。
3. `finalize_to_obsidian.py` 可以写入两篇 Markdown。
4. Obsidian 中只生成一个 MP3 音频附件。
5. frontmatter 不含模型名、provider、backend 字段。
6. 笔记中不含密钥、本地私钥路径或未确认个人结论。
7. 配套 Obsidian 插件可以复制到测试 vault，并包含 `manifest.json`、`main.js`、`styles.css`。
