#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${HOME}/.local/bin"
TARGET_BIN="${TARGET_DIR}/east-frisia-castaway"
XS_FILE="${HOME}/.xscreensaver"
ENTRY='"East Frisia Castaway"  east-frisia-castaway --window-id %w'

run_cmd() {
  if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

if [[ ! -f "${XS_FILE}" ]]; then
  echo "Could not find ${XS_FILE}." >&2
  echo "Open xscreensaver-demo (or xscreensaver-settings) once to generate it, then rerun this installer." >&2
  exit 1
fi

run_cmd mkdir -p "${TARGET_DIR}"

TMP_WRAPPER="$(mktemp)"
sed "s|__CASTAWAY_REPO_DIR__|${REPO_DIR}|g" "${SCRIPT_DIR}/east-frisia-castaway" > "${TMP_WRAPPER}"
run_cmd install -m 0755 "${TMP_WRAPPER}" "${TARGET_BIN}"
rm -f "${TMP_WRAPPER}"

if grep -Fq "${ENTRY}" "${XS_FILE}"; then
  echo "XScreenSaver entry already present."
else
  TMP_XS="$(mktemp)"
  awk -v entry="${ENTRY}" '
    BEGIN { inserted = 0 }
    {
      print $0
      if (!inserted && $0 ~ /^programs:/) {
        print "\t" entry " \\"
        inserted = 1
      }
    }
    END {
      if (!inserted) {
        exit 2
      }
    }
  ' "${XS_FILE}" > "${TMP_XS}" || {
    rm -f "${TMP_XS}"
    echo "Could not find a programs: section in ${XS_FILE}." >&2
    exit 1
  }
  run_cmd mv "${TMP_XS}" "${XS_FILE}"
  [[ ${DRY_RUN} -eq 1 ]] && rm -f "${TMP_XS}" || true
  echo "Added XScreenSaver entry to ${XS_FILE}."
fi

echo "Install complete."
echo "Launch command: east-frisia-castaway --window-id %w"
