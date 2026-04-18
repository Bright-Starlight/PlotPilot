"""State lock API integration tests."""
from __future__ import annotations


def _insert_chapter(db, chapter_id: str, novel_id: str, number: int, title: str = "第一章"):
    db.execute(
        """
        INSERT INTO chapters (id, novel_id, number, title, content, outline, status, tension_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (chapter_id, novel_id, number, title, "旧正文", "玉佩价值50两\n夜里转往钱府", "draft", 50.0),
    )
    db.get_connection().commit()


def test_generate_and_update_state_locks(client, db, test_novel_id):
    chapter_id = "state-lock-ch-1"
    _insert_chapter(db, chapter_id, test_novel_id, 1)

    created = client.post(f"/api/v1/chapters/{chapter_id}/state-locks", json={"plan_version": 3})
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["state_lock_id"]
    assert created_body["version"] == 1
    assert "numeric_lock" in created_body

    current = client.get(f"/api/v1/chapters/{chapter_id}/state-locks/current")
    assert current.status_code == 200
    current_body = current.json()
    assert current_body["state_lock_id"] == created_body["state_lock_id"]

    patch_payload = {
        "change_reason": "终态改到钱府正厅",
        "time_lock": current_body["time_lock"],
        "location_lock": current_body["location_lock"],
        "character_lock": current_body["character_lock"],
        "item_lock": current_body["item_lock"],
        "numeric_lock": current_body["numeric_lock"],
        "event_lock": current_body["event_lock"],
        "ending_lock": {
            "entries": [
                {
                    "key": "ending_target",
                    "label": "目标终态",
                    "value": "钱府正厅",
                    "source": "manual",
                    "kind": "ending_target",
                    "status": "normal",
                    "metadata": {},
                }
            ]
        },
    }
    updated = client.patch(f"/api/v1/state-locks/{created_body['state_lock_id']}", json=patch_payload)
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["version"] >= 2
    assert updated_body["change_reason"] == "终态改到钱府正厅"
    assert updated_body["ending_lock"]["entries"][0]["value"] == "钱府正厅"
