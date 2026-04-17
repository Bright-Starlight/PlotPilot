"""章节融合 API 集成测试。"""
from __future__ import annotations

import json


def _insert_chapter(db, chapter_id: str, novel_id: str, number: int, title: str = "第一章"):
    db.execute(
        """
        INSERT INTO chapters (id, novel_id, number, title, content, outline, status, tension_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (chapter_id, novel_id, number, title, "旧正文", "旧大纲", "draft", 50.0),
    )
    db.get_connection().commit()


def _insert_beat_sheet(db, chapter_id: str):
    payload = {
        "id": "bs-1",
        "chapter_id": chapter_id,
        "scenes": [
            {
                "title": "开场",
                "goal": "典当玉佩",
                "pov_character": "沈惊鸿",
                "location": "客栈",
                "tone": "紧张",
                "estimated_words": 500,
                "order_index": 0,
            },
            {
                "title": "转折",
                "goal": "前往钱府",
                "pov_character": "沈惊鸿",
                "location": "客栈",
                "tone": "深夜",
                "estimated_words": 600,
                "order_index": 1,
            },
        ],
        "created_at": "2026-04-17T00:00:00",
        "updated_at": "2026-04-17T00:00:00",
    }
    db.execute(
        "INSERT INTO beat_sheets (id, chapter_id, data) VALUES (?, ?, ?)",
        ("bs-1", chapter_id, json.dumps(payload, ensure_ascii=False)),
    )
    db.get_connection().commit()


def test_create_and_get_fusion_job(client, db, test_novel_id):
    chapter_id = "ch-12"
    _insert_chapter(db, chapter_id, test_novel_id, 12)
    _insert_beat_sheet(db, chapter_id)

    res = client.post(
        f"/api/v1/chapters/{chapter_id}/fusion-jobs",
        json={
            "plan_version": 1,
            "state_lock_version": 1,
            "beat_ids": ["b1", "b2"],
            "target_words": 1400,
            "suspense_budget": {"primary": 1, "secondary": 2},
        },
    )
    assert res.status_code == 201
    payload = res.json()
    assert payload["status"] == "queued"
    job_id = payload["fusion_job_id"]

    got = client.get(f"/api/v1/fusion-jobs/{job_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["fusion_job_id"] == job_id
    assert body["status"] in {"completed", "warning"}
    assert body["fusion_draft"]["text"]
    assert body["preview"]["expected_suspense_count"] >= 1


def test_create_fusion_job_blocks_without_beats(client, db, test_novel_id):
    chapter_id = "ch-13"
    _insert_chapter(db, chapter_id, test_novel_id, 13)

    res = client.post(
        f"/api/v1/chapters/{chapter_id}/fusion-jobs",
        json={
            "plan_version": 1,
            "state_lock_version": 1,
            "beat_ids": [],
            "target_words": 1400,
            "suspense_budget": {"primary": 1, "secondary": 2},
        },
    )
    assert res.status_code == 400
    assert "BeatDrafts" in res.json()["detail"]


def test_create_fusion_job_fails_on_beat_count_mismatch(client, db, test_novel_id):
    chapter_id = "ch-14"
    _insert_chapter(db, chapter_id, test_novel_id, 14)
    _insert_beat_sheet(db, chapter_id)

    res = client.post(
        f"/api/v1/chapters/{chapter_id}/fusion-jobs",
        json={
            "plan_version": 1,
            "state_lock_version": 1,
            "beat_ids": ["b1"],
            "target_words": 1400,
            "suspense_budget": {"primary": 1, "secondary": 2},
        },
    )
    assert res.status_code == 201
    job_id = res.json()["fusion_job_id"]

    got = client.get(f"/api/v1/fusion-jobs/{job_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert "stored beat sheet" in body["error_message"]
