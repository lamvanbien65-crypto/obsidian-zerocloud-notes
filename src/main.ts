// Link to Notes — 主入口
import { Notice, Plugin, normalizePath } from "obsidian";
import type { SrtSettings, TaskKind } from "./types";
import { DEFAULT_SETTINGS } from "./types";
import { PythonRunner } from "./runner";
import { getVaultRoot } from "./env";
import { TaskQueue } from "./queue";
import { SrtSettingTab } from "./settings";
import { registerCommands } from "./commands";
import { XhsModal } from "./modals";
import { registerLightbox } from "./lightbox";
import { TaskView, TASK_VIEW_TYPE, activateTaskView } from "./task-view";
import { notifyDone, notifyFailed } from "./notify";
import { ensurePythonScripts } from "./scripts-bootstrap";

let seq = 0;

export class SrtPlugin extends Plugin {
  settings: SrtSettings = DEFAULT_SETTINGS;
  runner!: PythonRunner;
  queue!: TaskQueue;
  private statusEl: HTMLElement | null = null;
  private statusTimer: number | null = null;

  async onload(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData()) as SrtSettings;
    ensurePythonScripts(this.app, this.manifest.id, this.manifest.version);   // 社区单文件分发：自举 python 脚本
    this.runner = new PythonRunner(this.app, this.settings, this.manifest.id);
    this.queue = new TaskQueue(this.runner, () => this.settings.maxParallel);

    this.registerView(TASK_VIEW_TYPE, (leaf) => new TaskView(leaf, this));

    registerCommands(this);
    registerLightbox(this.app);
    this.addSettingTab(new SrtSettingTab(this.app, this));

    this.addRibbonIcon("clipboard-copy", "剪藏", () => new XhsModal(this.app, this).open());
    this.setupStatusBar();
    this.subscribeQueue();
  }

  onunload(): void {
    this.queue.cancelAll(); // 杀残留子进程
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  // ---------- 任务入队 ----------

  enqueueClipAny(url: string): void {
    const s = this.settings;
    const label = url.match(/[a-z0-9-]+\.[a-z]{2,6}\/\S+|BV[0-9A-Za-z]{10}/)?.[0] ?? url;
    const base = getVaultRoot(this.app);
    const absDir = (p: string): string | undefined =>
      p ? normalizePath(`${base}/${p}`) : undefined;
    const noteDir = absDir(s.noteDir) || normalizePath(`${base}/Link to Notes/笔记`);
    const args = [url, "--out-dir", noteDir];
    if (s.minSpeech > 0) args.push("--min-speech", String(s.minSpeech));
    this.enqueue("clip-any", label, "剪藏.py", args);
  }

  enqueueClip(mode: TaskKind, file: string): void {
    switch (mode) {
      case "transcribe":
        this.enqueue("transcribe", file, "视频转录.py", [file]);
        break;
      case "standard":
        // 零云：--no-drop 跳过 LLM 剔除其他声音，纯本地断句
        this.enqueue("standard", file, "标准字幕剪藏.py", [file, "--no-drop", "--seg", "natural"]); // 默认自然断句+单点时间戳
        break;
      default:
        new Notice(`未支持的模式：${mode}`);
    }
  }

  private enqueue(kind: TaskKind, label: string, script: string, args: string[]): void {
    this.queue.enqueue({
      id: `${Date.now()}-${seq++}`,
      kind,
      label,
      script,
      args,
    });
    // 完成通知订阅（在 subscribeQueue 统一处理）
  }

  // ---------- 状态栏 / 通知 ----------

  private setupStatusBar(): void {
    this.statusEl = this.addStatusBarItem();
    this.statusEl.addClass("srt-statusbar");
    this.statusEl.setText("Link to Notes");
    this.statusEl.onclick = () => activateTaskView(this);
    this.updateStatusBar();
  }

  private subscribeQueue(): void {
    let lastNotifiedId: string | null = null;
    this.queue.onChange(() => {
      this.updateStatusBar();
      // 完成/失败通知（每个任务只通知一次）
      for (const t of this.queue.all) {
        if (t.id === lastNotifiedId) continue;
        if (t.status === "succeeded") {
          lastNotifiedId = t.id;
          notifyDone(this.app, t, {
            autoOpenNote: this.settings.autoOpenNote,
            systemNotify: this.settings.systemNotify,
          });
        } else if (t.status === "failed") {
          lastNotifiedId = t.id;
          notifyFailed(t);
        }
      }
    });
  }

  private updateStatusBar(): void {
    if (!this.statusEl) return;
    const running = this.queue.activeCount;
    const queued = this.queue.queuedCount;
    if (running + queued === 0) {
      this.statusEl.setText("Link to Notes");
    } else {
      this.statusEl.setText(`Link to Notes：${running} 进行中${queued ? ` · ${queued} 排队` : ""}`);
    }
  }
}

// Obsidian 加载契约：main.js 必须 default 导出 Plugin 子类
export default SrtPlugin;
