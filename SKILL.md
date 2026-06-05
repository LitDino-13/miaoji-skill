---
name: 妙计.Skill
description: Use when the user uploads or provides an audio recording and wants it transcribed with local FunASR, summarized briefly, and saved as Markdown notes in their Obsidian vault. Handles local attachment paths, speaker labels, audio playback files, and direct vault writes for audio transcript notes.
---

# 妙计.Skill

Turn one uploaded audio recording into two Obsidian Markdown notes.

## Core Promise

Input: one audio attachment uploaded by the user, or a local file path exposed in the current Codex session.

Output:

1. One transcript Markdown note containing metadata, embedded audio, speaker notes, and a cleaned Feishu Minutes-like transcript.
2. One intelligent summary Markdown note containing a Feishu Minutes-like AI summary, action items, chapters, decisions, quotes, and links back to the transcript note.

Default destination inside the configured Obsidian vault:

`40 Resources/录音转写`

The vault path must be provided by `--vault` or the `OBSIDIAN_VAULT` environment variable. See `README.md` for installation, model, and Obsidian setup instructions.

## Workflow

1. Locate the uploaded audio attachment path in the current Codex session.
2. If no actual local path is available, stop and ask the user to re-upload the file or provide a local path. Do not guess attachment paths.
3. Run the local FunASR transcription script.

```bash
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" \
  "$HOME/.codex/skills/妙计.Skill/scripts/transcribe_audio_funasr.py" \
  "/path/to/uploaded-audio" \
  --out-dir "/tmp/miaoji-skill-funasr"
```

5. Finalize the ASR output into Obsidian notes with `scripts/finalize_to_obsidian.py`.
6. If the user expects a polished intelligent summary, read the generated transcript note and refine the summary note manually as the Agent. The script creates a complete rule-based draft; it does not replace the Agent's language understanding.
7. Verify both Markdown files exist, the MP3 exists, and no API key or backend-only metadata is written into note frontmatter.

## Distribution Docs

For open-source distribution, keep these files as the public contract:

- `README.md`: user-facing setup, model, configuration, Obsidian, and safety instructions.
- `SKILL.md`: agent-facing workflow and behavior rules.
- `config/defaults.json`: portable default configuration. Do not put personal vault paths or secrets here.
- `config/models.json`: exact ModelScope model IDs required by the skill.
- `scripts/download_models.py`: one-command model bootstrapper.
- `.gitignore`: excludes `.venv`, model cache, generated transcripts, keys, and local env files.

Do not publish:

- `.venv/`
- ModelScope cache directories
- Downloaded model weight directories such as `models/`
- Real audio files
- Generated transcripts or summaries
- API keys, SSH keys, `.env`, or personal vault paths

## FunASR Local ASR

Use FunASR as the default ASR backend for this skill.

Before first use, check dependencies without guessing:

```bash
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" \
  "$HOME/.codex/skills/妙计.Skill/scripts/check_funasr_dependencies.py"
```

If `.venv` does not exist, create the skill-local environment first:

```bash
python3 -m venv "$HOME/.codex/skills/妙计.Skill/.venv"
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
```

If dependencies are missing, report the missing packages and ask before installing. Typical packages are:

```bash
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" -m pip install torch torchaudio funasr modelscope
```

The FunASR script defaults to:

- ASR model: `paraformer-zh`
- VAD model: `fsmn-vad`
- Punctuation model: `ct-punc`
- Speaker model: `cam++`
- Device: `cpu`
- Batch size: `300` seconds

The exact ModelScope model IDs live in `config/models.json`. To pre-download models before first transcription:

```bash
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" \
  "$HOME/.codex/skills/妙计.Skill/scripts/download_models.py"
```

To place models under the local ignored `models/` directory:

```bash
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" \
  "$HOME/.codex/skills/妙计.Skill/scripts/download_models.py" \
  --models-dir "$HOME/.codex/skills/妙计.Skill/models"
```

The FunASR script records timing breakdowns in `*.funasr.transcript.json` under `timings`.

For faster drafts where speaker diarization is not needed, run:

```bash
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" \
  "$HOME/.codex/skills/妙计.Skill/scripts/transcribe_audio_funasr.py" \
  "/path/to/uploaded-audio" \
  --out-dir "/tmp/miaoji-skill-funasr" \
  --disable-speaker-diarization
```

When `sentence_info` contains speaker IDs, preserve every distinct speaker ID in the transcript as `Speaker N`. This applies to two-person and multi-person recordings. If no speaker IDs are returned, state that speaker diarization was not produced and do not infer speakers as facts.

## Finalize Script

Use the finalizer after ASR succeeds:

```bash
"$HOME/.codex/skills/妙计.Skill/.venv/bin/python" \
  "$HOME/.codex/skills/妙计.Skill/scripts/finalize_to_obsidian.py" \
  "/tmp/miaoji-skill-funasr/recording.funasr.transcript.json" \
  --source-audio "/path/to/uploaded-audio.m4a" \
  --vault "$OBSIDIAN_VAULT" \
  --title "录音标题" \
  --speaker-role "0=根据内容推断，主要为候选人" \
  --speaker-role "1=根据内容推断，主要为面试官" \
  --tag "面试转写"
```

The finalizer handles:

- Converting or writing exactly one MP3 to `40 Resources/附件/录音原件`.
- Creating `{{title}}—逐字稿.md`.
- Creating `{{title}} - 智能摘要.md`.
- Merging consecutive same-speaker sentence fragments into natural speaker turns.
- Preserving all returned speakers as `Speaker N`.
- Writing Obsidian task items with `- [ ]`.
- Keeping human-facing frontmatter only.

Use `--overwrite` only when the user explicitly wants to replace existing notes.

## Note Shape

Use `references/note-template.md` for the transcript note.

Keep the summary short. Do not write personal reflection conclusions or unconfirmed personal judgments. The final note should mimic Feishu Minutes transcript documents:

- YAML metadata.
- `# {{title}}`
- A blockquoted meeting/audio info section.
- Embedded audio, using the single stored MP3 playback file, for example `![[recording.mp3]]`.
- `## 智能纪要`
- `## 说话人说明`
- `## 整理说明`
- `## 文字记录`

The transcript Obsidian file name must be the meeting topic or recording title plus `—逐字稿`:

```text
{{title}}—逐字稿.md
```

Do not include dates, ASR provider names, model names, status words, or other extra suffixes in the transcript file name unless the exact same title already exists and the user has approved a disambiguation strategy.

## Intelligent Summary Note Shape

Use `references/summary-template.md` for the second note.

The intelligent summary note should mimic the Feishu Minutes reference document structure. It is not a verbatim transcript and should not embed the audio player by default. It should link to the transcript note and source audio instead.

File name:

```text
{{title}} - 智能摘要.md
```

Title:

```markdown
# 智能纪要：{{title}}
```

Required sections:

- `## 总结`: concise structured summary of the whole recording.
- `## 后续计划`: split into `### 近期事项` and `### 长期规划` when the transcript supports both; otherwise use a single action-oriented list.
- `## 待办`: concrete owner/action/deadline items using Obsidian native task-list syntax. Each task must start with `- [ ]`. If owner or deadline is unknown, write `未明确`, not a guess. Do not use a Markdown table for to-do items.
- `## 智能章节`: timestamped chapters in `MM:SS  章节标题` or `HH:MM:SS  章节标题` format, with a short paragraph under each chapter.
- `## 关键决策`: decision, problem, discussed options, and basis. Include `其他决策` if there are multiple smaller decisions.
- `## 金句时刻`: only include quotes that are actually present or clearly recoverable from the transcript. Do not invent motivational quotes.
- `## 相关链接`: include a wikilink to the transcript note and, when useful, the embedded audio file.

Optional sections:

- Add `## 风险与待确认` when the recording contains ambiguous commitments, unclear ownership, unclear deadlines, or ASR uncertainty that affects decisions.
- Omit `## 金句时刻` if there are no real quotes worth preserving.

Summary note frontmatter should stay human-facing:

```yaml
---
type: audio-summary
title: 会议主题
source_type: audio
transcript: "[[会议主题—逐字稿]]"
audio: 40 Resources/附件/录音原件/录音文件.mp3
duration: 49:39
created: 2026-06-05
review_status: 已整理
participants:
  - Speaker 0
  - Speaker 1
tags:
  - 智能纪要
---
```

Do not include ASR backend fields in the summary note frontmatter.

## Frontmatter

Use human-facing knowledge-note metadata. Do not put ASR backend implementation details in frontmatter.

Recommended frontmatter:

```yaml
---
type: interview-transcript
title: 会议主题
category: 面试
source_type: audio
audio: 40 Resources/附件/录音原件/录音文件.mp3
duration: 49:39
created: 2026-06-05
review_status: 已整理
participants:
  - Speaker 0
  - Speaker 1
tags:
  - 面试转写
---
```

Do not include these backend fields in frontmatter: `asr_provider`, `asr_model`, `vad_model`, `punc_model`, `speaker_model`, `speaker_count`, `status`, or `source_file`. If needed, summarize technical processing in `## 整理说明` instead.

For `## 文字记录`, use this turn format:

```markdown
Speaker 0 00:00

连续发言内容合并为一个自然段。

Speaker 1 00:35

连续发言内容合并为一个自然段。
```

Speaker identity labels such as `面试官` or `候选人` belong only in `## 说话人说明`. Do not repeat inferred identities in every timestamp line. The local `audio-transcript-jumper` Obsidian plugin recognizes `Speaker N MM:SS` speaker lines. Keep `Speaker N MM:SS` as a standalone paragraph, then put the transcript text in the next paragraph.

For recordings with more than two speakers:

- Include every detected `Speaker N` in `participants`.
- Add one bullet per detected speaker in `## 说话人说明`.
- Keep each timestamp line as `Speaker N MM:SS`; do not rename timestamp lines to person names.
- The local `audio-transcript-jumper` plugin assigns colors from a 6-color speaker palette using the speaker number. `Speaker 0` through `Speaker 5` have distinct colors. This matches the expected real-world upper bound for this workflow. If an ASR result unexpectedly returns `Speaker 6` or above, keep the original `Speaker N` label and let the plugin reuse the 6-color palette cyclically.

The vault plugin lives at:

`<your-vault>/.obsidian/plugins/audio-transcript-jumper`

It turns each standalone speaker timestamp into a clickable button in Obsidian Reading view. Clicking the button seeks the embedded local recording to that timestamp and starts playback.

## Transcript Cleaning

The ASR output is an intermediate artifact, not the final note. Before saving the Obsidian note:

- Normalize technical terms such as `RAG`, `LLM`, `API`, `ToB`, `CRM`, `AI Native`, `multi-agent`, `sub agent`, `tool`, `skill`, `MCP`, `SOP`, and `web search`.
- Fix obvious Chinese ASR errors only when the surrounding context makes the correction clear.
- Remove standalone filler turns such as only `嗯`, `对`, or `OK` when they add no meaning.
- Keep timestamps and speaker turns.
- Do not fabricate missing content. Use `[听不清]` for uncertain words or phrases.
- State in `## 整理说明` that the transcript is a cleaned reading version, not a legal-grade verbatim transcript.

## Quality Checks

Before final response:

- Confirm the transcript artifact exists.
- Confirm the final transcript Obsidian Markdown file exists.
- Confirm the final intelligent summary Obsidian Markdown file exists.
- Confirm no API key appears in generated files.
- For FunASR, confirm whether `speaker_count` is greater than zero before claiming speaker separation.
- Report both final note paths and whether the transcript status is `ready` or `partial`.
