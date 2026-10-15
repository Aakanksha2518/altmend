"""altmend - find images with missing alt text and write it for them."""

import argparse
import sys
from pathlib import Path

from .cache import DescriptionCache
from .gemma import DEFAULT_MODEL, GemmaVision, ImageUnreadable, ModelUnavailable, mime_type_for, read_image_bytes
from .prompts import alt_text_prompt, long_description_prompt
from .scanner import ImageReference, apply_alt_texts, collect_documents, find_images

DECORATIVE_MARKER = "DECORATIVE"


def surrounding_text(document_text: str, position: int, window: int = 300) -> str:
    """A little of the text around the image, to steer what is worth mentioning."""
    start = max(0, position - window)
    return " ".join(document_text[start:position + window].split())


def tidy_alt_text(raw: str, max_chars: int) -> str:
    cleaned = " ".join(raw.replace("\n", " ").split()).strip().strip('"').strip("'")
    for opener in ("image of ", "picture of ", "a picture of ", "an image of ", "photo of "):
        if cleaned.lower().startswith(opener):
            cleaned = cleaned[len(opener):]
            cleaned = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
    if len(cleaned) > max_chars:
        cut = cleaned[:max_chars].rsplit(" ", 1)[0]
        cleaned = cut.rstrip(" ,;:") + "..."
    return cleaned


def gather_references(target: Path, include_filled: bool) -> list[tuple[Path, str, list[ImageReference]]]:
    findings = []
    for document in collect_documents(target):
        try:
            text = document.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        references = [
            reference
            for reference in find_images(document, text)
            if include_filled or reference.needs_alt
        ]
        if references:
            findings.append((document, text, references))
    return findings


def command_scan(options: argparse.Namespace) -> int:
    target = Path(options.path)
    findings = gather_references(target, include_filled=False)

    missing_count = 0
    for document, _text, references in findings:
        print(f"\n{document}")
        for reference in references:
            missing_count += 1
            reason = "no alt attribute" if reference.current_alt is None else f"placeholder alt {reference.current_alt!r}"
            print(f"  line {reference.line_number}: {reference.source}  ({reason})")

    if missing_count == 0:
        print("Every image already has useful alt text.")
        return 0

    print(f"\n{missing_count} image(s) need alt text. Run 'altmend fix' to write it.")
    return 1


def build_model(options: argparse.Namespace) -> GemmaVision:
    return GemmaVision(
        model=options.model,
        api_key=options.api_key,
        base_url=options.base_url,
        timeout=options.timeout,
    )


def command_fix(options: argparse.Namespace) -> int:
    target = Path(options.path)
    findings = gather_references(target, include_filled=options.rewrite_all)
    if not findings:
        print("Nothing to do. Every image already has useful alt text.")
        return 0

    try:
        model = build_model(options)
    except ModelUnavailable as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    cache_folder = target if target.is_dir() else target.parent
    cache = DescriptionCache(cache_folder, enabled=not options.no_cache)

    written_count = 0
    skipped_count = 0

    for document, text, references in findings:
        decisions: list[tuple[ImageReference, str]] = []

        for reference in references:
            if reference.is_remote and options.skip_remote:
                print(f"  skip (remote) {reference.source}")
                skipped_count += 1
                continue

            try:
                image_bytes = read_image_bytes(reference.source, document, timeout=options.timeout)
            except ImageUnreadable as problem:
                print(f"  skip {reference.source}: {problem}")
                skipped_count += 1
                continue

            key = DescriptionCache.key_for(image_bytes, options.model, options.language, options.max_chars)
            answer = cache.get(key)

            if answer is None:
                brief = alt_text_prompt(
                    max_chars=options.max_chars,
                    language=options.language,
                    document=str(document),
                    surrounding="" if options.no_context else surrounding_text(text, reference.span[0]),
                )
                try:
                    answer = model.describe(image_bytes, mime_type_for(reference.source), brief)
                except ModelUnavailable as problem:
                    print(f"  skip {reference.source}: {problem}")
                    skipped_count += 1
                    continue
                cache.put(key, answer)

            if answer.strip().upper().startswith(DECORATIVE_MARKER):
                alt_text = ""  # empty alt is the correct markup for a decorative image
                shown = '"" (decorative)'
            else:
                alt_text = tidy_alt_text(answer, options.max_chars)
                shown = alt_text

            decisions.append((reference, alt_text))
            print(f"  {document.name}:{reference.line_number}  {reference.source}\n    -> {shown}")

        if not decisions:
            continue

        if options.dry_run:
            written_count += len(decisions)
            continue

        updated = apply_alt_texts(text, decisions)
        try:
            document.write_text(updated, encoding="utf-8")
        except OSError as problem:
            print(f"error: could not write {document}: {problem}", file=sys.stderr)
            continue
        written_count += len(decisions)

    cache.save()

    verb = "would write" if options.dry_run else "wrote"
    summary = f"\n{verb} alt text for {written_count} image(s)"
    if cache.hits:
        summary += f", {cache.hits} reused from cache"
    if skipped_count:
        summary += f", {skipped_count} skipped"
    print(summary + ".")
    return 0


def command_describe(options: argparse.Namespace) -> int:
    image_path = Path(options.image)
    if not image_path.is_file() and not options.image.lower().startswith(("http://", "https://")):
        print(f"error: no such file: {image_path}", file=sys.stderr)
        return 2

    try:
        model = build_model(options)
        image_bytes = read_image_bytes(options.image, Path.cwd() / "placeholder", timeout=options.timeout)
    except (ModelUnavailable, ImageUnreadable) as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    mime = mime_type_for(options.image)
    try:
        if options.long:
            print(model.describe(image_bytes, mime, long_description_prompt(options.language)))
        else:
            answer = model.describe(
                image_bytes, mime, alt_text_prompt(options.max_chars, options.language)
            )
            print(tidy_alt_text(answer, options.max_chars))
    except ModelUnavailable as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    return 0


def add_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--api-key", default=None, help="overrides GEMINI_API_KEY")
    parser.add_argument(
        "--base-url",
        default=None,
        help="an OpenAI-compatible server instead of the Gemini API, e.g. http://localhost:11434/v1",
    )
    parser.add_argument("--language", default="English", help="language for the alt text (default: English)")
    parser.add_argument("--max-chars", type=int, default=125, help="length limit for alt text (default: 125)")
    parser.add_argument("--timeout", type=int, default=90, help="seconds to wait for the model")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="altmend",
        description="Find images with missing alt text and write it for them, using Gemma 4.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="list images that are missing alt text (no model call)")
    scan.add_argument("path", help="a file or a folder")
    scan.set_defaults(handler=command_scan)

    fix = commands.add_parser("fix", help="write alt text into the files")
    fix.add_argument("path", help="a file or a folder")
    fix.add_argument("--dry-run", action="store_true", help="show the alt text without editing anything")
    fix.add_argument("--rewrite-all", action="store_true", help="also replace alt text that already looks fine")
    fix.add_argument("--skip-remote", action="store_true", help="do not download images hosted elsewhere")
    fix.add_argument("--no-context", action="store_true", help="do not send the surrounding text to the model")
    fix.add_argument("--no-cache", action="store_true", help="ask the model again even for images seen before")
    add_model_options(fix)
    fix.set_defaults(handler=command_fix)

    describe = commands.add_parser("describe", help="describe one image and print it")
    describe.add_argument("image", help="path or URL of an image")
    describe.add_argument("--long", action="store_true", help="a short paragraph instead of one line")
    add_model_options(describe)
    describe.set_defaults(handler=command_describe)

    options = parser.parse_args(argv)
    return options.handler(options)


if __name__ == "__main__":
    raise SystemExit(main())
