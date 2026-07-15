#!/usr/bin/env bash
# Generates a self-signed cert for internal-only TLS termination at Traefik.
# Swap for an internal-CA-issued cert once one is available (see
# docs/infrastructure-setup-plan.md, "Networking & Access").
set -euo pipefail

DOMAIN="${1:-cmms.internal.local}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "${DIR}/cmms.key" \
  -out "${DIR}/cmms.crt" \
  -days 825 \
  -subj "/CN=${DOMAIN}" \
  -addext "subjectAltName=DNS:${DOMAIN}"

echo "Generated self-signed cert for ${DOMAIN} in ${DIR}"
