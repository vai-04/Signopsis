import pytest
from pydantic import ValidationError

from setu.perceive.fake import fake_percept
from setu.schemas import CaptionTarget, Grounding, PerceptEvent, RenderPlan, SemanticFrame
from setu.schemas.ws import CaptionFinal, client_message, server_message


def test_percept_roundtrip():
    ev = fake_percept(0)
    assert ev.id.startswith("pe_")
    again = PerceptEvent.model_validate_json(ev.model_dump_json())
    assert again == ev
    assert all(s.cands == sorted(s.cands, key=lambda c: c.score, reverse=True) for s in ev.lattice)


def test_frame_requires_grounding():
    with pytest.raises(ValidationError):
        SemanticFrame(utterance="hi", lang="en", speech_act="statement", grounding=[], trust=0.9, provenance={})
    f = SemanticFrame(utterance="hi", lang="en", speech_act="statement", trust=0.9, provenance={},
                      grounding=[Grounding(span=(0, 2), percept_ids=["pe_x"], t=(0, 10))])
    assert f.id.startswith("sf_")
    assert list(SemanticFrame.model_fields)[0] == "utterance"


def test_client_discriminator():
    m = client_message.validate_json('{"type":"audio.chunk","seq":1,"pcm16_b64":"AAA=","t":5}')
    assert m.type == "audio.chunk" and m.seq == 1
    m = client_message.validate_json('{"type":"session.start","mode":"LISTEN"}')
    assert m.spoken_langs == ["en"]
    with pytest.raises(ValidationError):
        client_message.validate_json('{"type":"nope"}')


def test_server_message_roundtrip():
    plan = RenderPlan(frame_id="sf_1", gate="emit",
                      targets=[CaptionTarget(lang="en", text="hello", trust_badge="high")])
    msg = CaptionFinal(segment_id="seg_1", plan=plan, t0=0, t1=100)
    back = server_message.validate_json(msg.model_dump_json())
    assert back.plan.targets[0].kind == "caption"
