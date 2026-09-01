#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  进度上报：TS 壳协议（OBSIDIAN_JSON_PROGRESS=1 时启用）
#    · 事件行以 \x1e 开头 + JSON：{"t": "stage"|"progress"|"result"|"error", ...}
#    · 其余 stdout 行按日志处理
# ============================================================
import json
import os
import sys

SEP = "\x1e"


def _emit(obj):
    if os.environ.get("OBSIDIAN_JSON_PROGRESS") != "1":
        return
    print(SEP + json.dumps(obj, ensure_ascii=False), flush=True)


def emit(event, **payload):
    """进度/阶段事件：emit("stage", stage="transcribe", label="▶ 转写中…")"""
    _emit({"t": event, **payload})


def emit_error(code, text):
    """错误事件：emit_error("whisper-missing", "未找到 whisper-cli")"""
    _emit({"t": "error", "code": code, "text": text})


def emit_result(outputs):
    """结果事件：emit_result([{"type": "note", "path": "..."}, ...])"""
    _emit({"t": "result", "outputs": outputs})
