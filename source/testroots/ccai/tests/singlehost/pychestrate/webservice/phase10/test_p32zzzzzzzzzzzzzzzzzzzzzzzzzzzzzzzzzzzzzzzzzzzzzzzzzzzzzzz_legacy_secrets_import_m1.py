"""
.. module:: test_legacy_secrets_import_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The legacy secrets say what they are and can be carried into the vault (audit ADM-07).

.. moduleauthor:: Code Craft AI LLC

Admin, Secrets (legacy) and Admin, Secret Scopes write an older store that nothing in the product reads; the vault is where secrets belong
(``specs/model-convergence.md`` section 9). The legacy pages now say so, and an administrator can import what is in the older store into the vault: each secret
is decrypted with the legacy key and stored service-wide as ``<scope>/<name>`` through the vault's own service. A name the vault already holds is left as it is, a secret
that cannot be decrypted is reported by name, no value is shown, and the legacy rows stay.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Any, Dict, Tuple

from ccai import testbase

from ccai.pychestrate.core.orm import Secret, SecretScope
from ccai.pychestrate.webservice.secrets import secrets_service
from ccai.pychestrate.webservice.secrets.exceptions import SecretNotFoundError
from ccai.pychestrate.webservice.secrets.models import SecretRecord, SecretScopeKind
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import build_default_aspects

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    SeededAdmin,
    ensure_seeded_admin,
    ensure_seeded_viewer,
    grant_role_to_user,
    login_as,
)


def _text(html: str) -> str:
    from html import unescape

    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _legacy_secret(cookies: Dict[str, str], scope: str, name: str, value: str) -> int:
    """A scope and a secret made on the legacy pages (the only way they were ever made); returns the scope id."""
    adm.post_form(path="/admin/scopes/create", cookies=cookies, fields={"name": scope, "description": "legacy"})
    session = adm.open_db_session()
    try:
        scope_id = int(session.query(SecretScope).filter(SecretScope.name == scope).first().id)
    finally:
        session.close()
    response = adm.post_form(path="/admin/secrets/create", cookies=cookies, fields={"scope_id": scope_id, "name": name, "secret_type": "generic", "value": value, "description": "d"})
    testbase.assert_equal(response.status_code, 303)
    return scope_id


def _vault_value(session: Any, ref: str) -> str:
    read = secrets_service.read_secret_for_service(db_session=session, secret_ref=ref, service_identity="test")
    try:
        return read.plaintext.reveal().decode("utf-8")
    finally:
        read.plaintext.close()


def _follow(response: Any, cookies: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    jar = adm.merge_cookies(cookies=cookies, response=response)
    page = adm.get(path=response.header("Location") or "/admin/secrets", cookies=jar)
    return _text(page.text), adm.merge_cookies(cookies=jar, response=page)


def test_the_legacy_pages_say_nothing_reads_them_and_point_at_the_vault():
    """
    **Feature: legacy secrets (ADM-07)**
    **Property: the legacy secrets and scopes pages are titled "(legacy)", carry a notice that nothing reads them and where secrets belong, the secrets list offers
    the import (with the count) to an administrator, and the Admin menu entry for the scopes says legacy too.**
    """
    from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import NAV_ENTRIES

    cookies = adm.admin_cookies()
    _legacy_secret(cookies, adm.unique_name(prefix="legacy-scope"), adm.unique_name(prefix="s"), "v-1")
    secrets = _text(adm.get(path="/admin/secrets", cookies=cookies).text)
    scopes = _text(adm.get(path="/admin/scopes", cookies=cookies).text)
    create = _text(adm.get(path="/admin/secrets/create", cookies=cookies).text)
    labels = {entry.entry_id: entry.label for entry in NAV_ENTRIES if entry.entry_id in ("admin.scopes", "admin.secrets")}

    testbase.assert_equal(
        (
            "Secrets (legacy)" in secrets, "Nothing in Pychestrate reads them" in secrets, "System, Secrets" in secrets, re.search(r"Import \d+ secrets? into the vault", secrets) is not None,
            "Secret Scopes (legacy)" in scopes, "legacy secret scopes" in scopes, "import" in scopes.lower() and "into the vault" in scopes,
            "legacy secrets" in create, labels,
        ),
        (True, True, True, True, True, True, False, True, {"admin.scopes": "Secret Scopes (legacy)", "admin.secrets": "Secrets (legacy)"}),
    )
    return


def test_the_import_stores_each_legacy_secret_in_the_vault_and_never_shows_a_value():
    """
    **Feature: legacy secrets (ADM-07)**
    **Property: the import stores each legacy secret service-wide in the vault under ``<scope>/<name>`` with its real value, says how many were imported, leaves the legacy
    rows, writes the vault's own audit records, and no page, flash or audit payload holds a value; a second import skips what is there and a name the vault already holds
    is neither overwritten nor reported as an error.**
    """
    cookies = adm.admin_cookies()
    scope = adm.unique_name(prefix="imp-scope")
    name, other = adm.unique_name(prefix="tok"), adm.unique_name(prefix="pre")
    canary, existing_canary = "canary-{}".format(uuid.uuid4().hex), "vault-already-{}".format(uuid.uuid4().hex)
    scope_id = _legacy_secret(cookies, scope, name, canary)
    adm.post_form(path="/admin/secrets/create", cookies=cookies, fields={"scope_id": scope_id, "name": other, "secret_type": "generic", "value": "legacy-pre-value", "description": ""})
    session = adm.open_db_session()
    try:
        secrets_service.put_secret(
            db_session=session, principal=_principal(), secret_ref="{}/{}".format(scope, other), plaintext=SecretBytes(existing_canary.encode()), aspects=build_default_aspects(),
            scope_kind=SecretScopeKind.ORG, scope_ref=None,
        )
    finally:
        session.close()

    since = adm.latest_audit_sequence()
    first = adm.post_form(path="/admin/secrets/import", cookies=cookies, fields={})
    flash_one, cookies = _follow(first, cookies)
    second = adm.post_form(path="/admin/secrets/import", cookies=cookies, fields={})
    flash_two, cookies = _follow(second, cookies)

    session = adm.open_db_session()
    try:
        imported_value = _vault_value(session, "{}/{}".format(scope, name))
        untouched_value = _vault_value(session, "{}/{}".format(scope, other))
        record = session.query(SecretRecord).filter(SecretRecord.secret_ref == "{}/{}".format(scope, name)).first()
        legacy_left = session.query(Secret).filter(Secret.scope_id == scope_id, Secret.is_deleted == False).count()  # noqa: E712
    finally:
        session.close()
    audit = adm.audit_records_for(kind="audit.secret.created", since_sequence=since)
    audit_text = " ".join(str(r.payload_json) for r in audit)

    testbase.assert_equal(
        (
            "imported into the vault" in flash_one, "already there and left as they are" in flash_one, "already there" in flash_two,
            imported_value, untouched_value, record.scope_kind, legacy_left,
            "{}/{}".format(scope, name) in audit_text, canary in flash_one + flash_two + audit_text, existing_canary in flash_one + flash_two + audit_text,
        ),
        (True, True, True, canary, existing_canary, SecretScopeKind.ORG, 2, True, False, False),
    )
    return


def _principal() -> Any:
    from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
    from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal

    return AuthPrincipal(user_id=ensure_seeded_admin().user_id, session_id="", provider_kind=AuthProviderKind.LOCAL, provider_name="local")


def test_a_secret_that_cannot_be_decrypted_is_reported_by_name_and_the_others_still_import():
    """
    **Feature: legacy secrets (ADM-07)**
    **Property: a legacy secret whose stored value cannot be decrypted with the legacy key is named in the result with a reason that holds no value, stores nothing in the
    vault, and does not stop the others from importing.**
    """
    cookies = adm.admin_cookies()
    scope = adm.unique_name(prefix="bad-scope")
    good, bad = adm.unique_name(prefix="good"), adm.unique_name(prefix="bad")
    scope_id = _legacy_secret(cookies, scope, good, "fine-value")
    adm.post_form(path="/admin/secrets/create", cookies=cookies, fields={"scope_id": scope_id, "name": bad, "secret_type": "generic", "value": "broken-value", "description": ""})
    session = adm.open_db_session()
    try:
        row = session.query(Secret).filter(Secret.scope_id == scope_id, Secret.name == bad).first()
        row.encrypted_value = b"not-a-valid-ciphertext"
        session.commit()
    finally:
        session.close()
    flash, cookies = _follow(adm.post_form(path="/admin/secrets/import", cookies=cookies, fields={}), cookies)

    session = adm.open_db_session()
    try:
        good_in_vault = _vault_value(session, "{}/{}".format(scope, good))
        try:
            _vault_value(session, "{}/{}".format(scope, bad))
            bad_in_vault = True
        except SecretNotFoundError:
            bad_in_vault = False
    finally:
        session.close()

    testbase.assert_equal(
        ("{}/{}".format(scope, bad) in flash and "could not be decrypted with the legacy key" in flash, good_in_vault, bad_in_vault, "not-a-valid-ciphertext" in flash),
        (True, "fine-value", False, False),
    )
    return


def test_only_someone_who_may_administer_secrets_can_import():
    """
    **Feature: legacy secrets (ADM-07)**
    **Property: the import route needs ``system:secrets.admin`` (a signed-in user without it gets the 403 page and nothing is stored), and the button is not drawn for them.**
    """
    viewer = login_as(wsgi_app=adm.app(), user=ensure_seeded_viewer())
    response = adm.post_form(path="/admin/secrets/import", cookies=viewer, fields={})
    page = adm.get(path="/admin/secrets", cookies=viewer)

    testbase.assert_equal((response.status_code, "into the vault" in page.text and "import-legacy" in page.text), (403, False))
    return


def test_someone_who_may_read_secrets_but_not_administer_them_cannot_import():
    """
    **Feature: legacy secrets (ADM-07)**
    **Property: a user whose role holds system:secrets.read but not system:secrets.admin can open the legacy list (without the import button) and is refused the import
    with the 403 page, so the import needs the administrative permission and not merely the right to look.**
    """
    cookies = adm.admin_cookies()
    role = adm.unique_name(prefix="secrets-reader")
    adm.post_form(path="/admin/roles/create", cookies=cookies, fields=[("name", role), ("description", "reads secrets"), ("permission_keys", "system:secrets.read")])
    login, password = adm.unique_name(prefix="reader"), "Correct-Horse-Battery-9"
    adm.post_form(path="/admin/users/create", cookies=cookies, fields={
        "username": login, "email": "{}@example.com".format(login), "password_setup": "password", "password": password, "display_name": "Reader", "firstname": "R", "lastname": "R",
    })
    page = adm.get(path="/admin/users", cookies=cookies, query={"search": login}).text
    user_id = re.search(r'href="/admin/users/([0-9a-f-]{36})"[^>]*>\s*' + re.escape(login), page).group(1)
    grant_role_to_user(user_id=user_id, role_name=role)
    reader = login_as(wsgi_app=adm.app(), user=SeededAdmin(user_id=user_id, login=login, password=password))

    listing = adm.get(path="/admin/secrets", cookies=reader)
    refused = adm.post_form(path="/admin/secrets/import", cookies=reader, fields={})

    testbase.assert_equal((listing.status_code, "import-legacy" in listing.text, refused.status_code), (200, False, 403))
    return
