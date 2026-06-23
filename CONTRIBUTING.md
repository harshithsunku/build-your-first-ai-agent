# Contributing to Build Your First AI Agent

Thanks for taking the time. This repo is a teaching resource, so the bar for changes is
"does it make the lesson clearer?" — not "does it add a feature?".

## Ground rules

- **Pedagogy first.** The notebooks are deliberately explicit. Notebook 02 hand-rolls the
  agent loop on purpose; don't replace it with a framework — the contrast with notebook 03 is
  the whole point.
- **One loop, many tools.** Notebooks 04–06 reuse notebook 02's control loop verbatim and only
  change the capability table. Keep it that way; if you change the loop, change it everywhere.
- **Read-only and sandboxed.** Filesystem/log tools must stay sandboxed under their `ROOT`; the
  SQL tool must stay `SELECT`-only. Don't loosen these guards for convenience.
- **No secrets, no proprietary names.** All config comes from `.env` (git-ignored). Never
  commit an API key or a real endpoint, in code, outputs, or commit messages.
- **Minimal dependencies.** Core notebooks use only the `openai` client. Don't add a dependency
  unless a notebook genuinely needs it — open an issue first.

## Development setup

```bash
git clone https://github.com/harshithsunku/build-your-first-ai-agent.git
cd build-your-first-ai-agent

pip install -r requirements.txt
cp .env.example .env        # then edit with your provider + key

jupyter lab
```

Notebook 01 runs on any model. Notebooks 02–06 need a **tool-capable** model
(`gpt-4o-mini`, `qwen2.5`, `llama3.1`, …).

## Testing your change

There's no unit-test suite — the notebooks *are* the deliverable. Validate end-to-end:

```bash
# Run every notebook top to bottom against a configured provider
jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=180 \
  --output /tmp/out.ipynb <notebook>.ipynb
```

A clean run with no error outputs is the bar. For notebooks 05 and 06, confirm the generated
sample data (`sample_logs/`, `inventory.db`) is recreated and that the agent reaches a final
answer.

## Pull requests

1. **Open an issue first** for anything non-trivial. Cheap to discuss, expensive to redo.
2. **One concern per PR.** A wording fix doesn't need a surrounding refactor.
3. **Run the affected notebooks end-to-end** before pushing. Clear all outputs you don't intend
   to commit, and never commit cells that contain a key or a private endpoint.
4. **Keep the narrative intact.** Preserve the networking analogies, the stack-layer mapping
   table, and the markdown explanations — they carry the lesson.
5. **Tight commit messages.** Subject ≤ 70 chars, body wraps at 72, focus on the *why*.

## License

By contributing you agree your work is offered under the project's [MIT license](LICENSE).
