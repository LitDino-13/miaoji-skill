const fs = require("fs");
const path = require("path");
const { Plugin, TFile } = require("obsidian");

const DEBUG = false;
const AUDIO_EMBED_RE = /!\[\[([^#|\]]+?\.(?:mp3|webm|wav|m4a|ogg|3gp|flac))(?:#[^\]]*)?(?:\|[^\]]*)?\]\]/i;
const SPEAKER_LINE_RE = /^(Speaker\s+\d+)\s+(\d{1,3}):(\d{2})(?::(\d{2}))?\s*$/;

module.exports = class AudioTranscriptJumperPlugin extends Plugin {
  async onload() {
    this.activeButton = null;
    this.activeAudio = null;
    this.activeSourcePath = null;
    this.activeLeafContent = null;
    this.audioByResourcePath = new Map();
    this.debugLogPath = this.getDebugLogPath();
    this.logDebug("plugin:onload", {
      version: this.manifest && this.manifest.version,
      debugLogPath: this.debugLogPath
    });
    this.registerEvent(
      this.app.workspace.on("active-leaf-change", () => {
        window.setTimeout(() => this.pauseIfAudioLeftActiveLeaf("active-leaf-change"), 0);
      })
    );
    this.registerEvent(
      this.app.workspace.on("file-open", (file) => {
        this.pauseIfDifferentFileOpened(file);
      })
    );
    this.registerMarkdownPostProcessor(async (container, context) => {
      const source = await this.readSource(context.sourcePath);
      if (!source || !AUDIO_EMBED_RE.test(source)) {
        this.logDebug("postprocessor:skip", {
          sourcePath: context.sourcePath,
          hasSource: Boolean(source)
        });
        return;
      }
      const resourcePath = this.getEmbeddedResourcePath(source, context.sourcePath);
      if (resourcePath) {
        this.ensureStablePlayer(container, resourcePath);
        this.cacheRenderedAudios(container, resourcePath);
      }
      const processedCount = this.processSpeakerLines(container, context.sourcePath, resourcePath);
      this.logDebug("postprocessor:processed", {
        sourcePath: context.sourcePath,
        resourcePath,
        processedCount
      });
    });
  }

  async readSource(sourcePath) {
    const file = this.app.vault.getAbstractFileByPath(sourcePath);
    if (!(file instanceof TFile)) return "";
    return await this.app.vault.cachedRead(file);
  }

  processSpeakerLines(container, sourcePath, resourcePath) {
    let processedCount = 0;
    for (const paragraph of Array.from(container.querySelectorAll("p"))) {
      if (paragraph.dataset.atjProcessed === "true") continue;
      const text = (paragraph.textContent || "").trim();
      const match = text.match(SPEAKER_LINE_RE);
      if (!match) continue;

      const speaker = match[1];
      const seconds = this.toSeconds(match[2], match[3], match[4]);
      const label = match[4] ? `${match[2]}:${match[3]}:${match[4]}` : `${match[2]}:${match[3]}`;

      paragraph.empty();
      const wrapper = paragraph.createSpan({ cls: "atj-line" });
      const speakerIndex = Number(speaker.match(/^Speaker\s+(\d+)$/)[1]);
      const speakerColorIndex = speakerIndex % 6;
      wrapper.createSpan({
        cls: `atj-speaker atj-speaker-id-${speakerIndex} atj-speaker-color-${speakerColorIndex}`,
        text: speaker
      });
      const button = wrapper.createEl("button", {
        cls: "atj-time",
        text: label,
        attr: {
          "data-atj-seconds": String(seconds),
          "aria-label": `Seek audio to ${label}`
        }
      });
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        try {
          this.logDebug("click", {
            sourcePath,
            resourcePath,
            speaker,
            label,
            seconds
          });
          await this.playFrom(sourcePath, resourcePath, seconds, button);
        } catch (error) {
          console.error("Audio Transcript Jumper failed to play timestamp", error);
          this.logDebug("click:error", { message: this.errorMessage(error) });
        }
      });
      paragraph.dataset.atjProcessed = "true";
      processedCount += 1;
    }
    return processedCount;
  }

  toSeconds(minOrHour, secOrMin, maybeSec) {
    const a = Number(minOrHour);
    const b = Number(secOrMin);
    if (maybeSec === undefined) return a * 60 + b;
    return a * 3600 + b * 60 + Number(maybeSec);
  }

  async playFrom(sourcePath, resourcePath, seconds, button) {
    const audio = await this.findEmbeddedAudio(button, sourcePath, resourcePath);
    if (!audio) {
      this.logDebug("playFrom:no-audio", { sourcePath, resourcePath, seconds });
      return;
    }

    if (this.activeButton && this.activeButton !== button) {
      this.activeButton.removeClass("is-playing");
    }

    this.logDebug("playFrom:audio-selected", {
      seconds,
      audio: this.audioSnapshot(audio)
    });
    this.showStablePlayer(audio);
    const didPlay = await this.seekAndPlay(audio, seconds);
    if (!didPlay) {
      this.logDebug("playFrom:not-played", { seconds, audio: this.audioSnapshot(audio) });
      return;
    }

    button.addClass("is-playing");
    this.activeButton = button;
    this.activeAudio = audio;
    this.activeSourcePath = sourcePath;
    this.activeLeafContent = button.closest(".workspace-leaf-content") || audio.closest(".workspace-leaf-content");
    this.bindAudioState(audio);
    this.logDebug("playFrom:playing", { seconds, audio: this.audioSnapshot(audio) });
  }

  async seekAndPlay(audio, seconds) {
    await this.waitForMetadata(audio);
    const target = Math.max(0, seconds);
    this.logDebug("seekAndPlay:before-seek", {
      target,
      audio: this.audioSnapshot(audio)
    });
    audio.currentTime = target;
    await this.waitForSeek(audio);
    this.logDebug("seekAndPlay:after-seek", {
      target,
      audio: this.audioSnapshot(audio)
    });
    try {
      await audio.play();
      this.logDebug("seekAndPlay:play-success", {
        target,
        audio: this.audioSnapshot(audio)
      });
      return true;
    } catch (error) {
      console.error("Audio Transcript Jumper could not start audio playback", error);
      this.logDebug("seekAndPlay:play-error", {
        target,
        message: this.errorMessage(error),
        audio: this.audioSnapshot(audio)
      });
      return false;
    }
  }

  waitForMetadata(audio) {
    if (audio.readyState >= 1) {
      this.logDebug("metadata:already-ready", { audio: this.audioSnapshot(audio) });
      return Promise.resolve();
    }
    this.logDebug("metadata:load", { audio: this.audioSnapshot(audio) });
    audio.load();
    return new Promise((resolve) => {
      const finish = () => {
        clearTimeout(timeout);
        audio.removeEventListener("loadedmetadata", finish);
        this.logDebug("metadata:finish", { audio: this.audioSnapshot(audio) });
        resolve();
      };
      const timeout = setTimeout(finish, 1200);
      audio.addEventListener("loadedmetadata", finish, { once: true });
    });
  }

  waitForSeek(audio) {
    if (!audio.seeking) {
      this.logDebug("seek:not-waiting", { audio: this.audioSnapshot(audio) });
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const finish = () => {
        clearTimeout(timeout);
        audio.removeEventListener("seeked", finish);
        audio.removeEventListener("canplay", finish);
        this.logDebug("seek:finish", { audio: this.audioSnapshot(audio) });
        resolve();
      };
      const timeout = setTimeout(finish, 800);
      audio.addEventListener("seeked", finish, { once: true });
      audio.addEventListener("canplay", finish, { once: true });
    });
  }

  async findEmbeddedAudio(button, sourcePath, resourcePath) {
    const resolvedResourcePath = resourcePath || (await this.getEmbeddedResourcePathFromFile(sourcePath));
    if (!resolvedResourcePath) return null;

    const roots = [];
    const leafContent = button.closest(".workspace-leaf-content");
    if (leafContent) roots.push(leafContent);
    const localPreview = button.closest(".markdown-preview-view");
    if (localPreview) roots.push(localPreview);
    roots.push(this.app.workspace.containerEl);

    for (const root of roots) {
      const audio = this.findMatchingAudio(root, resolvedResourcePath);
      if (audio) {
        this.audioByResourcePath.set(resolvedResourcePath, audio);
        this.logDebug("findAudio:root-match", {
          resolvedResourcePath,
          rootClass: root.className || null,
          audio: this.audioSnapshot(audio)
        });
        return audio;
      }
    }

    const cached = this.audioByResourcePath.get(resolvedResourcePath);
    if (cached && this.isUsableAudio(cached)) {
      this.logDebug("findAudio:cache-match", {
        resolvedResourcePath,
        audio: this.audioSnapshot(cached)
      });
      return cached;
    }
    if (cached) {
      this.logDebug("findAudio:drop-stale-cache", {
        resolvedResourcePath,
        audio: this.audioSnapshot(cached)
      });
      this.audioByResourcePath.delete(resolvedResourcePath);
    }

    console.warn("Audio Transcript Jumper could not find rendered audio for", resolvedResourcePath);
    this.logDebug("findAudio:not-found", { resolvedResourcePath });
    return null;
  }

  findMatchingAudio(root, resourcePath) {
    const audioElements = Array.from(root.querySelectorAll("audio"));
    const usableAudioElements = audioElements.filter((audio) => this.isUsableAudio(audio));
    this.logDebug("findMatchingAudio:scan", {
      resourcePath,
      totalAudioCount: audioElements.length,
      usableAudioCount: usableAudioElements.length,
      audios: audioElements.map((audio) => this.audioSnapshot(audio))
    });
    return usableAudioElements.find((audio) => {
      const src = audio.getAttribute("src") || "";
      return this.sameResource(src, resourcePath) || this.sameResource(audio.currentSrc, resourcePath);
    });
  }

  isUsableAudio(audio) {
    if (!audio.isConnected) return false;
    if (audio.dataset.atjStablePlayer === "true") return true;
    return audio.getClientRects().length > 0;
  }

  sameResource(actual, expected) {
    if (!actual || !expected) return false;
    if (actual === expected) return true;
    return this.normalizeResourceUrl(actual) === this.normalizeResourceUrl(expected);
  }

  normalizeResourceUrl(value) {
    const decoded = this.safeDecodeUrl(value);
    return decoded.split("?")[0];
  }

  safeDecodeUrl(value) {
    try {
      return decodeURI(value);
    } catch {
      return value;
    }
  }

  cacheRenderedAudios(container, resourcePath) {
    this.markSourceAudios(container, resourcePath);
    const audio = this.findMatchingAudio(container, resourcePath);
    if (audio) {
      this.audioByResourcePath.set(resourcePath, audio);
      this.logDebug("cacheRenderedAudios:cached", {
        resourcePath,
        audio: this.audioSnapshot(audio)
      });
    }
  }

  ensureStablePlayer(container, resourcePath) {
    const leafContent = container.closest(".workspace-leaf-content");
    if (!leafContent) return null;
    this.removeStaleStablePlayers(leafContent, resourcePath);
    const existing = Array.from(leafContent.querySelectorAll(".atj-stable-player audio")).find((audio) => {
      const src = audio.getAttribute("src") || "";
      return this.sameResource(src, resourcePath) || this.sameResource(audio.currentSrc, resourcePath);
    });
    if (existing) {
      this.audioByResourcePath.set(resourcePath, existing);
      return existing;
    }

    const host = leafContent.querySelector(".view-content") || leafContent;
    const shell = document.createElement("div");
    shell.className = "atj-stable-player is-idle";
    shell.dataset.resourcePath = resourcePath;

    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = resourcePath;
    audio.preload = "metadata";
    audio.dataset.atjStablePlayer = "true";
    shell.appendChild(audio);

    host.prepend(shell);
    this.audioByResourcePath.set(resourcePath, audio);
    this.logDebug("stablePlayer:created", {
      resourcePath,
      audio: this.audioSnapshot(audio)
    });
    return audio;
  }

  showStablePlayer(audio) {
    const shell = audio.closest(".atj-stable-player");
    if (!shell) return;
    shell.classList.remove("is-idle");
    shell.classList.add("is-active");
  }

  removeStaleStablePlayers(leafContent, resourcePath) {
    for (const shell of Array.from(leafContent.querySelectorAll(".atj-stable-player"))) {
      const audio = shell.querySelector("audio");
      if (!audio) {
        shell.remove();
        continue;
      }
      const src = audio.getAttribute("src") || "";
      const matches = this.sameResource(src, resourcePath) || this.sameResource(audio.currentSrc, resourcePath);
      if (!matches) {
        this.logDebug("stablePlayer:remove-stale", {
          resourcePath,
          audio: this.audioSnapshot(audio)
        });
        shell.remove();
      }
    }
  }

  markSourceAudios(container, resourcePath) {
    for (const audio of Array.from(container.querySelectorAll("audio"))) {
      const src = audio.getAttribute("src") || "";
      if (this.sameResource(src, resourcePath) || this.sameResource(audio.currentSrc, resourcePath)) {
        if (audio.dataset.atjStablePlayer !== "true") {
          audio.classList.add("atj-source-audio");
        }
      }
    }
  }

  async getEmbeddedResourcePathFromFile(sourcePath) {
    const source = await this.readSource(sourcePath);
    return this.getEmbeddedResourcePath(source, sourcePath);
  }

  getEmbeddedResourcePath(source, sourcePath) {
    const embed = source.match(AUDIO_EMBED_RE);
    if (!embed) return null;
    const linked = this.app.metadataCache.getFirstLinkpathDest(embed[1].trim(), sourcePath);
    if (!linked) return null;
    return this.app.vault.getResourcePath(linked);
  }

  bindAudioState(audio) {
    if (audio.dataset.atjBound === "true") return;
    const clearActive = () => {
      if (this.activeAudio !== audio || !this.activeButton) return;
      this.logDebug("audio:clear-active", { audio: this.audioSnapshot(audio) });
      this.activeButton.removeClass("is-playing");
      this.activeButton = null;
      this.activeAudio = null;
      this.activeSourcePath = null;
      this.activeLeafContent = null;
    };
    audio.addEventListener("pause", clearActive);
    audio.addEventListener("ended", clearActive);
    audio.dataset.atjBound = "true";
  }

  pauseIfAudioLeftActiveLeaf(reason) {
    if (!this.activeAudio || this.activeAudio.paused) return;
    const activeLeafContent = this.getActiveLeafContent();
    if (activeLeafContent && activeLeafContent.contains(this.activeAudio)) return;
    this.pauseActiveAudio(reason, {
      activeSourcePath: this.activeSourcePath,
      activeLeafContainsAudio: Boolean(activeLeafContent && activeLeafContent.contains(this.activeAudio))
    });
  }

  pauseIfDifferentFileOpened(file) {
    if (!this.activeAudio || this.activeAudio.paused || !this.activeSourcePath) return;
    const openedPath = file && file.path;
    if (!openedPath || openedPath === this.activeSourcePath) return;
    this.pauseActiveAudio("file-open", {
      openedPath,
      activeSourcePath: this.activeSourcePath
    });
  }

  pauseActiveAudio(reason, details = {}) {
    const audio = this.activeAudio;
    const button = this.activeButton;
    this.logDebug("audio:auto-pause", {
      reason,
      ...details,
      audio: this.audioSnapshot(audio)
    });
    if (button) button.removeClass("is-playing");
    this.activeButton = null;
    this.activeAudio = null;
    this.activeSourcePath = null;
    this.activeLeafContent = null;
    if (audio && !audio.paused) audio.pause();
  }

  getActiveLeafContent() {
    const leaf = this.app.workspace.activeLeaf;
    const container = leaf && leaf.view && leaf.view.containerEl;
    if (!container) return null;
    return container.closest(".workspace-leaf-content") || container;
  }

  getDebugLogPath() {
    try {
      const basePath = this.app.vault.adapter.getBasePath();
      return path.join(basePath, ".obsidian", "plugins", "audio-transcript-jumper", "debug.log");
    } catch {
      return null;
    }
  }

  logDebug(event, details = {}) {
    if (!DEBUG) return;
    const payload = {
      ts: new Date().toISOString(),
      event,
      details
    };
    console.log("Audio Transcript Jumper", payload);
    if (!this.debugLogPath) return;
    try {
      fs.appendFileSync(this.debugLogPath, JSON.stringify(payload) + "\n", "utf8");
    } catch (error) {
      console.error("Audio Transcript Jumper could not write debug log", error);
    }
  }

  audioSnapshot(audio) {
    if (!audio) return null;
    return {
      src: audio.getAttribute("src") || "",
      currentSrc: audio.currentSrc || "",
      currentTime: audio.currentTime,
      duration: audio.duration,
      paused: audio.paused,
      readyState: audio.readyState,
      seeking: audio.seeking,
      networkState: audio.networkState,
      isConnected: audio.isConnected,
      stablePlayer: audio.dataset.atjStablePlayer === "true",
      rectCount: audio.getClientRects().length,
      errorCode: audio.error && audio.error.code,
      errorMessage: audio.error && audio.error.message
    };
  }

  errorMessage(error) {
    if (!error) return "";
    if (error instanceof Error) return error.message;
    return String(error);
  }
};
