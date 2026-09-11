def test_protocol_contains_all_hard_privacy_rules(repo_root):
    text = (repo_root / "adapters/shared/learning-protocol.md").read_text()
    assert "Raw evidence must never be requested" in text
    assert "When Learning Mode is OFF" in text
    assert "candidate observation" in text.lower()
    assert "project discovery is not evidence" in text.lower()


def test_protocol_names_every_required_adapter_operation(repo_root):
    text = (repo_root / "docs/adapter-contract.md").read_text()
    for operation in [
        "session-start",
        "on",
        "off",
        "status",
        "context",
        "observe",
        "project puc",
        "test request",
        "test record",
    ]:
        assert f"learn {operation}" in text


def test_readme_states_core_privacy_invariants(repo_root):
    text = (repo_root / "README.md").read_text()
    assert "starts OFF" in text
    assert "local" in text.lower()
    assert "raw evidence" in text.lower()
    assert "Obsidian" in text and "future" in text.lower()
