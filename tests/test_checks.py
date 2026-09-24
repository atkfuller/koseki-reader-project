"""Review-flag tests. Names are invented; the situations are the ones found on
the Takagi register (a confident 恵 -> 惠 misread, a grandfather and grandson
one kanji apart)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.checks import needs_review, review
from koseki.tier1 import Certificate, Event, Field, Person


def F(label, value, date=None, conf=0.99):
    return Field(label=label, value=value, page=1, box=(0, 0, 1, 1), conf=conf, date=date)


def person(given, born, father, mother, kin, surname="山田"):
    return Person(given_name=given, surname=surname, fields=[
        F("名", given), F("生年月日", "", date=born),
        F("父", father), F("母", mother), F("続柄", kin)])


def cert(*persons):
    return Certificate(issue_no=None, office=None, pages=[1], persons=list(persons))


def flags(c):
    return {(f.label, f.value): f.review for f in needs_review(c)}


def test_links_parents_listed_in_the_registry():
    c = cert(person("一郎", "1899-03-15", "山田幸市", "山田ハナ", "長男"),
             person("ウメ", "1903-07-31", "田中平市", "田中ミト", "三女"),
             person("幸道", "1930-11-29", "山田一郎", "山田ウメ", "長男"))
    review(c)
    assert c.relationships == [{"child": 2, "parent": 0, "role": "father"},
                               {"child": 2, "parent": 1, "role": "mother"}]
    assert not needs_review(c)


def test_kanji_reused_across_generations_is_not_a_misread():
    # 一郎's father 山田幸市 and 一郎's son 山田幸道 differ by one kanji; the
    # son was born after 一郎, so he cannot be the father 山田幸市 misread.
    c = cert(person("一郎", "1899-03-15", "山田幸市", "山田ハナ", "長男"),
             person("幸道", "1930-11-29", "山田一郎", "山田ウメ", "長男"))
    review(c)
    assert not needs_review(c)


def test_near_miss_on_a_plausible_parent_is_flagged_on_both_sides():
    c = cert(person("一郎", "1899-03-15", "山田幸市", "山田ハナ", "長男"),
             person("次郎", "1930-11-29", "山田一朗", "山田ウメ", "二男"))
    review(c)
    f = flags(c)
    assert any(r.startswith("parent:") for r in f[("父", "山田一朗")])
    assert any(r.startswith("parent:") for r in f[("名", "一郎")])
    assert not c.relationships


def test_exact_match_to_an_impossible_parent_is_flagged():
    c = cert(person("花子", "1930-01-01", "山田一郎", "山田ウメ", "長女"),
             person("一郎", "1935-01-01", "山田太郎", "山田ハナ", "長男"))
    review(c)
    assert any(r.startswith("parent:") for r in flags(c)[("父", "山田一郎")])
    assert not c.relationships


def test_variant_character_flagged_once_naming_every_name():
    c = cert(person("惠子", "1930-01-01", "髙田一郎", "髙田ウメ", "長女", surname="髙田"))
    review(c)
    f = flags(c)
    assert list(f) == [("名", "惠子"), ("父", "髙田一郎")]
    (why,) = f[("父", "髙田一郎")]
    assert "髙田一郎, 髙田ウメ" in why


def test_low_confidence_and_birth_date_mismatch():
    p = person("一郎", "1899-03-15", "田中幸市", "田中ハナ", "長男")
    p.fields[0].conf = 0.6
    p.events = [Event(type="出生", fields=[F("出生日", "", date="1899-03-16")])]
    c = cert(p)
    review(c)
    f = flags(c)
    assert f[("名", "一郎")] == ["low-conf: OCR confidence 0.60"]
    assert any(r.startswith("birth-date:") for r in f[("出生日", "")])
