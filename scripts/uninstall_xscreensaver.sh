#!/usr/bin/env bash
set -euo pipefail

TARGET_BIN="${HOME}/.local/bin/east-frisia-castaway"
XS_FILE="${HOME}/.xscreensaver"
ENTRY='"East Frisia Castaway"  east-frisia-castaway --window-id %w'

if [[ -f "${TARGET_BIN}" ]]; then
  rm -f "${TARGET_BIN}"
  echo "Removed ${TARGET_BIN}."
else
  echo "No installed wrapper found at ${TARGET_BIN}."
fi

if [[ -f "${XS_FILE}" ]]; then
  TMP_XS="$(mktemp)"
  awk -v entry="${ENTRY}" '$0 !~ entry { print $0 }' "${XS_FILE}" > "${TMP_XS}"
  mv "${TMP_XS}" "${XS_FILE}"
  echo "Removed XScreenSaver entry from ${XS_FILE} (if present)."
else
  echo "No ${XS_FILE} found; skipped entry cleanup."
fi

echo "Uninstall complete."
