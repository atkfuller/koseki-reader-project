"""Second-engine name check. Boxes mirror what PaddleOCR and yomitoku returned
for the same page (a few pixels apart); the names are invented."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koseki.crosscheck import cross_check, second_read
from koseki.ocr.base import Line
from koseki.tier1 import Certificate, Event, Field, Person


def F(label, value, box):
    return Field(label=label, value=value, page=2, box=box, conf=0.996)


def L(text, box):
    return Line(text, box, 0.99)


def make():
    given = F("名", "惠子", (689, 985, 392, 101))             # merged 【名】 + name box
    father = F("父", "山田一郎", (691, 1183, 290, 51))
    spouse = F("配偶者氏名", "ヤマダ，ハナコ", (692, 476, 596, 49))
    place = F("出生地", "東京都", (691, 1300, 400, 51))      # not a name: never checked
    p = Person(given_name="惠子", fields=[given, father],
               events=[Event(type="婚姻", fields=[spouse, place])])
    return Certificate(issue_no=None, office=None, pages=[2], persons=[p]), given, father, spouse, place


SECOND = {2: [
    L("【名】", (691, 1026, 93, 55)), L("恵子", (824, 993, 247, 82)),
    L("【父】山田一郎", (693, 1182, 285, 48)),
    L("【配偶者氏名】ヤマダ ハナコ", (693, 474, 592, 50)),
    L("【出生地】京都府", (693, 1300, 400, 50)),
    L("うきはし", (0, 0, 2000, 3000)),                        # background noise, page-sized
]}


def test_reads_the_text_inside_a_fields_box():
    _, given, father, _, _ = make()
    assert second_read(given, SECOND[2]) == "恵子"
    assert second_read(father, SECOND[2]) == "山田一郎"


def test_flags_only_names_the_engines_disagree_on():
    cert, given, father, spouse, place = make()
    flagged = cross_check(cert, SECOND, "yomitoku")
    assert flagged == [given]
    assert "reads 恵子 where the primary read is 惠子" in given.review[0]
    assert not father.review
    assert not spouse.review        # comma vs space is not a different name
    assert not place.review         # places are not cross-checked


def test_nothing_read_is_not_a_disagreement():
    cert, given, *_ = make()
    assert cross_check(cert, {2: []}, "yomitoku") == []
    assert cross_check(cert, {}, "yomitoku") == []
    assert not given.review
