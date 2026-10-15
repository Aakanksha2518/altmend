"""Runs the whole 'fix' pipeline with a stand-in model, so no API key is needed."""

import shutil
from pathlib import Path

import altmend.cli as cli


class StandInModel:
    """Answers like Gemma would, without the network."""

    def __init__(self, answer="Bar chart showing signups rising from 60 in January to 175 in May"):
        self.answer = answer
        self.calls = 0

    def describe(self, image_bytes, mime_type, instruction):
        self.calls += 1
        return self.answer


def run_fix(tmp_path, monkeypatch, model, **flags):
    shutil.copytree(Path(__file__).parent / "examples", tmp_path / "site")
    monkeypatch.setattr(cli, "build_model", lambda options: model)

    arguments = ["fix", str(tmp_path / "site")]
    for name, value in flags.items():
        if value is True:
            arguments.append("--" + name.replace("_", "-"))
    cli.main(arguments)
    return tmp_path / "site"


def test_fix_writes_alt_text_into_html_and_markdown(tmp_path, monkeypatch):
    model = StandInModel()
    site = run_fix(tmp_path, monkeypatch, model)

    page = (site / "report.html").read_text(encoding="utf-8")
    notes = (site / "notes.md").read_text(encoding="utf-8")

    assert 'alt="Bar chart showing signups' in page
    assert "![Bar chart showing signups" in notes
    assert "alt=\"image\"" not in page  # the placeholder was replaced


def test_second_run_changes_nothing_more(tmp_path, monkeypatch):
    model = StandInModel()
    site = run_fix(tmp_path, monkeypatch, model)
    after_first = (site / "report.html").read_text(encoding="utf-8")

    cli.main(["fix", str(site)])
    assert (site / "report.html").read_text(encoding="utf-8") == after_first


def test_decorative_images_get_an_empty_alt(tmp_path, monkeypatch):
    site = run_fix(tmp_path, monkeypatch, StandInModel(answer="DECORATIVE"))
    page = (site / "report.html").read_text(encoding="utf-8")
    assert 'alt=""' in page


def test_dry_run_leaves_files_alone(tmp_path, monkeypatch):
    original = (Path(__file__).parent / "examples" / "report.html").read_text(encoding="utf-8")
    site = run_fix(tmp_path, monkeypatch, StandInModel(), dry_run=True)
    assert (site / "report.html").read_text(encoding="utf-8") == original


def test_cache_means_the_same_picture_is_only_sent_once(tmp_path, monkeypatch):
    model = StandInModel()
    run_fix(tmp_path, monkeypatch, model)
    # signups-chart.png appears in both files, divider.png once -> 2 calls, not 3
    assert model.calls == 2
