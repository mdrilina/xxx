"""CR-A: iedzīvotājs atsauc iesniegumu (POST /submissions/{id}/withdraw).

Sagaidāmās vērtības: tracker/CR-A.md un docs/openapi.yaml.
"""

import pytest

from app import storage

VALID_REASON = "Problēma jau ir atrisināta"


@pytest.fixture
def make_submission(client, valid_payload):
    """Izveido iesniegumu caur API un, ja vajag, iestata tam statusu."""

    def _make(status: str = "RECEIVED") -> dict:
        created = client.post("/submissions", json=valid_payload).json()
        if status != "RECEIVED":
            storage.update_status(created["id"], status)
        return created

    return _make


def withdraw(client, submission_id: str, body: dict):
    return client.post(f"/submissions/{submission_id}/withdraw", json=body)


def status_of(client, submission_id: str) -> str:
    return client.get(f"/submissions/{submission_id}").json()["status"]


def assert_validation_error_on_reason(response, issue: str | None = None):
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    fields = [detail["field"] for detail in error["details"]]
    assert "reason" in fields
    if issue is not None:
        assert {"field": "reason", "issue": issue} in error["details"]


def test_cra_ac1_received_200(client, make_submission):
    submission = make_submission("RECEIVED")

    response = withdraw(client, submission["id"], {"reason": VALID_REASON})

    assert response.status_code == 200
    assert response.json()["status"] == "WITHDRAWN"
    assert status_of(client, submission["id"]) == "WITHDRAWN"


def test_cra_ac2_in_progress_200(client, make_submission):
    submission = make_submission("IN_PROGRESS")

    response = withdraw(client, submission["id"], {"reason": VALID_REASON})

    assert response.status_code == 200
    assert response.json()["status"] == "WITHDRAWN"
    assert status_of(client, submission["id"]) == "WITHDRAWN"


def test_cra_ac3_answered_409(client, make_submission):
    submission = make_submission("ANSWERED")

    response = withdraw(client, submission["id"], {"reason": VALID_REASON})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert status_of(client, submission["id"]) == "ANSWERED"


def test_cra_ac4_second_withdraw_409(client, make_submission):
    submission = make_submission("RECEIVED")
    first = withdraw(client, submission["id"], {"reason": VALID_REASON})
    assert first.status_code == 200

    response = withdraw(client, submission["id"], {"reason": VALID_REASON})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert status_of(client, submission["id"]) == "WITHDRAWN"


def test_cra_ac5_unknown_id_404(client):
    response = withdraw(client, "IES-2026-999999", {"reason": VALID_REASON})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_cra_ac6_reason_missing_400(client, make_submission):
    submission = make_submission("RECEIVED")

    response = withdraw(client, submission["id"], {})

    assert_validation_error_on_reason(response, issue="REQUIRED")
    assert status_of(client, submission["id"]) == "RECEIVED"


def test_cra_ac6_reason_too_short_400(client, make_submission):
    submission = make_submission("RECEIVED")

    response = withdraw(client, submission["id"], {"reason": "a" * 9})

    # Līgumā nav noteikts `issue` kods par pārāk īsu vērtību: pārbauda tikai lauku.
    assert_validation_error_on_reason(response)
    assert status_of(client, submission["id"]) == "RECEIVED"


def test_cra_ac6_reason_too_long_400(client, make_submission):
    submission = make_submission("RECEIVED")

    response = withdraw(client, submission["id"], {"reason": "a" * 501})

    assert_validation_error_on_reason(response, issue="TOO_LONG")
    assert status_of(client, submission["id"]) == "RECEIVED"


@pytest.mark.parametrize(
    "reason",
    [
        "a" * 10,
        "ā" * 500,  # Robeža ir rakstzīmēs, ne baitos.
    ],
    ids=["10", "500"],
)
def test_cra_ac6_reason_boundaries_10_and_500_ok(client, make_submission, reason):
    submission = make_submission("RECEIVED")

    response = withdraw(client, submission["id"], {"reason": reason})

    assert response.status_code == 200
    assert response.json()["status"] == "WITHDRAWN"


def test_cra_ac7_audit_withdraw(client, make_submission):
    submission = make_submission("RECEIVED")
    assert (
        withdraw(client, submission["id"], {"reason": VALID_REASON}).status_code == 200
    )

    response = client.get(f"/submissions/{submission['id']}/audit")

    assert response.status_code == 200
    withdraw_entries = [e for e in response.json() if e["action"] == "WITHDRAW"]
    assert len(withdraw_entries) == 1
    assert withdraw_entries[0]["detail"] == VALID_REASON


@pytest.mark.skip(
    reason="CR-A precizējums 'Vai var atsaukt FORWARDED?' ir atvērts. "
    "Sagaidāmo rezultātu jāapstiprina produkta īpašniekam."
)
def test_cra_forwarded_409(client, make_submission):
    submission = make_submission("FORWARDED")

    response = withdraw(client, submission["id"], {"reason": VALID_REASON})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert status_of(client, submission["id"]) == "FORWARDED"


def test_cra_due_date_unchanged(client, make_submission):
    submission = make_submission("RECEIVED")

    response = withdraw(client, submission["id"], {"reason": VALID_REASON})

    assert response.status_code == 200
    assert response.json()["dueDate"] == submission["dueDate"]
    stored = client.get(f"/submissions/{submission['id']}").json()
    assert stored["dueDate"] == submission["dueDate"]
