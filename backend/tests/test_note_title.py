from app.services.ingestion import note_title


def test_short_first_line_is_the_title():
    assert note_title("Turium builds Zebra\n\nMore text.") == "Turium builds Zebra"


def test_label_before_colon_becomes_title():
    text = "Vendor contract: Acme Analytics renewal is due on 14 March 2027. Annual cost is 48,000 USD."
    assert note_title(text) == "Vendor contract"


def test_first_sentence_when_line_is_long():
    text = "The team agreed to ship on Friday. After that we will review the incident backlog in detail."
    assert note_title(text) == "The team agreed to ship on Friday"


def test_long_text_is_cut_at_a_word_with_ellipsis():
    text = "word " * 40
    title = note_title(text)

    assert title.endswith("…")
    assert len(title) <= 61
    assert title[:-1].split(" ")[-1] == "word"
