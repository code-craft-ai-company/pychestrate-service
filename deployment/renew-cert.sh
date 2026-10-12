#!/usr/bin/env bash
#
# renew-cert.sh -- workstation-driven renewal of the tailnet
# HTTPS certificate the nginx front terminates with.
#
# Tailscale-issued certs are valid for 90 days; when one lapses
# the :80 -> https redirect makes the whole site unreachable for
# browsers, so renewal is operationally load-bearing.  This
# script drives the renewal end-to-end over SSH with the SCOPED
# passwordless-sudo rules from
# ``deployment/sudoers.d/pychestrate-deploy.template`` (installed
# once via ``deployment/install-deploy-sudoers.sh``):
#
#   1. ``sudo tailscale cert`` mints a fresh cert pair for the
#      canonical public hostname into /tmp on the host.
#   2. Scoped ``install`` calls place the pair under
#      /etc/nginx/ssl/ (key 0640 root:www-data so the nginx
#      workers can read it).
#   3. ``nginx -t`` validates, ``systemctl reload nginx`` picks
#      the new cert up with zero downtime, and the root-owned
#      /tmp staging files are removed.
#   4. The new expiry is read back and printed, and the live
#      endpoint is probed from the workstation.
#
# Every privileged call uses ``sudo -n`` so a missing sudoers
# rule fails loudly with a pointer at the installer instead of
# hanging on a password prompt.
#
# Usage:
#
#   deployment/renew-cert.sh \
#       --host=HOST --user=USER --public-hostname=PUBLIC_HOSTNAME
#
# All three are required (there is no built-in default host):
#   HOST             how you reach the machine over SSH
#   USER             the deploy account on it
#   PUBLIC_HOSTNAME  the name on the TLS certificate (the tailnet name)
#
# ``--flag=value`` and ``--flag value`` both work.
#
# Renewal is idempotent -- re-running replaces the cert with a
# freshly minted one.  Suitable for a cron/systemd-timer on the
# workstation or the host itself (run monthly; well inside the
# 90-day validity).

set -euo pipefail

# No host-specific defaults: the flags name the target.
REMOTE_HOST=""
REMOTE_USER=""
PUBLIC_HOSTNAME=""

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
        --public-hostname=*) PUBLIC_HOSTNAME="${1#*=}" ;;
        --public-hostname) [ $# -gt 1 ] || usage_error "--public-hostname needs a value"; PUBLIC_HOSTNAME="$2"; shift ;;
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

if [ -z "${REMOTE_HOST}" ] || [ -z "${REMOTE_USER}" ] || [ -z "${PUBLIC_HOSTNAME}" ]; then
    usage_error "--host, --user and --public-hostname are required (for example --host app-server --user deploy --public-hostname app-server.example.ts.net)"
fi

REMOTE_TARGET="${REMOTE_USER}@${REMOTE_HOST}"

echo "================================================================"
echo "  Renew TLS cert for ${PUBLIC_HOSTNAME} on ${REMOTE_TARGET}"
echo "================================================================"

# Pre-flight: SSH must work non-interactively.
if ! ssh -o ConnectTimeout=8 -o BatchMode=yes "${REMOTE_TARGET}" "true" 2>/dev/null; then
    echo "ERROR: cannot SSH non-interactively to ${REMOTE_TARGET}." >&2
    exit 2
fi

# Pre-flight: the scoped sudoers rules must be in place.  Probe
# with the cheapest rule (the expiry read-back) so a stale
# sudoers install fails here with a clear pointer, not mid-renew.
if ! ssh -o BatchMode=yes "${REMOTE_TARGET}" \
        "sudo -n /usr/bin/openssl x509 -in /etc/nginx/ssl/pychestrate.crt -noout -subject -enddate" \
        >/dev/null 2>&1; then
    echo "ERROR: scoped sudo rules for cert renewal are missing on ${REMOTE_HOST}." >&2
    echo "       Install them once with:" >&2
    echo "           deployment/install-deploy-sudoers.sh --host=${REMOTE_HOST} --user=${REMOTE_USER} --public-hostname=${PUBLIC_HOSTNAME}" >&2
    echo "       (prompts for the remote sudo password one time)" >&2
    exit 3
fi

echo
echo "==> Current cert:"
ssh -o BatchMode=yes "${REMOTE_TARGET}" \
    "sudo -n /usr/bin/openssl x509 -in /etc/nginx/ssl/pychestrate.crt -noout -subject -enddate" \
    | sed 's/^/    /'

echo
echo "==> Minting fresh cert via tailscale + installing + reloading nginx"
ssh -o BatchMode=yes "${REMOTE_TARGET}" bash -s <<REMOTE_SCRIPT
set -euo pipefail
sudo -n /usr/bin/tailscale cert --cert-file /tmp/pychestrate.crt --key-file /tmp/pychestrate.key ${PUBLIC_HOSTNAME}
sudo -n /usr/bin/install -m 0644 -o root -g root /tmp/pychestrate.crt /etc/nginx/ssl/pychestrate.crt
sudo -n /usr/bin/install -m 0640 -o root -g www-data /tmp/pychestrate.key /etc/nginx/ssl/pychestrate.key
sudo -n /usr/sbin/nginx -t
sudo -n /usr/bin/systemctl reload nginx
sudo -n /usr/bin/rm -f /tmp/pychestrate.crt /tmp/pychestrate.key
REMOTE_SCRIPT

echo
echo "==> Renewed cert:"
ssh -o BatchMode=yes "${REMOTE_TARGET}" \
    "sudo -n /usr/bin/openssl x509 -in /etc/nginx/ssl/pychestrate.crt -noout -subject -enddate" \
    | sed 's/^/    /'

echo
echo "==> Probing https://${PUBLIC_HOSTNAME}/ from the workstation"
if probe_dates="$(echo \
        | openssl s_client -connect "${PUBLIC_HOSTNAME}:443" \
            -servername "${PUBLIC_HOSTNAME}" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null)"; then
    echo "    live endpoint serves: ${probe_dates}"
else
    echo "    WARNING: could not probe ${PUBLIC_HOSTNAME}:443 from here" >&2
    echo "             (tailnet routing?) -- verify in a browser." >&2
fi

echo
echo "================================================================"
echo "  RENEWAL COMPLETE"
echo "================================================================"
