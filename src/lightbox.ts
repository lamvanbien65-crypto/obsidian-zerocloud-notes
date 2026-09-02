// 全局画廊灯箱：点击轮播卡片 → 全屏查看；触控板左右滑动切换上一张/下一张
// 纯文字卡片 → 白底深字展示（与文字卡样式一致）；图片/视频 → 黑底原图
// 样式全部走 CSS 类（styles.css），满足 Obsidian 审核 no-static-styles-assignment
import { App, Modal } from "obsidian";

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

  private modalEl(): HTMLElement | null {
    return this.contentEl.closest(".modal") as HTMLElement | null;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    const modalEl = this.modalEl();
    if (modalEl) {
      modalEl.addClass("lb-modal", "lb-dark");
      const closeBtn = modalEl.querySelector(".modal-close-button") as HTMLElement | null;
      if (closeBtn) closeBtn.addClass("lb-close-btn");
    }
    contentEl.addClass("carousel-lightbox", "lb-dark");
    this.countEl = contentEl.createEl("div", { cls: "lb-count" });
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
    // 键盘 ← → 切图（组件生命周期内自动清理）
    this.registerDomEvent(window, "keydown", (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") this.prev();
      if (e.key === "ArrowRight") this.next();
    });
  }

  /** 白/黑主题切换：文字卡白底、图/视频黑底 */
  private setTheme(light: boolean): void {
    const modalEl = this.modalEl();
    const theme = light ? "lb-light" : "lb-dark";
    if (modalEl) {
      modalEl.removeClass("lb-light", "lb-dark");
      modalEl.addClass(theme);
    }
    this.contentEl.removeClass("lb-light", "lb-dark");
    this.contentEl.addClass(theme);
  }

  private show(): void {
    if (!this.countEl) return;
    if (this.mediaEl) this.mediaEl.remove();
    const item = this.items[this.idx];
    let el: HTMLElement;
    if (item.kind === "text") {
      // 纯文字笔记：白底深字，与文字卡样式一致
      this.setTheme(true);
      const wrap = this.contentEl.createDiv({ cls: "lb-wrap lb-text-wrap" });
      const h = wrap.createEl("div", { cls: "lb-text-step" });
      h.setText(item.step);
      const p = wrap.createEl("div", { cls: "lb-text-body" });
      p.setText(item.text);
      el = wrap;
    } else if (item.kind === "video") {
      this.setTheme(false);
      const wrap = this.contentEl.createDiv({ cls: "lb-wrap lb-media-wrap" });
      const v = wrap.createEl("video", { cls: "lb-media", attr: { src: item.src, controls: "controls" } });
      v.play();
      const cap = wrap.createEl("div", { cls: "lb-caption" });
      cap.setText(item.caption);
      el = wrap;
    } else {
      this.setTheme(false);
      const wrap = this.contentEl.createDiv({ cls: "lb-wrap lb-media-wrap" });
      const img = wrap.createEl("img", { cls: "lb-media lb-fade-in", attr: { src: item.src } });
      // 完整文字说明（图片下方，完整呈现）
      const cap = wrap.createEl("div", { cls: "lb-caption" });
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
    new GalleryModal(window.app, items, start).open();
  };
  document.addEventListener("pointerdown", open, true);
  document.addEventListener("click", open, true);
}
