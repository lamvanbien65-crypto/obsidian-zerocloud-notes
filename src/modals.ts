// 输入 Modal：小红书链接 / 视频选择
import { App, Modal, Notice, Setting, SuggestModal } from "obsidian";
import type { TaskKind } from "./types";
import type { SrtPlugin } from "./main";

const XHS_RE = /xhslink\.cn\/\S+|xiaohongshu\.com\/(explore|discovery\/item)\/\S+/;

export class XhsModal extends Modal {
  constructor(app: App, private plugin: SrtPlugin) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.createEl("h3", { text: "小红书剪藏" });
    contentEl.createEl("p", {
      text: "零云纯本地：图文笔记 → 图文 Markdown；视频 → 本地下载 + 口播字幕（纯 BGM 自动跳过）· 不使用任何云 LLM",
      cls: "srt-modal-hint",
    });

    let url = "";
    new Setting(contentEl).setName("小红书链接 / 分享口令").addText((t) => {
      t.setPlaceholder("https://xhslink.cn/o/xxxx 或 xiaohongshu.com/explore/xxxx")
        .onChange((v) => (url = v.trim()));
      t.inputEl.addClass("srt-wide");
    });

    new Setting(contentEl).addButton((b) =>
      b.setButtonText("开始剪藏").setCta().onClick(() => {
        const m = url.match(/(https?:\/\/[^\s]+)/);
        const target = m ? m[1] : url;
        if (!XHS_RE.test(target)) {
          new Notice("请输入有效的小红书链接（xhslink.cn 短链或 xiaohongshu.com 笔记页）");
          return;
        }
        this.plugin.enqueueXhs(target);
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
