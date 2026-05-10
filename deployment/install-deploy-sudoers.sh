#!/usr/bin/env bash
#
# install-deploy-sudoers.sh -- one-shot installer for the
# scoped passwordless-sudo rule that
# ``deployment/deploy-alpha-to-host.sh`` needs.
#
# Renders the sudoers template (``@USER@`` -> the deploy
# user) locally, scp's it to /tmp on the remote, validates
# with ``visudo -c -f``, and -- only on validation success --
# installs it to ``/etc/sudoers.d/pychestrate-deploy`` with
# the correct ownership + mode.
#
# This is a ONE-TIME setup step.  After it lands, every
# subsequent ``deploy-alpha-to-host.sh`` run -- workstation
# first-deploy AND CI re-deploy -- is fully non-interactive.
#
# The rules in the rendered file scope passwordless sudo to
# ONLY the operations the deploy script performs.  Outside
# of those (other systemctl targets, package install, etc.)
# the deploy user still needs a password.
#
# Usage:
#
#   deployment/install-deploy-sudoers.sh \
#       [--host=tc-app-server.local] \
#       [--user=myron]
#
# You will be prompted for the remote sudo password ONCE
# during this install (to drop the rules file).  After the
# rules file is in place, no further prompts.

set -euo pipefail

REMOTE_HOST="tc-app-server.local"
REMOTE_USER="myron"

while [ $# -gt 0 ]; do
    case "$1" in
        --host=*) REMOTE_HOST="${1#*=}" ;;
        --user=*) REMOTE_USER="${1#*=}" ;;
        --help|-h)
            sed -n '2,/^set -euo/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

REMOTE_TARGET="${REMOTE_USER}@${REMOTE_HOST}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${REPO_ROOT}/deployment/sudoers.d/pychestrate-deploy.template"

if [ ! -f "${TEMPLATE}" ]; then
    echo "ERROR: ${TEMPLATE} is missing." >&2
    exit 2
fi

echo "================================================================"
echo "  Install scoped sudoers rule for ${REMOTE_USER}@${REMOTE_HOST}"
echo "================================================================"
echo
echo "Template:    ${TEMPLATE}"
echo "Target file: /etc/sudoers.d/pychestrate-deploy"
echo "Deploy user: ${REMOTE_USER}"
echo

# Pre-flight: SSH must work non-interactively.
if ! ssh -o ConnectTimeout=8 -o BatchMode=yes "${REMOTE_TARGET}" "true" 2>/dev/null; then
    echo "ERROR: cannot SSH non-interactively to ${REMOTE_TARGET}." >&2
    echo "       Make sure your SSH key is in ${REMOTE_TARGET}:~/.ssh/authorized_keys" >&2
    exit 3
fi

# Render locally with @USER@ substitution.
RENDERED="$(mktemp)"
sed -e "s|@USER@|${REMOTE_USER}|g" "${TEMPLATE}" > "${RENDERED}"

# Validate locally if visudo is available.  ``visudo -c -f``
# parses without modifying.  Some macs may not have visudo on
# PATH; skip silently if so -- the remote will validate.
if command -v visudo >/dev/null 2>&1; then
    if ! visudo -c -f "${RENDERED}" >/dev/null 2>&1; then
        echo "ERROR: rendered sudoers fails visudo -c locally." >&2
        echo "       Inspect ${RENDERED} for syntax issues." >&2
        exit 4
    fi
fi

# scp + remote install via a short script (so ssh -t can
# prompt cleanly for sudo).
INSTALL_LOCAL="$(mktemp)"
cat > "${INSTALL_LOCAL}" <<'INSTALL'
#!/usr/bin/env bash
set -euo pipefail

SUDOERS_TARGET="/etc/sudoers.d/pychestrate-deploy"
SUDOERS_TMP="/tmp/pychestrate-deploy.sudoers"

# Validate before installing.  Refuses to write a malformed
# sudoers file; sudo would then refuse to load /etc/sudoers.d
# at all and your operator account could be locked out.
sudo visudo -c -f "${SUDOERS_TMP}"

sudo install -m 0440 -o root -g root "${SUDOERS_TMP}" "${SUDOERS_TARGET}"
sudo rm -f "${SUDOERS_TMP}"

echo "    installed at ${SUDOERS_TARGET}"
echo
echo "    verify:"
sudo cat "${SUDOERS_TARGET}" | grep -E "^[a-zA-Z]" | head -5 | sed 's/^/    /'
INSTALL

scp -q "${RENDERED}"      "${REMOTE_TARGET}:/tmp/pychestrate-deploy.sudoers"
scp -q "${INSTALL_LOCAL}" "${REMOTE_TARGET}:/tmp/pychestrate-deploy.sudoers.install.sh"
rm -f "${RENDERED}" "${INSTALL_LOCAL}"

echo "==> Installing on remote (you'll be prompted for sudo password ONCE)"
ssh -t "${REMOTE_TARGET}" "bash /tmp/pychestrate-deploy.sudoers.install.sh && rm -f /tmp/pychestrate-deploy.sudoers.install.sh"

echo
echo "================================================================"
echo "  Done"
echo "================================================================"
echo
echo "Verify by re-running the deploy with no password prompts:"
echo
echo "    ./deployment/deploy-alpha-to-host.sh"
echo
echo "If you ever want to remove this rule:"
echo
echo "    ssh ${REMOTE_TARGET} sudo rm /etc/sudoers.d/pychestrate-deploy"
echo
