"""translate_text tests, against a stand-in for the API client. The page text
is invented, so this file carries no personal data."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from translate_text import MODEL, SCHEMA, SYSTEM, render_md, translate_page

REPLY = {"lines": [{"ja": "氏名  山田一郎", "en": "Name  Yamada Ichirō (山田一郎)"},
                   {"ja": "【生年月日】明治32年3月15日", "en": "Date of birth: 15 March 1899"}],
         "notes": ["Reading of 一郎 is unconfirmed."]}


class FakeClient:
    def __init__(self, status="completed", refuse=False):
        self.sent = None
        self.status = status
        self.refuse = refuse
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.sent = kwargs
        part = (SimpleNamespace(type="refusal", refusal="no") if self.refuse
                else SimpleNamespace(type="output_text", text=json.dumps(REPLY, ensure_ascii=False)))
        return SimpleNamespace(
            status=self.status, _request_id="req_test",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            output=[SimpleNamespace(type="message", content=[part])],
            output_text="" if self.refuse else part.text)


def test_request_and_reply():
    client = FakeClient()
    assert translate_page(client, "氏名  山田一郎\n【生年月日】明治32年3月15日") == REPLY
    sent = client.sent
    assert sent["model"] == MODEL and sent["instructions"] == SYSTEM
    assert sent["text"]["format"]["schema"] is SCHEMA and sent["text"]["format"]["strict"]


def test_refusal_is_an_error():
    with pytest.raises(RuntimeError, match="declined"):
        translate_page(FakeClient(refuse=True), "x")


def test_cut_off_reply_is_an_error():
    with pytest.raises(RuntimeError, match="cut off"):
        translate_page(FakeClient("incomplete"), "x")


def test_glossary_is_in_the_prompt():
    assert "【出生地】 = Place of birth" in SYSTEM and "ビリグヰ駅 = Birigui Station" in SYSTEM


def test_side_by_side():
    md = render_md("p-01", REPLY)
    assert "| 氏名  山田一郎 | Name  Yamada Ichirō (山田一郎) |" in md
    assert md.rstrip().endswith("- Reading of 一郎 is unconfirmed.")
