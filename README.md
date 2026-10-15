# altmend

Find images with missing alt text in your HTML and Markdown, and write it for them — using **Gemma 4** vision.

Most websites and docs ship with images that screen readers simply skip over, because `alt` is empty, absent, or set to something useless like `"image"`. Fixing that by hand across a whole site is dull work, so it never gets done. `altmend` does it in one command and writes the text straight back into your files.

```
$ altmend scan docs/

docs/report.html
  line 7: signups-chart.png  (no alt attribute)
  line 9: divider.png        (placeholder alt 'image')

2 image(s) need alt text. Run 'altmend fix' to write it.

$ altmend fix docs/
  report.html:7  signups-chart.png
    -> Signups rose each month from 60 in January to a peak of 175 in May
  report.html:9  divider.png
    -> "" (decorative)

wrote alt text for 2 image(s).
```

## Why Gemma 4

Alt text needs a model that can actually read a picture — the numbers on a chart, the words on a poster, the error in a screenshot. Gemma 4 is natively multimodal and reads text inside images well, so the output describes what the image *says*, not just what it looks like.

It is also Apache 2.0 with open weights, which matters for a tool like this: you can point `altmend` at a local Gemma on your own machine and never send your unreleased screenshots to anyone's server.

## Install

```bash
git clone https://github.com/Aakanksha2518/altmend
cd altmend
pip install -e .
```

Get a free key from [Google AI Studio](https://aistudio.google.com) and set it:

```bash
export GEMINI_API_KEY=your-key-here
```

## Use

```bash
altmend scan docs/                  # list what is missing, no model call, free
altmend fix docs/                   # write alt text into the files
altmend fix docs/ --dry-run         # show what it would write, change nothing
altmend describe photo.jpg          # one image, one line of alt text
altmend describe photo.jpg --long   # a short paragraph instead
```

Try it on the bundled sample site:

```bash
altmend fix examples/ --dry-run
```

### Run it entirely on your own machine

Gemma 4's weights are open, so no API key is needed if you serve it yourself:

```bash
ollama run gemma4:31b
altmend fix docs/ --base-url http://localhost:11434/v1 --model gemma4:31b
```

Any OpenAI-compatible server works — Ollama, vLLM, llama.cpp, OpenRouter.

### Options

| Flag | What it does |
| --- | --- |
| `--dry-run` | Print the alt text without touching your files |
| `--rewrite-all` | Also replace alt text that already looks fine |
| `--language` | Write the alt text in another language (Gemma 4 covers 140+) |
| `--max-chars` | Length limit, default 125 — the usual screen-reader guidance |
| `--model` | Default `gemma-4-31b-it`; `gemma-4-26b-a4b-it` is faster |
| `--base-url` | Point at a local or third-party OpenAI-compatible server |
| `--skip-remote` | Don't download images hosted elsewhere |
| `--no-context` | Don't send the surrounding page text to the model |
| `--no-cache` | Ask the model again for images it has already seen |

## How it works

1. **Scan.** Walks your folder and pulls every `<img>` tag and `![](...)` from HTML and Markdown. An image counts as needing work if `alt` is missing, empty, or one of the usual placeholder words.
2. **Read the picture.** Loads the image file (or downloads it, if remote) and sends it to Gemma 4 with the surrounding paragraph as context, so the description mentions what the page is actually about.
3. **Clean up.** Trims to the length limit, strips openers like "image of" that screen readers already announce, and respects a `DECORATIVE` verdict by writing `alt=""` — which is the correct markup for an image that carries no meaning.
4. **Write it back.** Edits the tag in place. Everything else in your file — indentation, other attributes, Markdown titles — is left exactly as it was.

Answers are cached by the image's own hash in `.altmend-cache.json`, so the same picture used on ten pages costs one model call, and re-running after an edit is free.

## Tests

```bash
pytest
```

16 tests, none of which need an API key — the model is swapped for a stand-in, so the scanning and file-editing logic is tested on its own.

## Limits

- Covers HTML and Markdown. JSX, Vue and templating languages are not parsed yet.
- The model can be wrong about an image, so `--dry-run` first on anything that matters.
- Alt text is a judgement call. This gets you a solid draft everywhere instead of nothing anywhere.

## License

MIT. See [LICENSE](LICENSE).
