// 脚本自举：社区版 main.js 单文件分发 —— 首次加载把内嵌 python 脚本写入插件 python 目录
// 官方安装只下发 main.js/manifest.json/styles.css，python/ 必须由 main.js 自举生成
import type { App } from "obsidian";
import * as fs from "fs";
import * as path from "path";
import { EMBEDDED_SCRIPTS } from "./embeddedScripts";

export function ensurePythonScripts(app: App, pluginId: string, version: string): void {
  try {
    const adapter = app.vault.adapter as { getBasePath?: () => string };
    const root = adapter.getBasePath?.();
    if (!root) return;
    const configDir = (app.vault as { configDir?: string }).configDir ?? ".obsidian";
    const dir = path.join(root, configDir, "plugins", pluginId, "python");
    fs.mkdirSync(dir, { recursive: true });
    // 版本戳：插件升级时整体重写（脚本可能与版本联动）
    const stamp = path.join(dir, ".scripts-version");
    if (fs.existsSync(stamp) && fs.readFileSync(stamp, "utf-8") === version) {
      return;
    }
    for (const [name, b64] of Object.entries(EMBEDDED_SCRIPTS)) {
      const p = path.join(dir, name);
      fs.writeFileSync(p, Buffer.from(b64, "base64"));
    }
    fs.writeFileSync(stamp, version);
    console.log(`[${pluginId}] python 脚本自举完成（${Object.keys(EMBEDDED_SCRIPTS).length} 个，v${version}）`);
  } catch (e) {
    console.error(`[${pluginId}] python 脚本自举失败:`, e);
  }
}
