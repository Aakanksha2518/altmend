"""Find image references in HTML and Markdown files, and write alt text back."""

import html
import re
from dataclasses import dataclass
from pathlib import Path

HTML_SUFFIXES = {".html", ".htm", ".xhtml"}
MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdx"}

# <img ...> including self-closing forms.
HTML_IMAGE_TAG = re.compile(r"<img\b[^>]*?/?>", re.IGNORECASE | re.DOTALL)
# ![alt](path "optional title")
MARKDOWN_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\(\s*(?P<path><[^>]+>|[^)\s]+)(?P<title>\s+\"[^\"]*\")?\s*\)")

# Words people type when they are just filling the box in.
PLACEHOLDER_ALTS = {
    "", "image", "img", "photo", "picture", "screenshot", "graphic",
    "icon", "alt", "alt text", "todo", "tbd", "placeholder", "untitled",
}


@dataclass
class ImageReference:
    """One image found inside a document."""

    document: Path
    line_number: int
    source: str              # the src / path exactly as written
    current_alt: str | None  # None means the alt attribute is absent
    span: tuple[int, int]    # character range of the tag inside the document
    syntax: str              # "html" or "markdown"

    @property
    def is_remote(self) -> bool:
        return self.source.lower().startswith(("http://", "https://", "//"))

    @property
    def needs_alt(self) -> bool:
        if self.current_alt is None:
            return True
        return self.current_alt.strip().lower().strip(".") in PLACEHOLDER_ALTS


def _attribute_value(tag: str, attribute: str) -> str | None:
    pattern = re.compile(
        rf"\b{attribute}\s*=\s*(\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s\"'>]+))",
        re.IGNORECASE,
    )
    found = pattern.search(tag)
    if not found:
        return None
    raw = found.group("double") or found.group("single") or found.group("bare") or ""
    return html.unescape(raw)


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def find_images(document: Path, text: str) -> list[ImageReference]:
    """Return every image reference in one document, in the order it appears."""
    suffix = document.suffix.lower()
    references: list[ImageReference] = []

    if suffix in HTML_SUFFIXES:
        for tag in HTML_IMAGE_TAG.finditer(text):
            source = _attribute_value(tag.group(0), "src")
            if not source:
                continue
            references.append(
                ImageReference(
                    document=document,
                    line_number=_line_of(text, tag.start()),
                    source=source,
                    current_alt=_attribute_value(tag.group(0), "alt"),
                    span=tag.span(),
                    syntax="html",
                )
            )

    elif suffix in MARKDOWN_SUFFIXES:
        for match in MARKDOWN_IMAGE.finditer(text):
            source = match.group("path").strip("<>")
            references.append(
                ImageReference(
                    document=document,
                    line_number=_line_of(text, match.start()),
                    source=source,
                    current_alt=match.group("alt"),
                    span=match.span(),
                    syntax="markdown",
                )
            )
        # Markdown files often contain raw <img> tags too.
        for tag in HTML_IMAGE_TAG.finditer(text):
            source = _attribute_value(tag.group(0), "src")
            if not source:
                continue
            references.append(
                ImageReference(
                    document=document,
                    line_number=_line_of(text, tag.start()),
                    source=source,
                    current_alt=_attribute_value(tag.group(0), "alt"),
                    span=tag.span(),
                    syntax="html",
                )
            )
        references.sort(key=lambda reference: reference.span[0])

    return references


def collect_documents(target: Path) -> list[Path]:
    """One file, or every HTML/Markdown file under a folder."""
    wanted = HTML_SUFFIXES | MARKDOWN_SUFFIXES
    if target.is_file():
        return [target] if target.suffix.lower() in wanted else []

    skipped_folders = {"node_modules", ".git", "venv", ".venv", "dist", "build", "__pycache__"}
    documents = [
        path
        for path in sorted(target.rglob("*"))
        if path.suffix.lower() in wanted
        and not any(part in skipped_folders for part in path.parts)
    ]
    return documents


def _rewrite_html_tag(tag: str, alt_text: str) -> str:
    safe_alt = html.escape(alt_text, quote=True)
    existing = re.compile(r"(\balt\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s\"'>]+)", re.IGNORECASE)
    if existing.search(tag):
        return existing.sub(lambda _: f'alt="{safe_alt}"', tag, count=1)

    if tag.rstrip().endswith("/>"):
        head = tag.rstrip()[:-2].rstrip()
        return f'{head} alt="{safe_alt}" />'
    head = tag.rstrip()[:-1].rstrip()
    return f'{head} alt="{safe_alt}">'


def _rewrite_markdown_image(snippet: str, alt_text: str) -> str:
    safe_alt = alt_text.replace("[", "(").replace("]", ")")
    return MARKDOWN_IMAGE.sub(
        lambda match: f"![{safe_alt}]({match.group('path')}{match.group('title') or ''})",
        snippet,
        count=1,
    )


def apply_alt_texts(text: str, decisions: list[tuple[ImageReference, str]]) -> str:
    """Write new alt text into the document. Later spans are edited first so
    earlier character positions stay valid."""
    updated = text
    for reference, alt_text in sorted(decisions, key=lambda item: item[0].span[0], reverse=True):
        start, end = reference.span
        snippet = updated[start:end]
        if reference.syntax == "html":
            replacement = _rewrite_html_tag(snippet, alt_text)
        else:
            replacement = _rewrite_markdown_image(snippet, alt_text)
        updated = updated[:start] + replacement + updated[end:]
    return updated
