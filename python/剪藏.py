#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  剪藏：Link to Notes 统一编排入口
#
#  粘贴任意平台链接 → 自动识别平台 → 分派对应剪藏链路
#    · xhslink.cn / xiaohongshu.com  → 小红书（图文+视频）
#    · v.douyin.com / douyin.com     → 抖音（视频+图文）
#    · bilibili.com / b23.tv / BV号  → B站（视频）
#    · 其他 http(s)                  → 网页剪藏（v2.1，暂提示）
#
#  零云原则：全本地处理，不调用任何云 API
#
#  用法：
#    python3 剪藏.py "https://xhslink.cn/o/xxxx"
#    python3 剪藏.py "https://v.douyin.com/xxxx"
#    python3 剪藏.py "BV1xxxx"
# ============================================================
import re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, file):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def detect_platform(url):
    """URL → 平台标识"""
    if re.search(r"xhslink\.cn|xiaohongshu\.com", url):
        return "xiaohongshu"
    if re.search(r"douyin\.com", url):
        return "douyin"
    if re.search(r"bilibili\.com|b23\.tv|BV[0-9A-Za-z]{10}", url):
        return "bilibili"
    return "web"


def clip(url, out_dir=None, min_speech=0.15):
    """统一剪藏：按平台分派"""
    plat = detect_platform(url)
    print(f"▶ 识别平台：{plat}")

    if plat == "xiaohongshu":
        xhs = load("小红书剪藏", "小红书剪藏.py")
        nid, note_url = xhs.note_id_from(url)
        if not nid:
            raise RuntimeError("小红书链接解析失败")
        note = xhs.fetch_note(note_url)
        if note.get("type") == "video":
            xhs.clip_video(note, note_url, Path(out_dir) if out_dir else xhs.NOTE_DIR,
                           min_speech)
        else:
            xhs.clip_image(note, note_url, Path(out_dir) if out_dir else xhs.NOTE_DIR)
        return

    if plat == "douyin":
        dy = load("抖音剪藏", "抖音剪藏.py")
        final = dy.expand_url(url)
        if "/note/" in final:
            dy.clip_note(final, "chrome")
        else:
            dy.clip(final, "chrome", min_speech)
        return

    if plat == "bilibili":
        # b站全流程.py 的 CLI 入口（标准剪藏模式）
        bili = load("b站全流程", "b站全流程.py")
        sys.argv = ["b站全流程.py", url, "--mode", "standard"]
        if out_dir:
            sys.argv += ["--out-dir", out_dir]
        try:
            bili.main()
        except SystemExit:
            pass
        return

    raise RuntimeError(
        f"暂不支持的链接类型（{plat}）：网页剪藏将在 v2.1 提供，"
        "目前支持 B站 / 抖音 / 小红书")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="任意平台链接（B站/抖音/小红书）")
    ap.add_argument("--out-dir", help="笔记输出目录")
    ap.add_argument("--min-speech", type=float, default=0.15, help="语音占比阈值（默认 0.15）")
    args = ap.parse_args()
    try:
        clip(args.url, args.out_dir, args.min_speech)
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
