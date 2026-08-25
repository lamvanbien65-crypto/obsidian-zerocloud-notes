// 命令面板注册
import type { SrtPlugin } from "./main";
import { XhsModal, FileSuggestModal } from "./modals";
import { activateTaskView } from "./task-view";

export function registerCommands(plugin: SrtPlugin): void {
  const app = plugin.app;

  plugin.addCommand({
    id: "clip-any",
    name: "剪藏任意链接",
    callback: () => new XhsModal(app, plugin).open(),
  });
  plugin.addCommand({
    id: "transcribe",
    name: "视频转录",
    callback: () => new FileSuggestModal(app, plugin, "transcribe").open(),
  });
  plugin.addCommand({
    id: "standard-clip",
    name: "标准字幕剪藏",
    callback: () => new FileSuggestModal(app, plugin, "standard").open(),
  });
  plugin.addCommand({
    id: "open-task-view",
    name: "打开任务面板",
    callback: () => activateTaskView(plugin),
  });
  plugin.addCommand({
    id: "cancel-all",
    name: "取消全部任务",
    callback: () => {
      if (window.confirm("确定取消全部任务？")) plugin.queue.cancelAll();
    },
  });
}
