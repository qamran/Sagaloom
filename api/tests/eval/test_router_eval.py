"""Router eval (R6.5): on 15 labelled messages the router picks the right mode for at least 13.

Needs a real OpenRouter key. Excluded from the default run; run with:
    uv run pytest -m eval tests/eval/test_router_eval.py -v -s

One real call per message, on the `router` role (the guard's model, built through
`make_model_for` so the alias and the provider pin are the app's own).
"""

import pytest

from sagaloom.config import Settings
from sagaloom.model_settings import ModelSettings
from sagaloom.router import route
from sagaloom.web.app import make_model_for

LABELLED: list[tuple[str, str]] = [
    ("brainstorm", "Give me three ideas for a festival in Velmar."),
    ("brainstorm", "What could the Ashen Choir sing about? Just brainstorming."),
    ("brainstorm", "Suggest a name for a new tavern by the harbour."),
    ("brainstorm", "I'm stuck: what kind of conflict could start between Velmar and its neighbours?"),
    ("brainstorm", "Help me think up a legend about the moon."),
    ("query", "How many moons does Velmar have?"),
    ("query", "Who is the mayor of Velmar?"),
    ("query", "What do we know about Ister?"),
    ("query", "Which entries mention the harbour?"),
    ("query", "Is there anything in canon about the Ashen Choir?"),
    ("edit", "Velmar has two moons now, not one."),
    ("edit", "Add a place called Ostra, a port town with a deep harbour."),
    ("edit", "The mayor's name is Elsbeth Varr-Halden; update her entry."),
    ("edit", "Delete the rumour about the drowned bell."),
    ("edit", "The harbour freezes every winter."),
]
MIN_CORRECT = 13


@pytest.mark.eval
async def test_router_picks_the_labelled_mode(tmp_path):
    settings = Settings()
    model_settings = ModelSettings(tmp_path / "model_settings.json", settings)
    model = make_model_for(settings, model_settings)("router")
    model_id = model_settings.get_model_settings()["guard"]
    provider = {m.id: m.provider for m in settings.allowed_models}.get(model_id)
    print(f"\nRouter eval, model {model_id} via {provider} (no fallbacks), role {model.metadata['role']}")

    correct = 0
    misses: list[tuple[str, str, str]] = []
    for expected, text in LABELLED:
        try:
            got = (await route(model, text)).mode
        except Exception as exc:  # noqa: BLE001 - an error counts as a miss
            got = f"error:{type(exc).__name__}"
        ok = got == expected
        correct += ok
        if not ok:
            misses.append((expected, got, text))
        print(f"  {'PASS' if ok else 'MISS'}  [{expected:10}] got {got:10} {text!r}")

    for expected, got, text in misses:
        print(f"  miss: expected {expected}, got {got}: {text!r}")
    print(f"router: {correct}/{len(LABELLED)} (need {MIN_CORRECT})")
    assert correct >= MIN_CORRECT, f"{correct}/{len(LABELLED)} correct; misses: {misses}"
