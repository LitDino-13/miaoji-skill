---
name: 妙计.Skill
description: Use when the user uploads or provides an audio recording and wants a high-quality transcript, speaker timestamps, review summary, and Obsidian source package.
---

# 妙计.Skill

Turn one uploaded audio recording into one Obsidian source package.

## Core Promise

Input: one audio attachment uploaded by the user, or a local file path exposed in the current Agent session.

Output:

1. One Raw Markdown note indexing the original audio and ASR JSON.
2. One transcript Markdown note containing metadata, embedded audio, speaker notes, and a cleaned Feishu Minutes-like transcript.
3. One review-summary Markdown note containing a polished synthesis of the transcript: situation, core conclusions, action items, chapters, decisions, quotes, risks, and links back to the transcript note.

Default destination inside the configured Obsidian vault:

```text
40 Resources/源料库/{YYYY-MMDD-topic}/
  {YYYY-MMDD-topic}—Raw.md
  {YYYY-MMDD-topic}—逐字稿.md
  {YYYY-MMDD-topic}—Summary.md
  assets/
    {YYYY-MMDD-topic}.mp3
    transcript.json
```

The vault path must be provided by `--vault` or the `OBSIDIAN_VAULT` environment variable. See `README.md` for installation, model, and Obsidian setup instructions.

## Runtime Assumptions

This is a local-execution Agent Skill. It is portable across agents that support `SKILL.md`, but the full workflow requires:

- local filesystem access, including access to the uploaded audio file path;
- permission to run shell commands;
- Python 3 and `ffmpeg` / `ffprobe`;
- an Obsidian vault path provided by `--vault` or `OBSIDIAN_VAULT`.

Before running any command, set `SKILL_DIR` to the installed skill root: the directory that contains this `SKILL.md`. Do not assume a Codex-specific, Claude-specific, or global skills path. Examples:

```bash
SKILL_DIR="/path/to/installed/妙计.Skill"
cd "$SKILL_DIR"
```

All commands below are relative to `SKILL_DIR`.

## Workflow

1. Locate the uploaded audio attachment path in the current Agent session.
2. If no actual local path is available, stop and ask the user to re-upload the file or provide a local path. Do not guess attachment paths.
3. Decide whether this run is a high-quality run or an explicit fast draft.
   - Default to a high-quality run.
   - Use a fast draft only when the user explicitly asks for speed over quality or explicitly says speaker diarization is not needed.
   - Do not silently use `--disable-speaker-diarization` for normal user requests.
4. Run the local FunASR transcription script.

```bash
cd "$SKILL_DIR"
".venv/bin/python" scripts/transcribe_audio_funasr.py \
  "/path/to/uploaded-audio" \
  --out-dir "/tmp/miaoji-skill-funasr"
```

5. For long recordings or when the single-pass output loses speaker/timestamp fidelity, rerun with `scripts/transcribe_audio_funasr_chunked.py` and speaker diarization enabled. Treat missing speaker labels in a multi-speaker recording as a quality failure, not a cosmetic issue.
6. Inspect the ASR JSON before finalizing:
   - confirm `speaker_diarization` is `true` unless the user explicitly chose a fast draft;
   - confirm `speaker_count` is greater than zero before claiming speaker separation;
   - confirm `sentence_info` or equivalent sentence-level data contains timestamps;
   - confirm the recognized duration is close to the source audio duration.
7. Finalize the ASR output into Obsidian notes with `scripts/finalize_to_obsidian.py`.
8. Treat the generated `YYYY-MMDD-主题—Summary.md` as a placeholder or draft only. It is not a completed deliverable.
9. Read the generated transcript note end to end, including the final section of long recordings, then overwrite `YYYY-MMDD-主题—Summary.md` with an Agent-written review Summary. Do not ask the user to accept the finalizer's rule-based draft as the Summary.
10. Verify both Markdown files exist, the MP3 exists, speaker timestamp lines render in the transcript, the Agent-written Summary passes the review-summary requirements below, and no API key or backend-only metadata is written into note frontmatter.

## Distribution Docs

For open-source distribution, keep these files as the public contract:

- `README.md`: user-facing setup, model, configuration, Obsidian, and safety instructions.
- `SKILL.md`: agent-facing workflow and behavior rules.
- `config/defaults.json`: portable default configuration. Do not put personal vault paths or secrets here.
- `.env.example`: example local environment variables. Users may copy it locally, but scripts only read exported environment variables.
- `config/models.json`: exact ModelScope model IDs required by the skill.
- `scripts/download_models.py`: one-command model bootstrapper.
- `scripts/install_obsidian_plugin.py`: installs the bundled Obsidian timestamp playback plugin into a vault.
- `obsidian-plugin/audio-transcript-jumper/`: bundled Obsidian plugin for clickable transcript timestamps.
- `.gitignore`: excludes `.venv`, model cache, generated transcripts, keys, and local env files.

Do not publish:

- `.venv/`
- ModelScope cache directories
- Downloaded model weight directories such as `models/`
- Real audio files
- Generated transcripts or summaries
- API keys, SSH keys, `.env`, or personal vault paths
- User vault `.obsidian/plugins/` directories; only publish the bundled plugin under `obsidian-plugin/audio-transcript-jumper/`.

## FunASR Local ASR

Use FunASR as the default ASR backend for this skill.

Before first use, check dependencies without guessing:

```bash
cd "$SKILL_DIR"
".venv/bin/python" scripts/check_funasr_dependencies.py
```

If `.venv` does not exist, create the skill-local environment first:

```bash
cd "$SKILL_DIR"
python3 -m venv .venv
".venv/bin/python" -m pip install --upgrade pip setuptools wheel
```

If dependencies are missing, report the missing packages and ask before installing. Typical packages are:

```bash
cd "$SKILL_DIR"
".venv/bin/python" -m pip install torch torchaudio funasr modelscope
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
cd "$SKILL_DIR"
".venv/bin/python" scripts/download_models.py
```

To place models under the local ignored `models/` directory:

```bash
cd "$SKILL_DIR"
".venv/bin/python" scripts/download_models.py \
  --models-dir "models"
```

The FunASR script records timing breakdowns in `*.funasr.transcript.json` under `timings`.

For high-quality runs, the transcript must preserve both speaker labels and timestamps whenever the ASR backend returns them. Use the chunked script for long recordings or for recordings where the first pass produces incomplete speaker/timestamp structure:

```bash
cd "$SKILL_DIR"
".venv/bin/python" scripts/transcribe_audio_funasr_chunked.py \
  "/path/to/uploaded-audio" \
  --out-dir "/tmp/miaoji-skill-funasr"
```

Do not call the transcript high quality until these checks pass:

- `speaker_diarization` is `true`, unless the user explicitly chose a fast draft.
- `speaker_count` is greater than zero for multi-speaker recordings.
- The ASR output contains timestamped sentence or segment entries.
- The rendered transcript contains standalone `Speaker N MM:SS` or `Speaker N HH:MM:SS` lines.
- The last transcript timestamp is close to the source audio duration.

If any check fails, state the failure clearly and rerun with a better mode before writing the final Obsidian notes. If rerun is impossible, mark the transcript as `partial` and explain the missing quality dimension in `## 整理说明`.

For faster drafts where speaker diarization is not needed, run:

```bash
cd "$SKILL_DIR"
".venv/bin/python" scripts/transcribe_audio_funasr.py \
  "/path/to/uploaded-audio" \
  --out-dir "/tmp/miaoji-skill-funasr" \
  --disable-speaker-diarization
```

When `sentence_info` contains speaker IDs, preserve every distinct speaker ID in the transcript as `Speaker N`. This applies to two-person and multi-person recordings. If no speaker IDs are returned, state that speaker diarization was not produced and render the fallback as `Speaker 0` for Obsidian plugin compatibility. Do not infer speakers as facts.

## Finalize Script

Use the finalizer after ASR succeeds:

```bash
cd "$SKILL_DIR"
".venv/bin/python" scripts/finalize_to_obsidian.py \
  "/tmp/miaoji-skill-funasr/recording.funasr.transcript.json" \
  --source-audio "/path/to/uploaded-audio.m4a" \
  --vault "$OBSIDIAN_VAULT" \
  --title "录音标题" \
  --speaker-role "0=根据内容推断，主要为候选人" \
  --speaker-role "1=根据内容推断，主要为面试官" \
  --tag "面试转写"
```

The finalizer handles:

- Creating one source package under `40 Resources/源料库/{YYYY-MMDD-topic}`.
- Converting or writing exactly one MP3 to the package `assets/` folder by default.
- Copying the ASR JSON to `assets/transcript.json`.
- Normalizing note titles to `YYYY-MMDD-主题` before writing files. The date prefix is derived from `--created`; pass `--title` as the topic portion unless the full prefixed title is already known.
- Creating `YYYY-MMDD-主题—Raw.md`.
- Creating `YYYY-MMDD-主题—逐字稿.md`.
- Creating `YYYY-MMDD-主题—Summary.md` as a placeholder or draft for the Agent to overwrite after reading the transcript.
- Merging consecutive same-speaker sentence fragments into natural speaker turns.
- Preserving all returned speakers as `Speaker N`.
- Rendering missing speaker IDs as `Speaker 0`, with an explicit note that speaker diarization was not produced.
- Writing Obsidian task items with `- [ ]`.
- Keeping human-facing frontmatter only.

Use `--overwrite` only when the user explicitly wants to replace existing notes.

## Obsidian Timestamp Plugin

The transcript notes are valid Markdown without any plugin. For clickable timestamp playback, install the bundled plugin into the target vault:

```bash
cd "$SKILL_DIR"
python3 scripts/install_obsidian_plugin.py --vault "$OBSIDIAN_VAULT"
```

If `OBSIDIAN_VAULT` is exported in the current runtime environment, `--vault` can be omitted:

```bash
python3 scripts/install_obsidian_plugin.py
```

Use `--overwrite` only when the user explicitly wants to replace an existing installed plugin:

```bash
python3 scripts/install_obsidian_plugin.py --vault "$OBSIDIAN_VAULT" --overwrite
```

After installation, the user must enable `Audio Transcript Jumper` in Obsidian Community plugins.

Do not assume the plugin is already installed just because the skill repo was installed. The repo contains the distributable plugin files under `obsidian-plugin/audio-transcript-jumper/`; `scripts/install_obsidian_plugin.py` copies those files into the user's selected vault at `.obsidian/plugins/audio-transcript-jumper/`. Obsidian still requires the user to enable the plugin manually.

Plugin behavior:

- recognizes standalone `Speaker N MM:SS` and `Speaker N HH:MM:SS` paragraphs;
- renders `Speaker N` with a rotating six-color speaker palette;
- renders timestamps as blue buttons;
- controls the same embedded audio file used by the transcript note;
- creates one stable top audio player for the current note instead of one audio element per timestamp;
- provides a close button on the top stable player to stop playback and remove the player manually;
- stops playback and removes the top stable player when the active document changes.

## Note Shape

Use `references/note-template.md` for the transcript note.

Keep the transcript note readable and source-faithful. Do not write personal reflection conclusions or unconfirmed personal judgments. The transcript note should mimic Feishu Minutes transcript documents:

- YAML metadata.
- `# {{title}}`
- A blockquoted meeting/audio info section.
- Embedded audio, using the single stored MP3 playback file, for example `![[recording.mp3]]`.
- `## 智能纪要`
- `## 说话人说明`
- `## 整理说明`
- `## 文字记录`

The source package folder and transcript Obsidian file name must start with a date prefix in `YYYY-MMDD` format, followed by a hyphen and the meeting topic or recording title:

```text
YYYY-MMDD-{{topic}}—逐字稿.md
```

The review Summary uses the same prefixed title:

```text
YYYY-MMDD-{{topic}}—Summary.md
```

Do not include ASR provider names, model names, status words, or other extra suffixes in the transcript file name unless the exact same title already exists and the user has approved a disambiguation strategy.

## Review Summary Note Shape

Use `references/summary-template.md` for the second note.

The Summary note is a review-summary document, not a keyword extract and not a verbatim transcript. The finalizer creates a placeholder or rule-based draft only. A completed Summary requires Agent intervention: the Agent must read the transcript end to end and overwrite the Summary from understanding.

Completion boundary:

- Transcript completion means the ASR output has been finalized into a timestamped Obsidian transcript note and has passed the transcript quality checks.
- Summary completion means the Agent has read the complete transcript and rewritten `YYYY-MMDD-主题—Summary.md`.
- If only the finalizer draft exists, report the Summary as unfinished or draft, even if the file exists on disk.
- Do not mark the task complete until the Agent-written Summary has replaced the placeholder draft, unless the user explicitly asks for transcript-only output.

The review Summary should answer:

- What happened in the recording?
- What is the real theme or business/project question behind the conversation?
- What conclusions, decisions, risks, and next actions are now clearer?
- Which parts should be revisited through timestamps?
- What still needs human confirmation because ASR, ownership, names, dates, or commitments are unclear?

The Summary should not embed the audio player by default. It should link to the transcript note and source audio instead.

File name:

```text
YYYY-MMDD-{{topic}}—Summary.md
```

Default title:

```markdown
# 复盘 Summary：{{title}}
```

Required sections:

- `## 总结`: structured synthesis of the whole recording. Do not summarize by listing generic keywords.
- `## 后续计划`: split into `### 近期事项` and `### 长期规划` when the transcript supports both; otherwise use a single action-oriented list.
- `## 待办`: concrete owner/action/deadline items using Obsidian native task-list syntax. Each task must start with `- [ ]`. If owner or deadline is unknown, write `未明确`, not a guess. Do not use a Markdown table for to-do items.
- `## 智能章节`: timestamped chapters in `MM:SS  章节标题` or `HH:MM:SS  章节标题` format, with a short paragraph under each chapter.
- `## 关键决策`: decision, problem, discussed options, and basis. Include `其他决策` if there are multiple smaller decisions.
- `## 金句时刻`: only include quotes that are actually present or clearly recoverable from the transcript. Do not invent motivational quotes.
- `## 相关链接`: include a wikilink to the transcript note and, when useful, the embedded audio file.

Optional sections:

- Add `## 风险与待确认` when the recording contains ambiguous commitments, unclear ownership, unclear deadlines, or ASR uncertainty that affects decisions.
- Omit `## 金句时刻` if there are no real quotes worth preserving.

Recommended extra sections for long project, meeting, course, or strategy recordings:

- `## 一句话结论`: one sentence capturing the practical value of the recording.
- `## 复盘视角：真正沉淀了什么`: interpretive synthesis of reusable lessons, project judgments, or workflow insights.
- Topic-specific sections when the transcript clearly contains multiple business, learning, or product lines.

Low-quality Summary signals that must be fixed before final response:

- It says it was generated by a rule script or asks the user to verify a generic machine draft.
- It contains broad filler such as "主要围绕 AI、产品、面试、知识库展开" without explaining the real structure.
- It selects the first few long transcript turns as "representative" without synthesis.
- It creates generic tasks such as "回听并确认关键专有名词" as the main value.
- It invents owners, deadlines, decisions, quotes, or personal reflections not supported by the transcript.
- It ignores late-recording content because only the first part of the transcript was read.

Summary note frontmatter should stay human-facing:

```yaml
---
type: audio-summary
title: 会议主题
source_type: audio
transcript: "[[YYYY-MMDD-会议主题—逐字稿]]"
raw_note: "[[YYYY-MMDD-会议主题—Raw]]"
audio: 40 Resources/源料库/YYYY-MMDD-会议主题/assets/YYYY-MMDD-会议主题.mp3
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
raw_note: "[[YYYY-MMDD-会议主题—Raw]]"
audio: 40 Resources/源料库/YYYY-MMDD-会议主题/assets/YYYY-MMDD-会议主题.mp3
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
- Confirm the final review Summary Obsidian Markdown file exists.
- Confirm no API key appears in generated files.
- For FunASR, confirm whether `speaker_count` is greater than zero before claiming speaker separation.
- Confirm the transcript includes standalone `Speaker N` timestamp lines, unless the user explicitly requested a fast draft without speaker diarization.
- Confirm the last transcript timestamp is close to the source audio duration.
- Confirm the Summary is an Agent-written review Summary, not the finalizer's placeholder or rule-based draft.
- Confirm the Summary covers the whole recording, including the final section of long recordings.
- Confirm the Summary does not contain low-quality draft phrases such as "规则脚本", "可优先复盘以下片段", or generic keyword-only summaries.
- Report both final note paths and whether the transcript status is `ready` or `partial`.
