// 全局画廊灯箱：点击轮播卡片 → 全屏查看；触控板左右滑动切换上一张/下一张
// 纯文字卡片 → 白底深字展示（与文字卡样式一致）；图片/视频 → 黑底原图
import { App, Modal } from "obsidian";

const VIDEO_EXT = [".mov", ".mp4", ".webm", ".m4v"];

type GalleryItem =
  | { kind: "image"; src: string; caption: string }
  | { kind: "video"; src: string; caption: string }
  | { kind: "text"; step: string; text: string };

/** 去掉卡片文字里的 markdown 残留标记（## ** `） */
function cleanMarkdown(s: string): string {
  return s.replace(/[#*`]/g, "").trim();
}

class GalleryModal extends Modal {
  private idx = 0;
  private mediaEl: HTMLElement | null = null;
  private countEl: HTMLElement | null = null;
  private wheelAcc = 0;

  constructor(app: App, private items: GalleryItem[], start: number) {
    super(app);
    this.idx = start;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    const modalEl = contentEl.closest(".modal") as HTMLElement | null;
    if (modalEl) {
      modalEl.style.width = "100vw";
      modalEl.style.height = "100vh";
      modalEl.style.maxWidth = "100vw";
      modalEl.style.margin = "0";
      modalEl.style.background = "rgba(0,0,0,0.95)";
      const closeBtn = modalEl.querySelector(".modal-close-button") as HTMLElement | null;
      if (closeBtn) closeBtn.style.color = "#fff";
    }
    contentEl.addClass("carousel-lightbox");
    contentEl.style.width = "100%";
    contentEl.style.height = "100%";
    contentEl.style.display = "flex";
    contentEl.style.alignItems = "center";
    contentEl.style.justifyContent = "center";
    contentEl.style.overflow = "hidden";

    this.countEl = contentEl.createEl("div");
    this.countEl.style.position = "fixed";
    this.countEl.style.bottom = "20px";
    this.countEl.style.left = "50%";
    this.countEl.style.transform = "translateX(-50%)";
    this.countEl.style.color = "#fff";
    this.countEl.style.fontSize = "14px";
    this.countEl.style.background = "rgba(0,0,0,0.5)";
    this.countEl.style.padding = "4px 12px";
    this.countEl.style.borderRadius = "12px";

    this.show();
    // 触控板双指左右滑动 → 切图（wheel deltaX 累积）
    contentEl.addEventListener("wheel", (e) => {
      e.preventDefault();
      const dx = e.deltaX || e.deltaY * 0.5;
      this.wheelAcc += dx;
      if (Math.abs(this.wheelAcc) > 60) {
        if (this.wheelAcc < 0) this.prev();
        else this.next();
        this.wheelAcc = 0;
      }
    }, { passive: false });
    // 键盘 ← → 切图
    window.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") this.prev();
      if (e.key === "ArrowRight") this.next();
    });
  }

  private setTheme(light: boolean): void {
    const modalEl = this.contentEl.closest(".modal") as HTMLElement | null;
    if (modalEl) modalEl.style.background = light ? "#ffffff" : "rgba(0,0,0,0.95)";
    const closeBtn = modalEl?.querySelector(".modal-close-button") as HTMLElement | null;
    if (closeBtn) closeBtn.style.color = light ? "#333" : "#fff";
    if (this.countEl) {
      this.countEl.style.color = light ? "#666" : "#fff";
      this.countEl.style.background = light ? "rgba(0,0,0,0.08)" : "rgba(0,0,0,0.5)";
    }
  }

  private show(): void {
    if (!this.countEl) return;
    // 旧元素淡出移除，按卡片类型动态创建
    if (this.mediaEl) this.mediaEl.remove();
    const item = this.items[this.idx];
    let el: HTMLElement;
    if (item.kind === "text") {
      // 纯文字笔记：白底深字，与文字卡样式一致
      this.setTheme(true);
      const wrap = this.contentEl.createDiv();
      wrap.style.cssText =
        "width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;" +
        "padding:8vh 10vw;box-sizing:border-box;overflow-y:auto;";
      const h = wrap.createEl("div");
      h.style.cssText = "font-size:28px;font-weight:700;color:#b45309;margin-bottom:24px;";
      h.setText(item.step);
      const p = wrap.createEl("div");
      p.style.cssText =
        "font-size:20px;line-height:1.8;color:#222222;max-width:80vw;white-space:pre-wrap;word-break:break-word;text-align:center;";
      p.setText(item.text);
      el = wrap;
    } else if (item.kind === "video") {
      this.setTheme(false);
      const wrap = this.contentEl.createDiv();
      wrap.style.cssText = "display:flex;flex-direction:column;align-items:center;gap:14px;max-width:95vw;";
      const v = wrap.createEl("video", { attr: { src: item.src, controls: "controls" } });
      v.style.maxWidth = "95vw";
      v.style.maxHeight = "72vh";
      v.style.objectFit = "contain";
      v.style.borderRadius = "4px";
      v.play();
      const cap = wrap.createEl("div");
      cap.style.cssText = "color:#ddd;font-size:15px;line-height:1.7;text-align:center;max-width:90vw;white-space:normal;";
      cap.setText(item.caption);
      el = wrap;
    } else {
      this.setTheme(false);
      const wrap = this.contentEl.createDiv();
      wrap.style.cssText = "display:flex;flex-direction:column;align-items:center;gap:14px;max-width:95vw;";
      const img = wrap.createEl("img", { attr: { src: item.src } });
      img.style.maxWidth = "95vw";
      img.style.maxHeight = "72vh";
      img.style.objectFit = "contain";
      img.style.borderRadius = "4px";
      img.style.transition = "opacity 0.15s";
      img.style.opacity = "0";
      setTimeout(() => (img.style.opacity = "1"), 60);
      // 完整文字说明（图片下方，完整呈现）
      const cap = wrap.createEl("div");
      cap.style.cssText = "color:#ddd;font-size:15px;line-height:1.7;text-align:center;max-width:90vw;white-space:normal;";
      cap.setText(item.caption);
      el = wrap;
    }
    this.mediaEl = el;
    this.countEl.setText(`${this.idx + 1} / ${this.items.length}`);
  }

  private next(): void {
    this.idx = (this.idx + 1) % this.items.length;
    this.show();
  }

  private prev(): void {
    this.idx = (this.idx - 1 + this.items.length) % this.items.length;
    this.show();
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

/** 卡片 → 灯箱条目：图 → image（带完整文字说明）；视频 → video；纯文字 → text */
function cardToItem(card: HTMLElement): GalleryItem | null {
  const img = card.querySelector("img") as HTMLImageElement | null;
  const video = card.querySelector("video") as HTMLVideoElement | null;
  const titleEl = card.querySelector(".carousel-title") as HTMLElement | null;
  const caption = cleanMarkdown(titleEl?.textContent || "");
  if (img) {
    const src = img.getAttribute("src") || "";
    if (src) return { kind: "image", src, caption };
  }
  if (video && !img) {
    const src = video.getAttribute("src") || "";
    if (src) return { kind: "video", src, caption };
  }
  const stepEl = card.querySelector(".card-step") as HTMLElement | null;
  const textEl = card.querySelector(".carousel-text") as HTMLElement | null;
  if (textEl) {
    const step = stepEl?.textContent || "";
    let text = textEl.textContent || "";
    if (step && text.startsWith(step)) text = text.slice(step.length).trim();
    return { kind: "text", step, text };
  }
  return null;
}

export function registerLightbox(): void {
  // 捕获阶段注册：抢先于 Obsidian 原生图片查看器，防止事件在到达 document 前被拦截
  const open = (e: PointerEvent | MouseEvent): void => {
    const card = (e.target as HTMLElement).closest(".carousel-card") as HTMLElement | null;
    if (!card) return;
    if (!cardToItem(card)) return;
    e.preventDefault();
    e.stopPropagation();
    // 收集同轮播内所有卡片（图/视频/文字混合，上一张/下一张）
    const carousel = card.closest(".carousel") as HTMLElement | null;
    const items: GalleryItem[] = [];
    let start = 0;
    if (carousel) {
      carousel.querySelectorAll(".carousel-card").forEach((c) => {
        const el = c as HTMLElement;
        const item = cardToItem(el);
        if (!item) return;
        if (el === card) start = items.length;
        items.push(item);
      });
    }
    if (items.length === 0) return;
    console.log("[carousel] 灯箱打开", items.length, "项，第", start + 1, "项");
    new GalleryModal(window.app, items, start).open();
  };
  document.addEventListener("pointerdown", open, true);
  document.addEventListener("click", open, true);
  console.log("[carousel] 灯箱已注册（pointerdown 捕获阶段）");
}
