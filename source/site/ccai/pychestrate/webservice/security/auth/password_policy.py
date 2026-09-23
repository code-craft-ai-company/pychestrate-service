"""
.. module:: security.auth.password_policy
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The one password policy every path that sets a local
               password enforces.

.. moduleauthor:: Code Craft AI LLC

The admin "Create user" form promised "Minimum 12 characters with
uppercase, lowercase, digit, and special character" while the server
only checked the length, so ``aaaaaaaaaaaa`` was accepted. The setup
wizard checked the length alone as well. This module is the single
source of the rules, their user-facing wording, and the browser-side
hint, so the text a form shows and the check the server runs cannot
drift apart again.

The rules:

* at least :data:`MIN_PASSWORD_LENGTH` and at most
  :data:`MAX_PASSWORD_LENGTH` characters;
* at least one lowercase letter, one uppercase letter, one digit and
  one symbol (any character that is not a letter or a digit);
* it must not contain the account's login name or the local part of
  its email address;
* it must not be a commonly used password such as ``Password123!`` or
  ``Welcome2026!`` (see :data:`_COMMON_PASSWORD_WORDS`). This is a
  built-in list, not a breached-password corpus: the service runs
  offline and never sends password material anywhere.

Every path that sets a password -- admin create, admin reset, the
self-service change, invite / reset links, and the first-run setup
wizard -- calls :func:`check_password_against_policy` (or
:func:`enforce_password_policy`).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import FrozenSet, List, Optional, Tuple


MIN_PASSWORD_LENGTH: int = 12

#: Upper bound keeps hashing cost bounded; generous enough for
#: generated passphrases and password-manager output.
MAX_PASSWORD_LENGTH: int = 256

#: One-sentence summary shown under password fields.
PASSWORD_POLICY_SUMMARY: str = (
    "Use at least {} characters, with an uppercase letter, a lowercase "
    "letter, a digit, and a symbol. Don't use your username or a "
    "commonly used password."
).format(MIN_PASSWORD_LENGTH)

#: The rules as a checklist, keyed by the identifier the browser-side
#: hint uses (see ``config/_password_rules.html``).
PASSWORD_POLICY_RULES: Tuple[Tuple[str, str], ...] = (
    ("length", "At least {} characters".format(MIN_PASSWORD_LENGTH)),
    ("upper", "An uppercase letter"),
    ("lower", "A lowercase letter"),
    ("digit", "A digit"),
    ("symbol", "A symbol, such as ! # or -"),
)

#: ``pattern`` attribute for password inputs. Browsers compile it with
#: the ``v`` flag, so it uses Unicode property escapes (valid under
#: ``v``) rather than raw ASCII ranges; the server check stays the
#: authority.
PASSWORD_HTML_PATTERN: str = (
    r"(?=.*\p{Ll})(?=.*\p{Lu})(?=.*\p{Nd})(?=.*[^\p{L}\p{N}]).{"
    + str(MIN_PASSWORD_LENGTH) + "," + str(MAX_PASSWORD_LENGTH) + "}"
)

#: ``title`` attribute paired with :data:`PASSWORD_HTML_PATTERN`; the
#: browser shows it when the pattern does not match.
PASSWORD_HTML_TITLE: str = (
    "At least {} characters with an uppercase letter, a lowercase "
    "letter, a digit, and a symbol"
).format(MIN_PASSWORD_LENGTH)


# Common password stems. A candidate is refused when, after trimming
# the leading / trailing digits and symbols people pad passwords with
# and undoing common letter substitutions (``P@ssw0rd``), what remains
# is one of these words.
_COMMON_PASSWORD_WORDS: FrozenSet[str] = frozenset((
    "abc", "abcd", "abcde", "abcdef", "abcdefg", "abcdefgh",
    "access", "admin", "administrator", "asdf", "asdfgh", "azerty",
    "baseball", "batman", "changeme", "charlie", "codecraft",
    "default", "dragon", "football", "freedom", "hello", "iloveyou",
    "letmein", "login", "master", "monkey", "mustang", "passw",
    "passwd", "password", "passwort", "pychestrate", "qazwsx",
    "qwerty", "qwertyuiop", "secret", "shadow", "starwars",
    "summer", "sunshine", "superman", "test", "tester", "testing",
    "trustno", "welcome", "whatever", "winter", "spring", "autumn",
    "zaq", "zxcvbn", "zxcvbnm", "princess", "michael", "jordan",
))

_LEET_SUBSTITUTIONS = {
    "@": "a",
    "4": "a",
    "8": "b",
    "3": "e",
    "1": "i",
    "!": "i",
    "0": "o",
    "$": "s",
    "5": "s",
    "7": "t",
    "+": "t",
}


class PasswordPolicyError(ValueError):
    """
        Raised by :func:`enforce_password_policy` when a candidate
        password breaks one or more rules. ``problems`` carries one
        user-facing sentence per broken rule.
    """

    def __init__(self, problems: List[str]) -> None:
        """
            :param problems: User-facing sentences, one per broken
                             rule.
        """
        self.problems: List[str] = list(problems)
        err_msg = describe_password_problems(problems=self.problems)
        super().__init__(err_msg)
        return


def _strip_padding(*, text: str) -> str:
    """
        Remove the leading and trailing run of non-letters (the
        ``2026!`` people pad a word with).

        :param text: Candidate text.

        :returns: The text without its leading / trailing non-letter
                  runs.
    """
    start = 0
    end = len(text)
    while start < end and text[start].isalpha() is False:
        start = start + 1
    while end > start and text[end - 1].isalpha() is False:
        end = end - 1
    rtnval = text[start:end]
    return rtnval


def _common_word_stem(*, password: str) -> str:
    """
        Reduce a password to the stem compared against
        :data:`_COMMON_PASSWORD_WORDS`: case-folded, padding trimmed,
        common letter substitutions undone, non-letters dropped.

        :param password: Candidate password.

        :returns: The stem (may be empty).
    """
    lowered = password.casefold()
    trimmed = _strip_padding(text=lowered)
    translated_chars: List[str] = []
    for character in trimmed:
        translated = _LEET_SUBSTITUTIONS.get(character, character)
        if translated.isalpha() is True:
            translated_chars.append(translated)
    rtnval = "".join(translated_chars)
    return rtnval


def is_common_password(*, password: str) -> bool:
    """
        Whether ``password`` is a padded / substituted form of a
        commonly used password (``Password123!``, ``P@ssw0rd2026``,
        ``Welcome!!2026``).

        :param password: Candidate password.

        :returns: ``True`` when the password is too common.
    """
    stem = _common_word_stem(password=password)
    if len(stem) == 0:
        return False
    rtnval = stem in _COMMON_PASSWORD_WORDS
    return rtnval


def _email_local_part(*, email: Optional[str]) -> str:
    """
        Return the part of an email address before ``@`` (empty when
        there is none).

        :param email: Email address or None.

        :returns: The local part, case-folded.
    """
    if email is None:
        return ""
    text = str(email).strip()
    if "@" not in text:
        return ""
    rtnval = text.split("@", 1)[0].casefold()
    return rtnval


def check_password_against_policy(
        *,
        password: Optional[str],
        login_name: Optional[str] = None,
        email: Optional[str] = None
    ) -> List[str]:
    """
        Check a candidate password against every rule.

        :param password: The candidate password (plaintext).
        :param login_name: The account's login name, when known; a
                           password containing it is refused.
        :param email: The account's email address, when known; a
                      password containing its local part is refused.

        :returns: One user-facing sentence per broken rule (empty when
                  the password is acceptable).
    """
    if password is None:
        password = ""

    problems: List[str] = []

    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(
            "Password must be at least {} characters long.".format(
                MIN_PASSWORD_LENGTH
            )
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(
            "Password must be at most {} characters long.".format(
                MAX_PASSWORD_LENGTH
            )
        )

    has_lower = False
    has_upper = False
    has_digit = False
    has_symbol = False
    for character in password:
        if character.islower() is True:
            has_lower = True
        elif character.isupper() is True:
            has_upper = True
        elif character.isdigit() is True:
            has_digit = True
        elif character.isalnum() is False:
            has_symbol = True

    if has_upper is False:
        problems.append("Password must contain an uppercase letter.")
    if has_lower is False:
        problems.append("Password must contain a lowercase letter.")
    if has_digit is False:
        problems.append("Password must contain a digit.")
    if has_symbol is False:
        problems.append(
            "Password must contain a symbol, such as ! # or -."
        )

    folded_password = password.casefold()
    if login_name is not None:
        folded_login = str(login_name).strip().casefold()
        if len(folded_login) >= 3 and folded_login in folded_password:
            problems.append("Password must not contain the username.")

    local_part = _email_local_part(email=email)
    if len(local_part) >= 3 and local_part in folded_password:
        problems.append(
            "Password must not contain the email address."
        )

    if len(password) > 0 and is_common_password(password=password) is True:
        problems.append(
            "Password is too common. Choose something less predictable."
        )

    rtnval = problems
    return rtnval


def describe_password_problems(*, problems: List[str]) -> str:
    """
        Join the problem sentences into one message.

        :param problems: Sentences from
                         :func:`check_password_against_policy`.

        :returns: One message (empty when there are no problems).
    """
    rtnval = " ".join(problems)
    return rtnval


def enforce_password_policy(
        *,
        password: Optional[str],
        login_name: Optional[str] = None,
        email: Optional[str] = None
    ) -> None:
    """
        Raise :class:`PasswordPolicyError` unless ``password``
        satisfies every rule.

        :param password: The candidate password (plaintext).
        :param login_name: The account's login name, when known.
        :param email: The account's email address, when known.

        :returns: None.
        :raises: PasswordPolicyError
    """
    problems = check_password_against_policy(
        password=password, login_name=login_name, email=email
    )
    if len(problems) > 0:
        raise PasswordPolicyError(problems) from None
    return


def password_policy_template_context() -> dict:
    """
        The template variables every password form renders its hint
        from (``config/_password_rules.html`` reads them).

        :returns: Dict with ``password_rules``, ``password_summary``,
                  ``password_pattern``, ``password_title``,
                  ``password_min_length`` and ``password_max_length``.
    """
    rtnval = {
        "password_rules": [
            {"key": key, "label": label}
            for key, label in PASSWORD_POLICY_RULES
        ],
        "password_summary": PASSWORD_POLICY_SUMMARY,
        "password_pattern": PASSWORD_HTML_PATTERN,
        "password_title": PASSWORD_HTML_TITLE,
        "password_min_length": MIN_PASSWORD_LENGTH,
        "password_max_length": MAX_PASSWORD_LENGTH,
    }
    return rtnval


__all__ = [
    "MAX_PASSWORD_LENGTH",
    "MIN_PASSWORD_LENGTH",
    "PASSWORD_HTML_PATTERN",
    "PASSWORD_HTML_TITLE",
    "PASSWORD_POLICY_RULES",
    "PASSWORD_POLICY_SUMMARY",
    "PasswordPolicyError",
    "check_password_against_policy",
    "describe_password_problems",
    "enforce_password_policy",
    "is_common_password",
    "password_policy_template_context",
]
