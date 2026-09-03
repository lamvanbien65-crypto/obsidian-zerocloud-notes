// 共享类型定义

export type TaskId = string;
export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";
export type TaskKind =
  | "xhs-clip"
  | "clip-any"
  | "transcribe"
  | "standard";

export interface TaskSpec {
  id: TaskId;
  kind: TaskKind;
  label: string; // 笔记标题或链接
  script: string; // python/ 下的脚本名
  args: string[]; // CLI 参数（数组传参，不拼 shell）
}

export interface StageState {
  id: string;
  label: string;
  status: "pending" | "active" | "done" | "failed" | "skipped";
}

export interface ProgressEvent {
  t: "stage" | "progress" | "result" | "error" | "log";
  stage?: string;
  label?: string;
  done?: number;
  total?: number;
  outputs?: { type: "note" | "video" | "audio" | "json" | "srt" | "txt"; path: string }[];
  code?: string;
  text?: string;
  line?: string;
}

export interface TaskRuntime extends TaskSpec {
  status: TaskStatus;
  stages: StageState[];
  progress?: { done: number; total: number };
  logTail: string[];
  result?: { outputs: ProgressEvent["outputs"] };
  error?: { code: string; text: string };
  createdAt: number;
  cancelFn?: () => void; // 运行时注入
  cancelRequested?: boolean; // 取消请求标记（进程退出时归入 canceled 而非 failed）
}

export interface SrtSettings {
  pythonPath: string; // 留空 = 自动探测
  whisperModel: string; // 留空 = ~/.cache/whisper/ggml-large-v3-turbo.bin
  downloadDir: string; // 留空 = 小红书剪藏/下载（vault 相对）
  noteDir: string; // 留空 = 小红书剪藏/笔记（vault 相对）
  minSpeech: number; // 语音占比阈值（低于此判纯BGM，跳过转录）
  autoOpenNote: boolean;
  systemNotify: boolean;
  maxParallel: number;
}

export const DEFAULT_SETTINGS: SrtSettings = {
  pythonPath: "",
  whisperModel: "",
  downloadDir: "Link to Notes/下载",
  noteDir: "Link to Notes/笔记",
  minSpeech: 0.15,
  autoOpenNote: true,
  systemNotify: true,
  maxParallel: 1,
};
