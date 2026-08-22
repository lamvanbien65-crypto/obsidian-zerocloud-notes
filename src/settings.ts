// 设置页
import { App, PluginSettingTab, Setting, Notice } from "obsidian";
import { execFileSync } from "child_process";
import { existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";
import type { SrtPlugin } from "./main";

export class SrtSettingTab extends PluginSettingTab {
  constructor(app: App, private plugin: SrtPlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    new Setting(containerEl).setName("零云本地笔记（ZeroCloud Notes）").setHeading();
    containerEl.createEl("p", {
      text: "小红书图文/视频本地剪藏：图文笔记 → 结构化 Markdown；视频 → 本地下载 + 口播字幕（纯 BGM 自动跳过）。零云模式：全部处理本地完成，不调用任何云 LLM。依赖：python3、yt-dlp、ffmpeg、whisper-cli。",
    });

    // ---------- 环境 ----------
    new Setting(containerEl).setName("环境").setHeading();
    new Setting(containerEl)
      .setName("环境自检")
      .setDesc("检查 python3 / yt-dlp / ffmpeg / whisper-cli / whisper 模型 / silero-vad 是否就绪")
      .addButton((b) =>
        b.setButtonText("检测全部").onClick(() => {
          const el = containerEl.createDiv({ cls: "srt-env-check" });
          el.empty();
          const has = (cmd: string): boolean => {
            try {
              execFileSync("which", [cmd], { stdio: "pipe" });
              return true;
            } catch {
              return false;
            }
          };
          const rows: [string, boolean, string][] = [
            ["python3", has("python3"), "brew install python3"],
            ["yt-dlp", has("yt-dlp"), "brew install yt-dlp"],
            ["ffmpeg", has("ffmpeg"), "brew install ffmpeg"],
            ["whisper-cli", has("whisper-cli"), "brew install whisper-cpp"],
          ];
          const model = this.plugin.settings.whisperModel ||
            join(homedir(), ".cache", "whisper", "ggml-large-v3-turbo.bin");
          const modelOk = existsSync(model);
          rows.push(["whisper 模型（large-v3-turbo）", modelOk,
            `curl -L -C - -o "${model}" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin`]);
          let vadOk = false;
          try {
            execFileSync("python3", ["-c", "import silero_vad"], { stdio: "pipe" });
            vadOk = true;
          } catch {
            // 未安装 → 降级直接转录（提示安装）
          }
          rows.push(["silero-vad（语音检测，可选）", vadOk, "pip3 install --user --break-system-packages silero-vad onnxruntime"]);
          for (const [name, ok, fix] of rows) {
            el.createEl("div", {
              text: ok ? `✅ ${name}` : `❌ ${name}  →  ${fix}`,
              cls: ok ? "srt-env-ok" : "srt-env-missing",
            });
          }
        })
      );
    new Setting(containerEl)
      .setName("python3 路径")
      .setDesc("留空自动探测（/opt/homebrew/bin → /usr/local/bin → /usr/bin）")
      .addText((t) => {
        t.setPlaceholder("自动探测")
          .setValue(this.plugin.settings.pythonPath)
          .onChange(async (v) => {
            this.plugin.settings.pythonPath = v.trim();
            await this.plugin.saveSettings();
          });
      })
      .addButton((b) =>
        b.setButtonText("检测").onClick(async () => {
          const p = this.plugin.settings.pythonPath;
          try {
            execFileSync(p || "python3", ["--version"], { stdio: "pipe" });
            new Notice("✅ python3 可用");
          } catch {
            new Notice("❌ 未找到 python3");
          }
        })
      );
    new Setting(containerEl)
      .setName("whisper 模型路径")
      .setDesc("留空使用默认 ~/.cache/whisper/ggml-large-v3-turbo.bin")
      .addText((t) =>
        t.setPlaceholder("自动探测")
          .setValue(this.plugin.settings.whisperModel)
          .onChange(async (v) => {
            this.plugin.settings.whisperModel = v.trim();
            await this.plugin.saveSettings();
          })
      );

    // ---------- 输出 ----------
    new Setting(containerEl).setName("输出").setHeading();
    new Setting(containerEl)
      .setName("下载目录")
      .setDesc("视频/图片保存目录（vault 相对路径，默认 小红书剪藏/下载）")
      .addText((t) =>
        t.setPlaceholder("小红书剪藏/下载")
          .setValue(this.plugin.settings.downloadDir)
          .onChange(async (v) => {
            this.plugin.settings.downloadDir = v.trim();
            await this.plugin.saveSettings();
          })
      );
    new Setting(containerEl)
      .setName("笔记目录")
      .setDesc("笔记保存目录（vault 相对路径，默认 小红书剪藏/笔记）")
      .addText((t) =>
        t.setPlaceholder("小红书剪藏/笔记")
          .setValue(this.plugin.settings.noteDir)
          .onChange(async (v) => {
            this.plugin.settings.noteDir = v.trim();
            await this.plugin.saveSettings();
          })
      );

    // ---------- 剪藏 ----------
    new Setting(containerEl).setName("剪藏").setHeading();
    new Setting(containerEl)
      .setName("语音占比阈值")
      .setDesc("silero VAD 检测：语音占比低于此值判为纯 BGM，自动跳过转录（0~1，默认 0.15）")
      .addSlider((sl) =>
        sl.setLimits(0.05, 0.5, 0.05)
          .setValue(this.plugin.settings.minSpeech)
          .setDynamicTooltip()
          .onChange(async (v) => {
            this.plugin.settings.minSpeech = v;
            await this.plugin.saveSettings();
          })
      );
    new Setting(containerEl)
      .setName("完成后自动打开笔记")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.autoOpenNote).onChange(async (v) => {
          this.plugin.settings.autoOpenNote = v;
          await this.plugin.saveSettings();
        })
      );
    new Setting(containerEl)
      .setName("系统通知")
      .setDesc("任务完成/失败时发送系统通知")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.systemNotify).onChange(async (v) => {
          this.plugin.settings.systemNotify = v;
          await this.plugin.saveSettings();
        })
      );
    new Setting(containerEl)
      .setName("并发任务数")
      .addSlider((sl) =>
        sl.setLimits(1, 4, 1)
          .setValue(this.plugin.settings.maxParallel)
          .setDynamicTooltip()
          .onChange(async (v) => {
            this.plugin.settings.maxParallel = v;
            await this.plugin.saveSettings();
          })
      );
  }
}
