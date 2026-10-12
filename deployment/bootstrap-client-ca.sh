#!/usr/bin/env bash
#
# bootstrap-client-ca.sh -- one-shot installer for the
# self-signed client-CA bundle that nginx uses to verify
# incoming client certificates for the mTLS-gated
# orchestration-ingest endpoints.
#
# Generates a self-signed root CA on the remote (via
# ``openssl req``) at:
#
#   /etc/nginx/ssl/client-ca.crt   (mode 0644 root)
#   /etc/nginx/ssl/client-ca.key   (mode 0600 root)
#
# ...if -- and ONLY if -- one does not already exist.  The
# script is idempotent: a second invocation against a host that
# already has the CA in place is a clean no-op, never
# regenerating (which would invalidate previously-issued client
# certs).
#
# After the CA is in place, operators issue client certs
# against it with a separate ``openssl x509 -req`` flow -- see
# ``deployment/README.md`` for the operator command.
#
# Usage:
#
#   deployment/bootstrap-client-ca.sh \
#       --host=HOST --user=USER \
#       [--ca-subject="/CN=pychestrate-client-ca"] \
#       [--days=3650]
#
# ``--host`` and ``--user`` are required (there is no built-in default
# host); ``--flag=value`` and ``--flag value`` both work.
#
# This is a ONE-TIME setup step.  After it lands, every
# subsequent ``deploy-alpha-to-host.sh`` run picks up the CA
# and renders nginx config that points nginx at it.
#
# You will be prompted for the remote sudo password ONCE
# during this install (to drop the CA files into
# ``/etc/nginx/ssl/``).  After the rules file is in place,
# no further prompts on subsequent deploys.

set -euo pipefail

# No host-specific defaults: the flags name the target.
REMOTE_HOST=""
REMOTE_USER=""
CA_SUBJECT="/CN=pychestrate-client-ca"
CA_DAYS="3650"

usage_error() {
    echo "ERROR: $1" >&2
    echo "       Run with --help for usage." >&2
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --host=*) REMOTE_HOST="${1#*=}" ;;
        --host) [ $# -gt 1 ] || usage_error "--host needs a value"; REMOTE_HOST="$2"; shift ;;
        --user=*) REMOTE_USER="${1#*=}" ;;
        --user) [ $# -gt 1 ] || usage_error "--user needs a value"; REMOTE_USER="$2"; shift ;;
        --ca-subject=*) CA_SUBJECT="${1#*=}" ;;
        --ca-subject) [ $# -gt 1 ] || usage_error "--ca-subject needs a value"; CA_SUBJECT="$2"; shift ;;
        --days=*) CA_DAYS="${1#*=}" ;;
        --days) [ $# -gt 1 ] || usage_error "--days needs a value"; CA_DAYS="$2"; shift ;;
        --help|-h)
            sed -n '2,/^set -euo/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            usage_error "Unknown argument: $1"
            ;;
    esac
    shift
done

if [ -z "${REMOTE_HOST}" ] || [ -z "${REMOTE_USER}" ]; then
    usage_error "--host and --user are required (for example --host app-server --user deploy)"
fi

REMOTE_TARGET="${REMOTE_USER}@${REMOTE_HOST}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "================================================================"
echo "  Bootstrap client-CA bundle on ${REMOTE_TARGET}"
echo "================================================================"
echo
echo "  CA cert  : /etc/nginx/ssl/client-ca.crt"
echo "  CA key   : /etc/nginx/ssl/client-ca.key"
echo "  Subject  : ${CA_SUBJECT}"
echo "  Validity : ${CA_DAYS} days"
echo

# Pre-flight: SSH must work non-interactively.
if ! ssh -o ConnectTimeout=8 -o BatchMode=yes "${REMOTE_TARGET}" "true" 2>/dev/null; then
    echo "ERROR: cannot SSH non-interactively to ${REMOTE_TARGET}." >&2
    exit 3
fi

# Render a remote-side install script (so ssh -t can prompt
# cleanly for sudo).  The script:
#
# * Is idempotent: bails out if the CA cert already exists.
# * Uses ``openssl req -x509`` to mint a self-signed root CA
#   in /tmp first, then sudo-installs both files into
#   /etc/nginx/ssl/ with the correct ownership + mode.
INSTALL_LOCAL="$(mktemp)"
cat > "${INSTALL_LOCAL}" <<INSTALL
#!/usr/bin/env bash
set -euo pipefail

CA_CRT_TARGET="/etc/nginx/ssl/client-ca.crt"
CA_KEY_TARGET="/etc/nginx/ssl/client-ca.key"

CA_CRT_TMP="/tmp/pychestrate-client-ca.crt"
CA_KEY_TMP="/tmp/pychestrate-client-ca.key"

# Idempotency: if BOTH files exist already, do nothing.
# We never regenerate -- that would invalidate every client
# cert previously issued against the existing root.
if sudo test -f "\${CA_CRT_TARGET}" && sudo test -f "\${CA_KEY_TARGET}"; then
    echo "    client-CA already present at \${CA_CRT_TARGET}; leaving in place."
    echo
    echo "    fingerprint:"
    sudo openssl x509 -in "\${CA_CRT_TARGET}" -noout -fingerprint -sha256 \\
        | sed 's/^/    /'
    sudo openssl x509 -in "\${CA_CRT_TARGET}" -noout -subject -enddate \\
        | sed 's/^/    /'
    exit 0
fi

# Make sure openssl is installed.
if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl not found on the remote." >&2
    echo "       Install it (sudo apt-get install -y openssl) and re-run." >&2
    exit 4
fi

# Make sure the target directory exists.  ``/etc/nginx/ssl/``
# is created by the operator's TLS-cert setup; if missing,
# create it with 0755 root.
sudo mkdir -p /etc/nginx/ssl
sudo chmod 0755 /etc/nginx/ssl

# Mint a self-signed root CA in /tmp first.  ``-nodes`` so the
# private key is unencrypted (no passphrase prompt at nginx
# startup -- the file's 0600 root mode is the access control).
echo "    minting self-signed root CA (subject ${CA_SUBJECT}, ${CA_DAYS} days) ..."
umask 077
openssl req -x509 -newkey rsa:4096 -sha256 \\
    -keyout "\${CA_KEY_TMP}" \\
    -out    "\${CA_CRT_TMP}" \\
    -days   "${CA_DAYS}" \\
    -nodes \\
    -subj   "${CA_SUBJECT}" \\
    2>/dev/null
umask 022

# Install with the correct ownership + mode in a single
# privileged ``install`` call each (shrinks sudoers surface).
sudo install -m 0644 -o root -g root "\${CA_CRT_TMP}" "\${CA_CRT_TARGET}"
sudo install -m 0600 -o root -g root "\${CA_KEY_TMP}" "\${CA_KEY_TARGET}"

# Scrub the /tmp copies -- the key is sensitive.
shred -u "\${CA_KEY_TMP}" 2>/dev/null || rm -f "\${CA_KEY_TMP}"
rm -f "\${CA_CRT_TMP}"

echo "    installed:"
echo "      \${CA_CRT_TARGET}  (0644 root)"
echo "      \${CA_KEY_TARGET}  (0600 root)"
echo
echo "    fingerprint:"
sudo openssl x509 -in "\${CA_CRT_TARGET}" -noout -fingerprint -sha256 \\
    | sed 's/^/    /'
sudo openssl x509 -in "\${CA_CRT_TARGET}" -noout -subject -enddate \\
    | sed 's/^/    /'
INSTALL

scp -q "${INSTALL_LOCAL}" "${REMOTE_TARGET}:/tmp/pychestrate-client-ca.install.sh"
rm -f "${INSTALL_LOCAL}"

echo "==> Installing on remote (you'll be prompted for sudo password ONCE)"
ssh -t "${REMOTE_TARGET}" "bash /tmp/pychestrate-client-ca.install.sh && rm -f /tmp/pychestrate-client-ca.install.sh"

echo
echo "================================================================"
echo "  Done"
echo "================================================================"
echo
echo "Issue a client cert against this CA (run locally; copy the"
echo "resulting client.crt + client.key wherever the worker runs):"
echo
echo "    openssl req -new -newkey rsa:2048 -nodes \\"
echo "        -keyout client.key -out client.csr \\"
echo "        -subj /CN=worker-1"
echo
echo "    ssh ${REMOTE_TARGET} 'sudo openssl x509 -req \\"
echo "        -in /dev/stdin \\"
echo "        -CA /etc/nginx/ssl/client-ca.crt \\"
echo "        -CAkey /etc/nginx/ssl/client-ca.key \\"
echo "        -CAcreateserial \\"
echo "        -days 365 -sha256' < client.csr > client.crt"
echo
echo "Then re-run the deploy to apply the nginx mTLS config:"
echo
echo "    deployment/deploy-alpha-to-host.sh"
echo
