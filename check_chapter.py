import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.persistence.database.connection import get_database

db = get_database()

# 查询小说信息
novel_sql = "SELECT * FROM novels WHERE id = ?"
novel = db.fetch_one(novel_sql, ('novel-1776499481673',))
if novel:
    print(f'小说标题: {novel.get("title")}')
    print(f'小说状态: {novel.get("status")}')
    print(f'总章节数: {novel.get("total_chapters")}')
    print()

# 查询第32章信息
chapter_sql = "SELECT * FROM chapters WHERE novel_id = ? AND number = ?"
chapter = db.fetch_one(chapter_sql, ('novel-1776499481673', 32))

if chapter:
    print(f'章节ID: {chapter.get("id")}')
    print(f'章节标题: {chapter.get("title")}')
    print(f'章节状态: {chapter.get("status")}')
    print()

    # 查询验证报告
    validation_sql = """
        SELECT * FROM validation_reports
        WHERE chapter_id = ?
        ORDER BY created_at DESC LIMIT 1
    """
    validation = db.fetch_one(validation_sql, (chapter.get('id'),))

    if validation:
        print('=== 验证报告 ===')
        print(f'报告ID: {validation.get("report_id")}')
        print(f'验证状态: {validation.get("status")}')
        print(f'是否通过: {"是" if validation.get("passed") else "否"}')
        print(f'阻塞问题数: {validation.get("blocking_issue_count")}')
        print(f'P0问题数: {validation.get("p0_count")}')
        print(f'P1问题数: {validation.get("p1_count")}')
        print(f'P2问题数: {validation.get("p2_count")}')
        print(f'验证时间: {validation.get("created_at")}')
        print()

        # 查询验证问题
        issues_sql = """
            SELECT * FROM validation_issues
            WHERE report_id = ?
            ORDER BY
                CASE severity
                    WHEN 'P0' THEN 1
                    WHEN 'P1' THEN 2
                    WHEN 'P2' THEN 3
                    ELSE 4
                END,
                created_at
        """
        issues = db.fetch_all(issues_sql, (validation.get('report_id'),))

        if issues:
            print(f'=== 验证问题详情 (共{len(issues)}条) ===')
            for i, issue in enumerate(issues, 1):
                blocking_mark = '[阻塞]' if issue.get('blocking') else ''
                print(f'\n{i}. [{issue.get("severity")}] {blocking_mark} {issue.get("code")}')
                print(f'   标题: {issue.get("title")}')
                print(f'   消息: {issue.get("message")}')
                if issue.get('spans_json'):
                    import json
                    spans = json.loads(issue.get('spans_json'))
                    if spans:
                        print(f'   位置: {spans}')
                print(f'   处理状态: {issue.get("handling_status")}')
        else:
            print('无验证问题')
    else:
        print('未找到验证报告')

    print()
    print('=== 章节大纲 ===')
    outline = chapter.get('outline')
    if outline:
        print(outline)
        print()
        print(f'大纲长度: {len(outline)} 字符')
        # 检查大纲是否被截断
        if outline.endswith('发现黑市'):
            print('⚠️ 警告: 大纲似乎被截断了！')
    else:
        print('无大纲')

    print()
    print('=== 章节内容长度 ===')
    content = chapter.get('content')
    print(f'内容长度: {len(content) if content else 0} 字符')
    if content:
        print()
        print('=== 章节内容前500字 ===')
        print(content[:500])
else:
    print('未找到第32章')

db.close()
