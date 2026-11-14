"""Transcript cards preserve evidence and expose only the latest approval."""

from report_agent.application.onboarding import Onboarding
from report_agent.interfaces.gradio.transcript import snapshot


def test_report_history_survives_revisions_and_only_current_preview_is_active(tmp_path):
    session = Onboarding(draft="drafts/first")
    first = str(tmp_path / "first.pdf")
    session.files = [first]
    session.preview_path = tmp_path / "first.pdf"
    session.preview_reference = session.draft
    initial = snapshot(session)
    assert initial[0]["active"]
    session.draft = "drafts/revised"
    session.preview_reference = None
    session.preview_path = None
    session.files = []
    assert not snapshot(session)[0]["active"]
    session.preview_reference = session.draft
    session.preview_path = tmp_path / "new.pdf"
    session.files = [str(session.preview_path)]
    revised = snapshot(session)
    assert revised[0]["files"] == [first]
    assert not revised[0]["active"] and revised[1]["active"]
    assert not any(e["active"] for e in snapshot(session, busy=True))
    assert initial[0]["active"]  # Returned snapshots cannot mutate past UI updates.
    session.draft = None
    session.files = [str(tmp_path / "final.pdf")]
    final = snapshot(session)
    assert final[-1]["reference"] is None  # A repeat run has no draft approval.


def test_superseded_parameters_stay_visible_without_duplicate_active_actions():
    session = Onboarding(
        pending={"reference": "accepted/a/v1", "parameters": {"month": "Oct"}}
    )
    snapshot(session)
    session.pending["parameters"]["month"] = "Nov"
    snapshot(session)
    session.pending["parameters"]["month"] = "Oct"
    cards = snapshot(session)
    assert [e["active"] for e in cards] == [False, False, True]
    session.pending = None
    assert not any(e["active"] for e in snapshot(session))
    assert cards[1]["proposal"]["parameters"] == {"month": "Nov"}
