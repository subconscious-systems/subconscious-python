#!/usr/bin/env bash
# Regenerate Pydantic models under subconscious/_schemas/ from the monorepo's
# packages/schemas/src/*.json. Sources from the workspace root so this repo
# and the monorepo share a single source of truth.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# The workspace root holds both subconscious-python/ and subconscious-monorepo/.
WORKSPACE_ROOT="$(cd "$SDK_ROOT/.." && pwd)"
SCHEMA_ROOT="$WORKSPACE_ROOT/subconscious-monorepo/packages/schemas/src"

if [ ! -d "$SCHEMA_ROOT" ]; then
  echo "error: schemas not found at $SCHEMA_ROOT" >&2
  echo "hint: this script must run from the subconscious-workspace/ layout" >&2
  exit 1
fi

OUT_DIR="$SDK_ROOT/subconscious/_schemas"
mkdir -p "$OUT_DIR"

cd "$SDK_ROOT"

# Prefer `uv` if available; fall back to the local .venv's python.
if command -v uv >/dev/null 2>&1; then
  RUN=(uv run --with 'datamodel-code-generator>=0.25.0' datamodel-codegen)
elif [ -x .venv/bin/datamodel-codegen ]; then
  RUN=(.venv/bin/datamodel-codegen)
else
  RUN=(python -m datamodel_code_generator)
fi

# Target 3.10 for the codegen tool (it only supports 3.10+ in recent versions),
# but we deliberately omit --use-union-operator and --use-standard-collections so
# the emitted models use `Union[...]` / `Optional[...]` / `List[...]` and remain
# importable on Python >= 3.8 (the Python SDK's minimum supported runtime).
"${RUN[@]}" \
  --input "$SCHEMA_ROOT" \
  --input-file-type jsonschema \
  --output "$OUT_DIR" \
  --output-model-type pydantic_v2.BaseModel \
  --use-schema-description \
  --use-field-description \
  --enum-field-as-literal all \
  --use-annotated \
  --target-python-version 3.10

# Ensure __init__.py exists.
if [ ! -f "$OUT_DIR/__init__.py" ]; then
  : > "$OUT_DIR/__init__.py"
fi

echo "Generated schemas at $OUT_DIR"
