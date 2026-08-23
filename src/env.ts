// 子进程环境构造：敏感信息（key/cookie）只走 env，绝不进 argv
import { App, FileSystemAdapter } from "obsidian";
import { existsSync } from "fs";
import { execFileSync } from "child_process";
import type { SrtSettings } from "./types";

const BREW_DIRS = ["/opt/homebrew/bin", "/usr/local/bin"];

export function getVaultRoot(app: App): string {
  return (app.vault.adapter as FileSystemAdapter).getBasePath();
}

export function buildEnv(app: App, s: SrtSettings): Record<string, string> {
  const env: Record<string, string> = {
    ...process.env,
    OBSIDIAN_VAULT_ROOT: getVaultRoot(app),
    OBSIDIAN_JSON_PROGRESS: "1",
  };
  // PATH 注入 brew 目录（Finder 启动的 Obsidian 无 homebrew PATH）
  const pathParts = [...BREW_DIRS];
  if (s.pythonPath) {
    const dir = s.pythonPath.replace(/\/[^/]+$/, "");
    pathParts.unshift(dir);
  }
  if (process.env.PATH) pathParts.push(process.env.PATH);
  env.PATH = pathParts.join(":");

  // 零云硬保证：插件注入 LLM_PROVIDER=none，任何脚本都不会发起云 LLM 调用
  //（llm.py 的 none 分支直接返回 None；Claudian 环境不设此变量，行为不变）
  env.LLM_PROVIDER = "none";
  if (s.whisperModel) env.OBSIDIAN_WHISPER_MODEL = s.whisperModel;
  return env;
}

// 探测 python3 绝对路径（Finder 启动的 Obsidian 无 shell PATH）
export async function detectPython3(override: string): Promise<string> {
  if (override && override.trim()) return override.trim();
  const candidates = [
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
    "/usr/bin/env python3",
  ];
  // 优先文件存在性检测（execFileSync 在部分 Obsidian 环境会异常，改用 existsSync 更稳）
  for (const c of candidates) {
    if (c.includes(" ")) continue;               // /usr/bin/env python3 走命令探测
    if (existsSync(c)) return c;
  }
  // 兜底：zsh login shell 探测
  try {
    const out = execFileSync("/bin/zsh", ["-lc", "command -v python3"], {
      encoding: "utf8",
      timeout: 5000,
    });
    const p = out.trim().split("\n")[0];
    if (p) return p;
  } catch {
    // ignore
  }
  // 最后兜底：/usr/bin/env 探测（PATH 可用时）
  try {
    execFileSync("/usr/bin/env", ["python3", "--version"], { stdio: "pipe" });
    return "python3";
  } catch {
    // ignore
  }
  throw new Error("未找到 python3，请在设置页手动指定路径");
}
