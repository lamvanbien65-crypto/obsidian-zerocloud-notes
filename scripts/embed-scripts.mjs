// 生成 src/embeddedScripts.ts：把 python/ 下脚本 base64 内嵌进 main.js
// 用法：node scripts/embed-scripts.mjs [--release]   （--release 社区版：不含抖音剪藏）
import { readdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

const RELEASE = process.argv.includes("--release");
const PY = join(process.cwd(), "python");
const OUT = join(process.cwd(), "src", "embeddedScripts.ts");

// 不进内嵌：vault 侧开发工具（如 轮播生成.py 由 vault Function/轮播生成/ 独立管理，
// 不经插件运行时调用，无需随插件分发给用户）
const EXCLUDE = ["轮播生成.py"];

const files = readdirSync(PY)
  .filter((f) => f.endsWith(".py") && !f.includes("__pycache__"))
  .filter((f) => !EXCLUDE.includes(f))
  .filter((f) => !(RELEASE && f.includes("抖音剪藏")))
  .sort();

const entries = files.map((f) => {
  const b64 = readFileSync(join(PY, f)).toString("base64");
  return `  ${JSON.stringify(f)}: ${JSON.stringify(b64)},`;
});

const ts = `// 自动生成（scripts/embed-scripts.mjs）——python 脚本 base64 内嵌，社区单文件分发必需
// 修改 python/ 后重新运行构建。${RELEASE ? "社区版：不含抖音剪藏" : "开发版：全功能"}
export const EMBEDDED_SCRIPTS: Record<string, string> = {
${entries.join("\n")}
};
`;

writeFileSync(OUT, ts);
console.log(`✅ src/embeddedScripts.ts 已生成（${files.length} 个脚本 · ${RELEASE ? "社区版" : "开发版"}）`);
