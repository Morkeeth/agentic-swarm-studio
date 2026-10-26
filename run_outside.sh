#!/bin/sh
set -eu

cd "$(dirname "$0")"

: "${TOKEN_FACTORY_MODEL:?Set TOKEN_FACTORY_MODEL to the exact NVIDIA Nemotron model ID}"
if [ -z "${TOKEN_FACTORY_API_KEY:-${NEBIUS_API_KEY:-}}" ] && [ ! -s "${HOME}/.config/keys/tokenfactory.key" ]; then
  echo "Configure the existing Token Factory key; no request was made." >&2
  exit 2
fi
if [ "${CONFIRM_OUTSIDE_REHEARSAL:-}" != "RUN" ]; then
  echo "Set CONFIRM_OUTSIDE_REHEARSAL=RUN to authorize nine bounded Token Factory calls." >&2
  exit 2
fi

for command in git rg jq; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Missing required tool: $command" >&2
    exit 2
  }
done

PYTHONPATH=. python3 -m sim.outside_rehearsal --output web/landing/outside-run.json
PYTHONPATH=. python3 -m json.tool web/landing/outside-run.json >/dev/null
echo "Fresh outside rehearsal written to web/landing/outside-run.json"
