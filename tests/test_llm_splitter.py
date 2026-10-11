from src.llm.splitter import TRUNCATED_NOTE, split_reply


def test_short_reply_is_one_part() -> None:
    assert split_reply("  你好！  ", 100, 5) == ["你好！"]


def test_empty_reply_has_no_parts() -> None:
    assert split_reply(" \n ", 100, 5) == []


def test_splits_at_paragraphs_first() -> None:
    first, second = "第一段。" * 10, "第二段。" * 10
    assert split_reply(f"{first}\n\n{second}", 50, 5) == [first, second]


def test_merges_short_paragraphs_that_fit() -> None:
    assert split_reply("一。\n\n二。\n\n三。", 100, 5) == ["一。\n\n二。\n\n三。"]


def test_splits_long_chinese_paragraph_at_sentences() -> None:
    sentence = "这是一个完整的句子。"  # 10 characters
    parts = split_reply(sentence * 12, 35, 10)
    assert parts == [sentence * 3] * 4


def test_keeps_spaces_between_english_sentences() -> None:
    text = "One sentence here. Another one follows. And a third one."
    parts = split_reply(text, 40, 5)
    assert parts == ["One sentence here. Another one follows.", "And a third one."]
    assert " ".join(parts) == text


def test_cuts_inside_text_without_boundaries() -> None:
    assert split_reply("a" * 250, 100, 5) == ["a" * 100, "a" * 100, "a" * 50]


def test_truncates_to_max_parts_with_a_note() -> None:
    text = "\n\n".join(f"段落{i}。" * 20 for i in range(8))
    parts = split_reply(text, 100, 3)
    assert len(parts) == 3
    assert parts[-1].endswith(TRUNCATED_NOTE)
    assert "段落3" not in "".join(parts)


def test_no_part_exceeds_the_limit() -> None:
    text = "第一行很长" * 30 + "\n短行\n" + "第三行。" * 40
    for part in split_reply(text, 60, 100):
        assert 0 < len(part) <= 60
