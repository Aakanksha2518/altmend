"""Tests that do not need an API key: finding images and writing alt text back."""

from pathlib import Path

from altmend.cli import tidy_alt_text
from altmend.scanner import apply_alt_texts, find_images

PAGE = Path("page.html")
NOTES = Path("notes.md")


def test_finds_image_with_no_alt_attribute():
    text = '<p>hi</p>\n<img src="chart.png" width="400">'
    found = find_images(PAGE, text)
    assert len(found) == 1
    assert found[0].source == "chart.png"
    assert found[0].current_alt is None
    assert found[0].needs_alt is True
    assert found[0].line_number == 2


def test_placeholder_alt_counts_as_missing():
    text = '<img src="a.png" alt="image"><img src="b.png" alt="Sales rose in May">'
    first, second = find_images(PAGE, text)
    assert first.needs_alt is True
    assert second.needs_alt is False


def test_markdown_empty_alt_is_found():
    found = find_images(NOTES, "![](chart.png)\n\n![Already described](other.png)")
    assert [reference.needs_alt for reference in found] == [True, False]


def test_remote_images_are_flagged():
    found = find_images(PAGE, '<img src="https://cdn.example.com/a.png">')
    assert found[0].is_remote is True


def test_alt_text_is_inserted_into_html():
    text = '<img src="chart.png" width="400">'
    reference = find_images(PAGE, text)[0]
    updated = apply_alt_texts(text, [(reference, "Signups rose from 60 in January to 175 in May")])
    assert 'alt="Signups rose from 60 in January to 175 in May"' in updated
    assert 'src="chart.png"' in updated
    assert 'width="400"' in updated


def test_existing_alt_is_replaced_not_duplicated():
    text = '<img alt="image" src="chart.png">'
    reference = find_images(PAGE, text)[0]
    updated = apply_alt_texts(text, [(reference, "A bar chart of monthly signups")])
    assert updated.count("alt=") == 1
    assert "A bar chart of monthly signups" in updated


def test_self_closing_tag_keeps_its_slash():
    text = '<img src="chart.png" />'
    reference = find_images(PAGE, text)[0]
    updated = apply_alt_texts(text, [(reference, "A chart")])
    assert updated == '<img src="chart.png" alt="A chart" />'


def test_quotes_in_alt_text_do_not_break_the_tag():
    text = '<img src="poster.png">'
    reference = find_images(PAGE, text)[0]
    updated = apply_alt_texts(text, [(reference, 'Poster reading "Open Source Day"')])
    assert '&quot;Open Source Day&quot;' in updated
    assert updated.count('"') % 2 == 0


def test_markdown_alt_is_written_between_the_brackets():
    text = '![](chart.png "Monthly signups")'
    reference = find_images(NOTES, text)[0]
    updated = apply_alt_texts(text, [(reference, "Bar chart of signups by month")])
    assert updated == '![Bar chart of signups by month](chart.png "Monthly signups")'


def test_several_images_in_one_file_all_get_their_own_text():
    text = '<img src="one.png">\n<img src="two.png">'
    first, second = find_images(PAGE, text)
    updated = apply_alt_texts(text, [(first, "First picture"), (second, "Second picture")])
    assert 'src="one.png" alt="First picture"' in updated
    assert 'src="two.png" alt="Second picture"' in updated


def test_tidy_removes_image_of_and_trims_length():
    assert tidy_alt_text('"Image of a red bus"', 125) == "A red bus"
    assert len(tidy_alt_text("word " * 80, 40)) <= 43
