# Voice to Obsidian

将本地录音文件转写为 Obsidian 笔记的 Codex Skill。

这个 skill 的默认链路是：

1. 用户把音频文件发给 Agent，或提供本地音频路径。
2. Agent 调用本地 FunASR 完成语音识别。
3. 脚本输出结构化转写 JSON 和可读 Markdown。
4. Agent 或 finalizer 将结果整理为两篇 Obsidian 笔记：
   - `录音标题—逐字稿.md`
   - `录音标题 - 智能摘要.md`

当前版本只规定本地 FunASR 流程，不包含云端常驻服务。

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

建议在 skill 目录内创建独立虚拟环境：

```bash
cd ~/.codex/skills/voice-to-obsidian
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install torch torchaudio funasr modelscope
```

安装后检查：

```bash
.venv/bin/python scripts/check_funasr_dependencies.py
```

如果机器需要指定 CPU-only 或特定平台的 PyTorch，请以 PyTorch 官方安装命令为准，然后再安装 `funasr`、`modelscope`、`torchaudio`。

## 前置模型

默认使用 FunASR 自动下载 ModelScope 模型。首次运行会下载模型，之后复用本地缓存。

默认模型配置在 `config/defaults.json`：

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

说话人识别可关闭：

```bash
.venv/bin/python scripts/transcribe_audio_funasr.py "/path/to/audio.m4a" \
  --out-dir "/tmp/voice-to-obsidian-funasr" \
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

## 使用方式

### 1. 转写音频

```bash
.venv/bin/python scripts/transcribe_audio_funasr.py "/path/to/audio.m4a" \
  --out-dir "/tmp/voice-to-obsidian-funasr"
```

输出：

- `*.funasr.transcript.json`：结构化转写结果、说话人、时间戳、耗时。
- `*.funasr.transcript.md`：中间可读逐字稿。

### 2. 写入 Obsidian

```bash
.venv/bin/python scripts/finalize_to_obsidian.py \
  "/tmp/voice-to-obsidian-funasr/audio.funasr.transcript.json" \
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

如果希望点击逐字稿时间戳后跳转到上方音频条播放，需要安装配套 Obsidian 插件。

插件约定：

- 识别独立段落中的 `Speaker N MM:SS`。
- 点击时间戳按钮后，控制当前笔记内嵌入的同一个音频播放器。
- 不应该为每个时间戳创建新的独立播放器。

没有插件时，笔记仍然可用，只是时间戳不能自动跳转播放。

## 安全和开源分发规则

- 不要提交 `.venv/`。
- 不要提交模型缓存。
- 不要提交真实 Obsidian vault 路径。
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
python3 -m py_compile scripts/transcribe_audio_funasr.py
python3 -m py_compile scripts/finalize_to_obsidian.py
```

端到端验收：

1. 一段短音频可以生成 `*.funasr.transcript.json`。
2. `finalize_to_obsidian.py` 可以写入两篇 Markdown。
3. Obsidian 中只生成一个 MP3 音频附件。
4. frontmatter 不含模型名、provider、backend 字段。
5. 笔记中不含密钥、本地私钥路径或未确认个人结论。
