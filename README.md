# Rosetta

[![CI](https://github.com/adi45726/rosetta-translate/actions/workflows/ci.yml/badge.svg)](https://github.com/adi45726/rosetta-translate/actions/workflows/ci.yml)

Translate anything, into anything — 75 languages, automatic source-language
detection, no API key required.

## What it is

A small Flask app: a translation core (`src/translator/`) that's pure Python
and fully unit-tested in isolation, wrapped by a thin web layer (`web/`) that
serves a browser UI and a JSON API. Deployed as a Vercel serverless function.

## Design decisions

- **Provider: [MyMemory](https://mymemory.translated.net) API.** Free, no API
  key, no signup — the whole point was a translator that works the moment you
  clone it. The trade-off is a 500-character-per-request limit and variable
  quality (it blends translation memory with machine translation). The
  provider call is isolated to one function
  ([`src/translator/client.py`](src/translator/client.py)), so swapping in
  DeepL / Google Cloud Translation / Azure Translator later is a one-file
  change — nothing else in the app knows which provider it's talking to.
- **Detection: [`langdetect`](https://pypi.org/project/langdetect/), run
  locally.** No second network call for the "Detect language" option, and one
  less thing that can rate-limit you. It's seeded (`DetectorFactory.seed = 0`)
  because langdetect's classifier is otherwise non-deterministic on short
  text — same input can otherwise get a different guess between runs.
- **Same-language shortcut.** If the resolved source and target are the same
  (either picked directly, or resolved from auto-detect), the app returns the
  input text unchanged instead of round-tripping to MyMemory, which would
  otherwise reject the request outright.
- **Errors are typed, not stringly.** `ProviderError` (provider reached, but
  said no — bad language pair, etc.) and `ProviderUnavailableError` (network
  failure, timeout, bad response) are distinct exceptions, mapped to 502 and
  503 respectively at the Flask boundary — so a "MyMemory is down" looks
  different to the client than "you picked an unsupported language."

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt   # app deps + ruff/mypy/pytest

python web/app.py   # http://127.0.0.1:5053, PORT env var to override
```

## Development

```bash
ruff check .              # lint
mypy src/ web/app.py      # type check
pytest tests/ -v          # tests (39, no live network calls -- the MyMemory
                          # client is exercised against mocked responses)
```

The same three commands run in CI (`.github/workflows/ci.yml`) on every push
and PR to `main`, across Python 3.12 and 3.13.

## API

```
POST /api/translate
{
  "text": "Good morning",
  "source": "en",     // or "auto" to detect
  "target": "ja"
}
```

```json
{
  "translated_text": "おはようございます",
  "detected_source": null,
  "detected_source_name": null
}
```

`detected_source` / `detected_source_name` are populated only when
`source: "auto"` was used. Errors come back as `{"error": "..."}` with
`400` (bad request — missing/invalid fields, text over 500 chars, detection
failed), `502` (provider rejected the request), or `503` (provider
unreachable).

## Deploy

Already configured for Vercel (`vercel.json`, `@vercel/python` builder
pointed at `web/app.py`, same pattern as this author's other Flask-on-Vercel
projects):

```bash
vercel --prod
```

## Project structure

```
src/translator/
  languages.py    75 (code, name) pairs + lookup helpers
  client.py       MyMemory API client (the one place that knows the provider)
  detect.py       langdetect wrapper, seeded for determinism
  exceptions.py   TranslationError / ProviderError / ProviderUnavailableError / DetectionError
web/
  app.py          Flask routes: / and /api/translate
  templates/, static/   UI: language pickers, debounced auto-translate, swap, copy, theme toggle
tests/
  test_languages.py, test_client.py (mocked HTTP), test_detect.py (real, seeded),
  test_app.py (Flask test client, provider mocked)
```

## License

MIT
