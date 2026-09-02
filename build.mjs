// 构建脚本：esbuild 构建 main.js + 同步 python 脚本到 vault 插件目录
//   node build.mjs              → 本地开发构建（部署到 vault 插件目录，全功能）
//   node build.mjs --release    → 社区发布构建（输出到 release/link-to-notes/，不含抖音剪藏）
import { execSync } from "child_process";
import { cpSync, existsSync, mkdirSync, rmSync } from "fs";
import { homedir } from "os";
import path from "path";

const RELEASE = process.argv.includes("--release");
const VAULT = process.env.OBSIDIAN_VAULT
  || "/Users/skylines/Desktop/SRT-ThinkTank";
const PLUGIN_DIR = path.join(VAULT, ".obsidian", "plugins", "zerocloud-notes");
const RELEASE_DIR = path.join(process.cwd(), "release", "zerocloud-notes"); // 社区版打包目录
const SRC_PYTHON = path.join(VAULT, "Function", "视频转录"); // 共享脚本事实源
const PLUGIN_PYTHON = path.join(process.cwd(), "python");     // 仓库内快照

// 同步共享脚本：从 vault 的 Function/视频转录/ 拷贝最新脚本到 python/
// CI/干净环境（无 vault）时跳过：仓库内 python/ 快照即事实源
// 注意：小红书剪藏.py 为本仓库专属脚本，不进同步列表
function syncPython() {
  if (!existsSync(SRC_PYTHON)) {
    console.log("  · vault 脚本目录不存在（CI/干净环境）：跳过同步，使用仓库内 python/ 快照");
    return;
  }
  const files = ["视频转录.py", "标准字幕剪藏.py", "llm.py"];
  for (const f of files) {
    const src = path.join(SRC_PYTHON, f);
    const dst = path.join(PLUGIN_PYTHON, f);
    if (!existsSync(src)) { console.error(`✗ 源脚本不存在：${src}`); process.exit(1); }
    if (existsSync(dst)) rmSync(dst, { force: true });   // 先移除开发期符号链接
    cpSync(src, dst);
    console.log(`  · 已同步 ${f}`);
  }
  console.log("✅ 共享脚本已与 Function/视频转录/ 同步");
}

function deploy() {
  const target = RELEASE ? RELEASE_DIR : PLUGIN_DIR;
  if (!RELEASE && !existsSync(VAULT)) {
    console.log("  · vault 不存在（CI/干净环境）：跳过部署");
    return;
  }
  mkdirSync(target, { recursive: true });
  // 清空旧产物（保留 manifest 由主构建负责）
  for (const f of ["main.js", "main.js.map", "styles.css", "manifest.json", "versions.json"]) {
    const p = path.join(target, f);
    if (existsSync(p)) rmSync(p, { force: true });
  }
  rmSync(path.join(target, "python"), { recursive: true, force: true });

  cpSync(path.join(process.cwd(), "main.js"), path.join(target, "main.js"));
  cpSync(path.join(process.cwd(), "styles.css"), path.join(target, "styles.css"));
  cpSync(path.join(process.cwd(), "manifest.json"), path.join(target, "manifest.json"));
  if (existsSync("versions.json")) cpSync("versions.json", path.join(target, "versions.json"));
  cpSync(path.join(process.cwd(), "python"), path.join(target, "python"), {
    recursive: true,
    filter: (p) => !p.includes("__pycache__") && !(RELEASE && p.includes("抖音剪藏.py")),
  });
  console.log(`✅ 已部署到 ${target}${RELEASE ? "（社区版：不含抖音剪藏）" : ""}`);
}

if (process.argv[2] === "sync-python") {
  syncPython();
} else {
  console.log("▶ 生成内嵌脚本…");
  execSync(`node scripts/embed-scripts.mjs${RELEASE ? " --release" : ""}`, { stdio: "inherit" });
  console.log("▶ esbuild 构建…");
  execSync("node esbuild.config.mjs production", { stdio: "inherit" });
  syncPython();
  deploy();
  console.log("✅ 构建+部署完成（重启 Obsidian 或使用 BRAT 热加载）");
}
