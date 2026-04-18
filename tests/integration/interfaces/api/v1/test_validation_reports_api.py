"""Validation report API integration tests."""
from __future__ import annotations

import json
from types import SimpleNamespace

from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage


def _insert_chapter(db, chapter_id: str, novel_id: str, number: int, title: str = "第一章"):
    db.execute(
        """
        INSERT INTO chapters (id, novel_id, number, title, content, outline, status, tension_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (chapter_id, novel_id, number, title, "旧正文", "旧大纲", "draft", 50.0),
    )
    db.get_connection().commit()


def _insert_beat_sheet(db, chapter_id: str, *, state_lock_version: int = 1, plan_version: int = 3):
    payload = {
        "id": "bs-validate-1",
        "chapter_id": chapter_id,
        "plan_version": plan_version,
        "state_lock_version": state_lock_version,
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
        ("bs-validate-1", chapter_id, json.dumps(payload, ensure_ascii=False)),
    )
    db.get_connection().commit()


def _insert_state_lock(db, chapter_id: str, novel_id: str, version: int = 1):
    db.execute(
        """
        INSERT INTO state_locks (
            state_lock_id, chapter_id, novel_id, current_version, latest_version, plan_version,
            time_lock_json, location_lock_json, character_lock_json, item_lock_json,
            numeric_lock_json, event_lock_json, ending_lock_json, last_change_reason, last_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "sl-1",
            chapter_id,
            novel_id,
            version,
            version,
            1,
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[{"key":"ending_target","label":"目标终态","value":"钱府","source":"test","kind":"ending_target","status":"normal","metadata":{}}]}',
            "",
            "generated",
        ),
    )
    db.execute(
        """
        INSERT INTO state_lock_versions (
            state_lock_version_id, state_lock_id, chapter_id, novel_id, version, plan_version, source,
            change_reason, changed_fields_json, inference_notes_json, critical_change_json,
            time_lock_json, location_lock_json, character_lock_json, item_lock_json,
            numeric_lock_json, event_lock_json, ending_lock_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "slv-1",
            "sl-1",
            chapter_id,
            novel_id,
            version,
            1,
            "generated",
            "",
            "[]",
            "[]",
            "{}",
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[]}',
            '{"entries":[{"key":"ending_target","label":"目标终态","value":"钱府","source":"test","kind":"ending_target","status":"normal","metadata":{}}]}',
        ),
    )
    db.get_connection().commit()


def _insert_fusion_draft(db, chapter_id: str):
    db.execute(
        """
        INSERT INTO fusion_jobs (
            fusion_job_id, chapter_id, novel_id, plan_version, state_lock_version,
            beat_ids_json, target_words, suspense_budget_json, status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "job-validate-1",
            chapter_id,
            "test-novel-1",
            3,
            1,
            '["b1","b2"]',
            1800,
            "{}",
            "completed",
            "",
        ),
    )
    db.execute(
        """
        INSERT INTO chapter_fusion_drafts (
            fusion_id, fusion_job_id, chapter_id, source_beat_ids_json, plan_version, state_lock_version,
            text, repeat_ratio, facts_confirmed_json, open_questions_json, end_state_json,
            warnings_json, state_lock_violations_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "fusion-validate-1",
            "job-validate-1",
            chapter_id,
            '["b1","b2"]',
            3,
            1,
            "沈惊鸿闯入禁地，偏偏把沈惊鸿写进了正文。银两50两。银两3两。结尾却停在客栈。",
            0.2,
            "[]",
            "[]",
            json.dumps({"location": "客栈"}, ensure_ascii=False),
            "[]",
            "[]",
            "warning",
        ),
    )
    db.get_connection().commit()


def test_start_validation_and_get_report(client, db, test_novel_id):
    chapter_id = "ch-validate-1"
    _insert_chapter(db, chapter_id, test_novel_id, 16)
    _insert_beat_sheet(db, chapter_id)
    _insert_state_lock(db, chapter_id, test_novel_id)
    _insert_fusion_draft(db, chapter_id)

    db.execute(
        """
        UPDATE state_lock_versions
        SET character_lock_json = ?, numeric_lock_json = ?, ending_lock_json = ?
        WHERE chapter_id = ? AND version = 1
        """,
        (
            json.dumps(
                {
                    "entries": [
                        {
                            "key": "forbidden_character_1",
                            "label": "禁入人物",
                            "value": "沈惊鸿",
                            "source": "test",
                            "kind": "forbidden_character",
                            "status": "normal",
                            "metadata": {},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "entries": [
                        {
                            "key": "numeric_1",
                            "label": "银两",
                            "value": "50两",
                            "source": "test",
                            "kind": "numeric_constraint",
                            "status": "normal",
                            "metadata": {},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "entries": [
                        {
                            "key": "ending_target",
                            "label": "目标终态",
                            "value": "钱府",
                            "source": "test",
                            "kind": "ending_target",
                            "status": "normal",
                            "metadata": {},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            chapter_id,
        ),
    )
    db.execute(
        """
        UPDATE state_locks
        SET character_lock_json = ?, numeric_lock_json = ?, ending_lock_json = ?
        WHERE chapter_id = ?
        """,
        (
            json.dumps({"entries": [{"key": "forbidden_character_1", "label": "禁入人物", "value": "沈惊鸿", "source": "test", "kind": "forbidden_character", "status": "normal", "metadata": {}}]}, ensure_ascii=False),
            json.dumps({"entries": [{"key": "numeric_1", "label": "银两", "value": "50两", "source": "test", "kind": "numeric_constraint", "status": "normal", "metadata": {}}]}, ensure_ascii=False),
            json.dumps({"entries": [{"key": "ending_target", "label": "目标终态", "value": "钱府", "source": "test", "kind": "ending_target", "status": "normal", "metadata": {}}]}, ensure_ascii=False),
            chapter_id,
        ),
    )
    db.get_connection().commit()

    res = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "fusion",
            "draft_id": "fusion-validate-1",
            "plan_version": 3,
            "state_lock_version": 1,
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["passed"] is False
    assert body["p0_count"] >= 2
    assert body["state_lock_version"] == 1

    detail = client.get(f"/api/v1/validation-reports/{body['report_id']}")
    assert detail.status_code == 200
    report = detail.json()
    assert report["issues_by_severity"]["P0"]
    assert any(issue["metadata"].get("group") == "character_lock" for issue in report["issues_by_severity"]["P0"])


def test_validation_issue_filter_blocks_p0_ignore(client, db, test_novel_id):
    chapter_id = "ch-validate-2"
    _insert_chapter(db, chapter_id, test_novel_id, 17)
    _insert_beat_sheet(db, chapter_id)
    _insert_state_lock(db, chapter_id, test_novel_id)
    _insert_fusion_draft(db, chapter_id)

    client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "fusion",
            "draft_id": "fusion-validate-1",
            "plan_version": 3,
            "state_lock_version": 1,
        },
    )

    blocked = client.get("/api/v1/validation-issues", params={"chapter_id": chapter_id, "severity": "P0", "status": "ignored"})
    assert blocked.status_code == 400
    assert "cannot be ignored" in blocked.json()["detail"]


def test_validation_issue_status_update_allows_non_p0_ignore(client, db, test_novel_id):
    chapter_id = "ch-validate-ignore"
    _insert_chapter(db, chapter_id, test_novel_id, 17)
    db.execute(
        """
        INSERT INTO validation_reports (
            report_id, chapter_id, novel_id, draft_type, draft_id, plan_version, state_lock_version,
            status, passed, blocking_issue_count, p0_count, p1_count, p2_count, token_usage_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "vr-ignore-1",
            chapter_id,
            test_novel_id,
            "fusion",
            "fusion-validate-1",
            3,
            1,
            "completed",
            1,
            0,
            0,
            1,
            0,
            "{}",
        ),
    )
    db.execute(
        """
        INSERT INTO validation_issues (
            issue_id, report_id, chapter_id, severity, code, title, message,
            spans_json, blocking, suggest_patch, handling_status, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "vi-ignore-1",
            "vr-ignore-1",
            chapter_id,
            "P1",
            "identity_drift",
            "人物称谓漂移",
            "同一人物在本章里出现多个互斥身份称呼。",
            "[]",
            0,
            0,
            "unresolved",
            "{}",
        ),
    )
    db.get_connection().commit()

    updated = client.patch("/api/v1/validation-issues/vi-ignore-1", json={"status": "ignored"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "ignored"


def test_validation_issue_status_update_blocks_p0_ignore(client, db, test_novel_id):
    chapter_id = "ch-validate-ignore-p0"
    _insert_chapter(db, chapter_id, test_novel_id, 17)
    db.execute(
        """
        INSERT INTO validation_reports (
            report_id, chapter_id, novel_id, draft_type, draft_id, plan_version, state_lock_version,
            status, passed, blocking_issue_count, p0_count, p1_count, p2_count, token_usage_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "vr-ignore-p0-1",
            chapter_id,
            test_novel_id,
            "fusion",
            "fusion-validate-1",
            3,
            1,
            "completed",
            0,
            1,
            1,
            0,
            0,
            "{}",
        ),
    )
    db.execute(
        """
        INSERT INTO validation_issues (
            issue_id, report_id, chapter_id, severity, code, title, message,
            spans_json, blocking, suggest_patch, handling_status, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "vi-ignore-p0-1",
            "vr-ignore-p0-1",
            chapter_id,
            "P0",
            "ending_lock_violation",
            "违反终态锁",
            "终态不匹配。",
            "[]",
            1,
            1,
            "unresolved",
            "{}",
        ),
    )
    db.get_connection().commit()

    updated = client.patch("/api/v1/validation-issues/vi-ignore-p0-1", json={"status": "ignored"})
    assert updated.status_code == 400
    assert "cannot be ignored" in updated.json()["detail"]


def test_validation_issue_repair_patch_returns_suggestion(client, db, test_novel_id):
    chapter_id = "ch-validate-patch"
    _insert_chapter(db, chapter_id, test_novel_id, 18)
    _insert_beat_sheet(db, chapter_id)
    _insert_state_lock(db, chapter_id, test_novel_id)
    _insert_fusion_draft(db, chapter_id)

    res = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "fusion",
            "draft_id": "fusion-validate-1",
            "plan_version": 3,
            "state_lock_version": 1,
        },
    )
    report = client.get(f"/api/v1/validation-reports/{res.json()['report_id']}").json()
    patchable = next(issue for issue in report["issues_by_severity"]["P0"] if issue["suggest_patch"])

    patch = client.post(f"/api/v1/validation-issues/{patchable['issue_id']}/repair-patch")
    assert patch.status_code == 200
    assert patch.json()["issue_id"] == patchable["issue_id"]
    assert patch.json()["patch_text"]


def test_start_validation_records_identity_drift_and_token_usage(client, db, test_novel_id, monkeypatch):
    chapter_id = "ch-validate-semantic"
    _insert_chapter(db, chapter_id, test_novel_id, 22)
    _insert_beat_sheet(db, chapter_id)
    _insert_state_lock(db, chapter_id, test_novel_id)
    _insert_fusion_draft(db, chapter_id)

    db.execute(
        """
        UPDATE chapters
        SET content = ?, outline = ?
        WHERE id = ?
        """,
        (
            "沈惊鸿独自潜入钱府偏院，行动极轻。可下一段里，众人忽然都叫他陆归舟，还把他认作钱府旧客。"
            "称呼和身份在同一章里发生了明显漂移，旁白也没有解释这次伪装是否成立。",
            "潜入钱府并保持身份一致。",
            chapter_id,
        ),
    )
    db.execute(
        """
        UPDATE chapter_fusion_drafts
        SET text = ?, end_state_json = ?
        WHERE fusion_id = 'fusion-validate-1'
        """,
        (
            "沈惊鸿独自潜入钱府偏院，行动极轻。可下一段里，众人忽然都叫他陆归舟，还把他认作钱府旧客。"
            "称呼和身份在同一章里发生了明显漂移，旁白也没有解释这次伪装是否成立。",
            json.dumps({"location": "钱府"}, ensure_ascii=False),
        ),
    )
    db.get_connection().commit()

    class FakeLlm:
        async def generate(self, prompt, config):
            return GenerationResult(
                content=json.dumps(
                    {
                        "issues": [
                            {
                                "severity": "P1",
                                "code": "identity_drift",
                                "title": "人物身份漂移",
                                "message": "同一人物在本章内被称作“沈惊鸿”和“陆归舟”，但没有交代伪装成立。",
                                "needle": "陆归舟",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                token_usage=TokenUsage(input_tokens=120, output_tokens=45),
            )

    monkeypatch.setattr("interfaces.api.dependencies.get_llm_service", lambda: FakeLlm())
    monkeypatch.setattr(
        "interfaces.api.dependencies.get_bible_service",
        lambda: SimpleNamespace(
            get_bible_by_novel=lambda _novel_id: SimpleNamespace(
                characters=[SimpleNamespace(name="沈惊鸿")]
            )
        ),
    )

    res = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "fusion",
            "draft_id": "fusion-validate-1",
            "plan_version": 3,
            "state_lock_version": 1,
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["p1_count"] >= 1
    assert body["token_usage"]["input_tokens"] == 120
    assert body["token_usage"]["output_tokens"] == 45
    assert body["token_usage"]["total_tokens"] == 165

    detail = client.get(f"/api/v1/validation-reports/{body['report_id']}")
    assert detail.status_code == 200
    report = detail.json()
    assert any(issue["code"] == "identity_drift" for issue in report["issues_by_severity"]["P1"])


def test_start_validation_for_merged_draft_requires_explicit_versions(client, db, test_novel_id):
    chapter_id = "ch-validate-merged"
    _insert_chapter(db, chapter_id, test_novel_id, 18)
    _insert_state_lock(db, chapter_id, test_novel_id)

    ok = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "merged",
            "draft_id": "merged-current",
            "plan_version": 4,
            "state_lock_version": 1,
        },
    )
    assert ok.status_code == 201
    body = ok.json()
    assert body["draft_type"] == "merged"
    assert body["state_lock_version"] == 1

    reused = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "merged",
            "draft_id": "merged-current",
        },
    )
    assert reused.status_code == 201
    assert reused.json()["state_lock_version"] == 1

    blocked = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "merged",
            "draft_id": "merged-other",
        },
    )
    assert blocked.status_code == 400
    assert "not bound to a state_lock_version" in blocked.json()["detail"]


def test_start_validation_for_merged_draft_rejects_binding_version_mismatch(client, db, test_novel_id):
    chapter_id = "ch-validate-merged-mismatch"
    _insert_chapter(db, chapter_id, test_novel_id, 21)
    _insert_state_lock(db, chapter_id, test_novel_id)

    seeded = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "merged",
            "draft_id": "merged-current",
            "plan_version": 4,
            "state_lock_version": 1,
        },
    )
    assert seeded.status_code == 201

    mismatch = client.post(
        f"/api/v1/chapters/{chapter_id}/validate",
        json={
            "draft_type": "merged",
            "draft_id": "merged-current",
            "plan_version": 5,
            "state_lock_version": 1,
        },
    )
    assert mismatch.status_code == 400
    assert "plan_version does not match stored draft binding" in mismatch.json()["detail"]


def test_review_approval_is_blocked_by_validation_issues(client, db, test_novel_id):
    chapter_id = "ch-validate-approve"
    _insert_chapter(db, chapter_id, test_novel_id, 19)
    _insert_beat_sheet(db, chapter_id)
    _insert_state_lock(db, chapter_id, test_novel_id)
    _insert_fusion_draft(db, chapter_id)

    db.execute(
        """
        UPDATE state_lock_versions
        SET ending_lock_json = ?
        WHERE chapter_id = ? AND version = 1
        """,
        (
            json.dumps(
                {
                    "entries": [
                        {
                            "key": "ending_target",
                            "label": "目标终态",
                            "value": "钱府",
                            "source": "test",
                            "kind": "ending_target",
                            "status": "normal",
                            "metadata": {},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            chapter_id,
        ),
    )
    db.execute(
        """
        UPDATE state_locks
        SET ending_lock_json = ?
        WHERE chapter_id = ?
        """,
        (
            json.dumps(
                {
                    "entries": [
                        {
                            "key": "ending_target",
                            "label": "目标终态",
                            "value": "钱府",
                            "source": "test",
                            "kind": "ending_target",
                            "status": "normal",
                            "metadata": {},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            chapter_id,
        ),
    )
    db.get_connection().commit()

    res = client.put(
        f"/api/v1/novels/{test_novel_id}/chapters/19/review",
        json={"status": "approved", "memo": "准备发布"},
    )
    assert res.status_code == 400
    assert "Publish blocked" in json.dumps(res.json(), ensure_ascii=False)


def test_publish_check_returns_blocking_issues(client, db, test_novel_id):
    chapter_id = "ch-validate-gate"
    _insert_chapter(db, chapter_id, test_novel_id, 20)
    _insert_beat_sheet(db, chapter_id)
    _insert_state_lock(db, chapter_id, test_novel_id)
    _insert_fusion_draft(db, chapter_id)

    gate = client.post(f"/api/v1/chapters/{chapter_id}/publish-check")
    assert gate.status_code == 200
    body = gate.json()
    assert body["publishable"] is False
    assert body["blocking_issues"]
