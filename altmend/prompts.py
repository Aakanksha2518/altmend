"""The briefs we give Gemma. Kept in one place so they are easy to tune."""

ALT_TEXT_RULES = """You are writing alt text for a screen reader.

Rules:
- One sentence, at most {max_chars} characters.
- Say what matters in the picture, not what kind of file it is.
- Never start with "image of", "picture of", "graphic showing" or similar.
- If the picture contains words, charts or numbers that carry the meaning, put those in.
- If it is decorative and carries no information, reply with exactly: DECORATIVE
- Plain {language}. No quotes around your answer, no markdown, no explanation.

Reply with the alt text only."""

CONTEXT_NOTE = """
Where this picture appears:
- file: {document}
- nearby text: {surrounding}
Use this only to decide what is worth mentioning."""

LONG_DESCRIPTION_RULES = """Describe this picture for someone who cannot see it.

Rules:
- Two to five sentences in plain {language}.
- Lead with the main subject, then the details that change the meaning.
- Read out any text, labels, axis names or numbers that the picture relies on.
- No guessing about things you cannot see. No markdown.

Reply with the description only."""


def alt_text_prompt(max_chars: int, language: str, document: str = "", surrounding: str = "") -> str:
    brief = ALT_TEXT_RULES.format(max_chars=max_chars, language=language)
    if surrounding.strip():
        brief += CONTEXT_NOTE.format(document=document, surrounding=surrounding.strip()[:400])
    return brief


def long_description_prompt(language: str) -> str:
    return LONG_DESCRIPTION_RULES.format(language=language)
