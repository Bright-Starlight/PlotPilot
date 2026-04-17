"""章节正文清洗工具测试。"""
from application.engine.services.chapter_output_sanitizer import sanitize_chapter_output


def test_sanitize_chapter_output_removes_thinking_preamble():
    raw = (
        "沈惊鸿的目光骤然收紧。\n\n"
        "让我分析一下当前的情况：\n\n"
        "1. 当前字数：2398 字\n\n"
        "2. 目标字数：3000 字\n\n"
        "3. 需要补写：约 602 字\n\n"
        "用户要求我续写章节，目标是3000字，当前字数2398字，需要补写约602字。"
    )

    assert sanitize_chapter_output(raw) == "沈惊鸿的目光骤然收紧。"


def test_sanitize_chapter_output_keeps_normal_prose():
    raw = "沈惊鸿推开门，屋内的烛火轻轻跳动。\n\n他没有再犹豫，直接走了进去。"

    assert sanitize_chapter_output(raw) == raw
