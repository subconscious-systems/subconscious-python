"""End-to-end tests for the Python SDK multimodal surface.

Skipped by default. Run with::

    SUBCONSCIOUS_API_KEY=... SUBCONSCIOUS_E2E=1 pytest tests/e2e/test_multimodal.py

Hits a live API; safe to run against the dev environment.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from subconscious import Image, Subconscious, densify_trace

E2E = os.environ.get('SUBCONSCIOUS_E2E') == '1'

pytestmark = pytest.mark.skipif(not E2E, reason='set SUBCONSCIOUS_E2E=1 to run')

FIXTURE = Path(__file__).parent.parent / 'fixtures' / 'mm-1x1.png'


def test_image_from_path_roundtrips_against_dev_api():
    client = Subconscious()
    run = client.run(
        engine='tim-claude',
        input={
            'instructions': 'What do you see?',
            'content': [Image.from_path(FIXTURE)],
        },
        options={'await_completion': True},
    )
    assert run.run_id


def test_densify_trace_produces_jsonl():
    client = Subconscious()
    # Create a run first so we have something to densify.
    run = client.run(
        engine='tim-claude',
        input={'instructions': 'Hi'},
        options={'await_completion': True},
    )
    out = io.StringIO()
    densify_trace(client, run.run_id, output=out)
    text = out.getvalue()
    # Each line should be valid JSON.
    for line in text.splitlines():
        if line.strip():
            json.loads(line)
