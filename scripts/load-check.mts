// 加载契约回归测试：验证构建产物满足 Obsidian 加载器契约
// 用法：node scripts/load-check.mts [插件目录]
// 契约：require(main.js).default 必须是 Plugin 子类，onload 不得抛错
import { createRequire } from "module";
import Module from "module";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

type PluginClassLike = new (app: unknown, manifest: unknown) => { onload: () => Promise<void> | void; name?: string };

const defaultDir = "/Users/skylines/Desktop/SRT-ThinkTank/.obsidian/plugins/srt-subtitle-toolkit";
const pluginDir = process.argv[2] || defaultDir;
const mainPath = path.join(pluginDir, "main.js");
const mockObsidianMod = await import(path.join(path.dirname(fileURLToPath(import.meta.url)), "obsidian-mock.mjs")) as { default?: unknown };
const mockObsidian = mockObsidianMod.default;
const baseRequire = createRequire(mainPath);
const customRequire = (id: string): unknown => (id === "obsidian" ? mockObsidian : baseRequire(id)) as unknown;

// 控制实验：机制自检
const m0 = new Module("/tmp/ctrl.js", undefined);
new Function("exports", "require", "module", "__filename", "__dirname",
  "module.exports={__esModule:true,default:()=>42};")
  .call(m0.exports, m0.exports, (id: string) => require(id) as unknown, m0, "/tmp/ctrl.js", "/tmp");
const ctrl = m0.exports as { default?: () => unknown };
if (!ctrl.default || ctrl.default() !== 42) { console.error("✗ 控制实验失败"); process.exit(1); }

const src = fs.readFileSync(mainPath, "utf8");
const m = new Module(mainPath, undefined);
new Function("exports", "require", "module", "__filename", "__dirname", src)
  .call(m.exports, m.exports, customRequire, m, mainPath, pluginDir);

const mod = m.exports as { default?: unknown };
if (!mod || typeof mod.default !== "function") {
  console.error(`✗ 契约失败：main.js 缺少 default 导出（实际键：${Object.keys(mod)}）——Obsidian 将无法启用插件`);
  process.exit(1);
}
const pluginCtor = mod.default as { name?: string };
console.log(`✓ 契约：exports.default = ${pluginCtor.name}`);

const app = {
  vault: { adapter: { getBasePath: () => pluginDir.replace(/\/\.obsidian\/plugins\/.*$/, ""), getFiles: () => [] } },
  workspace: {
    getLeavesOfType: () => [], getRightLeaf: () => ({ setViewState() {}, getIcon() {} }),
    revealLeaf() {}, openLinkText() {},
  },
};
// Node 环境缺 DOM 全局：插件 onload 会注册 document 事件与 window 定时器，注入最小桩
(globalThis as { document?: unknown }).document = {
  addEventListener() {}, removeEventListener() {},
};
(globalThis as { window?: unknown }).window = globalThis;
const plugin = new (mod.default as PluginClassLike)(app, { id: "srt-subtitle-toolkit", version: "0.1.0", minAppVersion: "1.5.0", name: "SRT 字幕工具箱" });
await plugin.onload();
console.log("✓ onload 执行完成，插件类实例化成功");
