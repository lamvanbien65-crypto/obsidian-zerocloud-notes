// 输入 Modal：小红书链接 / 视频选择
import { App, Modal, Notice, Setting, SuggestModal } from "obsidian";
import type { TaskKind } from "./types";
import type { SrtPlugin } from "./main";

const CLIP_RE = /https?:\/\/[^\s]+|BV[0-9A-Za-z]{10}|b23\.tv\/\S+/;

export class XhsModal extends Modal {
  constructor(app: App, private plugin: SrtPlugin) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.createEl("h3", { text: "Link to Notes · 剪藏" });
    contentEl.createEl("p", {
      text: "粘贴任意平台链接：B站（视频）/ 抖音（视频·图文）/ 小红书（视频·图文）→ 自动识别平台并剪藏为本地笔记 · 纯本地 0 元",
      cls: "srt-modal-hint",
    });

    let url = "";
    new Setting(contentEl).setName("链接 / 分享口令（支持多行批量）").addTextArea((t) => {
      t.setPlaceholder("每行一个链接：\nB站 / 抖音 / 小红书 链接或分享口令…")
        .onChange((v) => (url = v));
      t.inputEl.addClass("srt-wide");
      t.inputEl.rows = 5;
    });

    new Setting(contentEl).addButton((b) =>
      b.setButtonText("任务面板").onClick(() => {
        this.close();
        import("./task-view").then((m) => m.activateTaskView(this.plugin));
      }));

    new Setting(contentEl).addButton((b) =>
      b.setButtonText("开始剪藏").setCta().onClick(() => {
        const lines = url.split(/\n+/).map((l) => l.trim()).filter(Boolean);
        const targets = lines.map((l) => {
          const m = l.match(/(https?:\/\/[^\s]+)/);
          return (m ? m[1] : l);
        }).filter((t) => CLIP_RE.test(t));
        if (targets.length === 0) {
          new Notice("请输入有效的链接（B站 / 抖音 / 小红书）");
          return;
        }
        targets.forEach((t) => this.plugin.enqueueClipAny(t));
        new Notice(`已加入队列：${targets.length} 条链接`);
        this.close();
      })
    );
  }

  onClose(): void {
    const { contentEl } = this;
    contentEl.empty();
  }
}

export class FileSuggestModal extends SuggestModal<string> {
  constructor(app: App, private plugin: SrtPlugin, private mode: TaskKind) {
    super(app);
    this.setPlaceholder("输入视频文件名关键字…");
    this.setInstructions([
      { command: "↑↓", purpose: "选择" },
      { command: "↵", purpose: "开始任务" },
    ]);
  }

  getSuggestions(query: string): string[] {
    const files = this.app.vault.getFiles();
    const exts = ["mp4", "mov", "mkv", "webm", "m4a", "mp3", "flac", "wav", "aac", "m4b"];
    return files
      .filter((f) => {
        const ext = f.extension.toLowerCase();
        return exts.includes(ext) && (!query || f.path.toLowerCase().includes(query.toLowerCase()));
      })
      .slice(0, 20)
      .map((f) => f.path);
  }

  renderSuggestion(item: string, el: HTMLElement): void {
    el.setText(item);
  }

  onChooseSuggestion(item: string, evt: MouseEvent | KeyboardEvent): void {
    this.plugin.enqueueClip(this.mode, item);
  }
}
