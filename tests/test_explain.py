from dataclasses import fields

from pocumentary.explain import explain
from pocumentary.spec import Annotation, Layout, Pane, Recording, Verify


def test_explain_documents_every_schema_field():
    """Coarse drift guard: every dataclass field name must appear somewhere in
    the reference. A new field added to spec.py without documenting it here
    fails this test."""
    text = explain()
    for dc in (Recording, Layout, Pane, Verify, Annotation):
        for f in fields(dc):
            assert f.name in text, f"{dc.__name__}.{f.name} is undocumented"


def test_explain_names_the_tables_and_commands():
    text = explain()
    for table in ("[recording]", "[layout]", "[[pane]]", "[verify]"):
        assert table in text
    for cmd in ("validate", "dryrun", "record", "scaffold", "annotate"):
        assert cmd in text


def test_explain_documents_the_layout_modes():
    text = explain()
    for mode in ("columns", "rows", "grid"):
        assert mode in text


def test_explain_returns_substantial_text():
    assert isinstance(explain(), str)
    assert len(explain()) > 400


def test_explain_documents_the_annotation_block():
    text = explain()
    assert "[[annotation]]" in text
    assert "pane:<title>" in text


def test_explain_documents_narrate_and_tts():
    from pocumentary.explain import explain
    text = explain()
    assert "pocumentary narrate" in text
    assert "[tts]" in text
    assert "voice_id" in text            # ElevenLabs voice id key
    assert "pip install" in text and "pocumentary[tts]" in text  # one-time install
    assert "full" in text.lower() and "sentence" in text.lower()  # authoring guidance
    # [tts] is no longer described as merely "reserved / not yet acted on"
    assert "Reserved (parsed and preserved, not yet acted on): the [tts] block" not in text
