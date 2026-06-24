#!/usr/bin/env bash
#
# setup.sh — one-shot environment setup for "Build Your First AI Agent" (Linux/macOS).
#
# Creates a local .venv, installs requirements, registers a Jupyter kernel, and
# copies .env.example to .env if you don't have one yet.
#
#   ./setup.sh            # create .venv and install everything
#   source ./setup.sh     # do the above AND leave the venv activated in your shell
#
# Windows users: a virtualenv isn't required — just `pip install -r requirements.txt`
# with a system Python and run `jupyter lab`.

set -euo pipefail

# Resolve the repo root (directory of this script) so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
KERNEL_NAME="ai-agent"
KERNEL_LABEL="Python (Build Your First AI Agent)"

# Pick a Python interpreter (prefer python3).
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "ERROR: no python3/python found on PATH. Install Python 3.8+ first." >&2
    return 1 2>/dev/null || exit 1
fi

echo "==> Using $($PY --version) at $(command -v $PY)"

# 1. Create the virtual environment if it doesn't exist.
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating virtual environment in $VENV_DIR"
    "$PY" -m venv "$VENV_DIR"
else
    echo "==> Reusing existing virtual environment in $VENV_DIR"
fi

# 2. Activate it.
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 3. Install dependencies.
echo "==> Upgrading pip and installing requirements"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

# 4. Register a Jupyter kernel that points at this venv.
echo "==> Registering Jupyter kernel '$KERNEL_NAME'"
python -m ipykernel install --user --name "$KERNEL_NAME" --display-name "$KERNEL_LABEL"

# 5. Seed a .env from the template if the user doesn't have one.
if [ ! -f ".env" ]; then
    echo "==> No .env found — copying .env.example to .env (edit it with your provider + key)"
    cp .env.example .env
else
    echo "==> .env already exists — leaving it untouched"
fi

cat <<EOF

✅ Setup complete.

Next steps:
  1. Edit .env with your OPENAI_BASE_URL / OPENAI_API_KEY / MODEL.
  2. Start Jupyter:           jupyter lab
  3. In each notebook, pick the kernel: "$KERNEL_LABEL".

This script was run with: $0
If you ran it as './setup.sh', activate the venv in your shell with:
  source $VENV_DIR/bin/activate
(If you ran it as 'source ./setup.sh', the venv is already active.)
EOF
