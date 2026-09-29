=====================
The pyc Command Line
=====================

``pyc`` is the command line for Pychestrate. Every operation of the
REST API under ``/api/v1`` is a ``pyc <noun> <verb>`` command,
generated from the OpenAPI document the server publishes, so the CLI
always offers what the server it talks to offers. It is meant for
people at a terminal and for scripts and CI jobs alike: output is a
table on a terminal and JSON in a pipe, and every failure has its own
exit code.

``pyc`` uses only the Python standard library. It talks to the service
over HTTPS with an API token, like any other client; it never touches
the database.

Installing
==========

``pyc`` is packaged on its own as ``pychestrate-cli`` (Python 3.10 or
later, no dependencies). From a checkout of this repository::

    pipx install ./packages/pychestrate-cli

To hand it to people without a checkout, build a wheel once and share
the file::

    python3 -m pip wheel --no-deps -w dist ./packages/pychestrate-cli
    pipx install dist/pychestrate_cli-*.whl

In a development checkout, ``python -m ccai.pychestrate.cli.entry``
(with the ``PYTHONPATH`` from ``.env``) runs the working tree's CLI;
the service environment itself does not install a ``pyc`` command
(``development/setup-environment`` installs the dependencies only).

``pyc --version`` prints the CLI's version. ``pyc version`` also asks
the server and prints the service's version and the version of its
REST API::

    $ pyc version
    pyc      0.3.0 (python 3.12.14)
    server   https://pychestrate.example.com
    service  0.0.7-preview
    api      0.0.17-preview

Signing in
==========

``pyc`` authenticates with an **API token**. Create one in the web
interface under **Account > API tokens** (a read-only token is enough
for commands that only read), then::

    pyc login --server-url https://pychestrate.example.com

``pyc login`` asks for the token without echoing it, checks it against
``GET /api/v1/me``, and saves the **server URL** and the token in a
credentials **profile** (file mode ``0600``). It also downloads the
server's command list, so help knows every command from the start.
Scripts pipe the token in instead: ``pyc login --with-token <
token-file``. The token never has to appear on a command line.

``pyc whoami`` shows who the token authenticates as and when it
expires; ``pyc logout`` forgets it (``--revoke`` also revokes it on the
server). ``pyc`` warns on every command when the stored token expires
within seven days, and when it has expired.

A CI job needs no file at all: set ``PYC_SERVER_URL`` and ``PYC_TOKEN``
(a service account's token) and run the command.

Profiles
--------

Keep one profile per server (``staging``, ``production``) and pick one
with ``--profile NAME`` or ``PYC_PROFILE``; the default profile is
``default``. ``pyc config profiles`` lists them, ``pyc config set
server_url URL`` / ``get`` / ``unset`` / ``path`` manage one without
editing the file.

Commands
========

::

    pyc <noun> <verb> [PATH_PARAMETERS] [--query-parameter VALUE ...]

* **Nouns** are the REST resources, in the plural: ``projects``,
  ``runs``, ``rpa-jobs``, ``resource-pools``. The singular works too
  (``pyc project list``).
* **Verbs** follow the REST methods: ``list``, ``get``, ``create``,
  ``update``, ``delete``, plus the resource's own actions
  (``trigger``, ``cancel``, ``archive``, ``revoke`` ...).
* **Path parameters** are positional, in URL order:
  ``pyc rpa-jobs trigger PROJECT_ID SPEC_ID``.
* **Query parameters** are ``--kebab-case`` flags
  (``--per-page 20``, ``--state active``). Values are checked before
  anything is sent: numbers must be numbers, and a parameter with a
  fixed set of values accepts only those (case does not matter).
* **Request bodies** come from ``--data JSON`` (or ``--data @FILE``,
  or ``--data -`` for standard input), ``--from-file PATH``, and
  repeated ``--set FIELD=VALUE``. ``--set`` values are parsed as JSON
  when they can be (``--set count=3`` sends a number) and dotted fields
  nest (``--set labels.env=ci``); ``--set`` after ``--from-file``
  overrides that field.

``pyc commands`` lists every command the server offers; ``pyc <noun>
--help`` lists a noun's verbs; ``pyc <noun> <verb> --help`` shows the
REST endpoint, what each parameter means, its server default, and the
fields of the request body. Help never contacts the server: it is
written from the command list the last command (or ``pyc login``)
cached, so it is instant and works offline. ``pyc help <noun> <verb>``
is the same as ``--help``.

A few examples::

    pyc projects list
    pyc projects get demo
    pyc projects create --set slug=demo --set display_name="Demo"
    pyc rpa-jobs trigger 12 3 --from-file packet.json --wait
    pyc runs list --state failed --all -o tsv --fields run_id,project_id

Some operations used to be reached through their tag name (``pyc rpa
jobs-trigger``, ``pyc projects get-by-slug``); those spellings keep
working, and ``pyc rpa --help`` shows where each one moved.

A mistyped command, verb or option exits 2 and names the closest match:
``'projets list' is not a known command; did you mean 'projects'?``.

Waiting for runs
----------------

``POST`` commands that start a run take ``--wait``: ``pyc`` follows the
run and exits 0 when it succeeds, 10 when it fails, and 11 when
``--wait-timeout`` (default an hour) runs out; ``pyc runs wait RUN_ID``
does the same for a run started elsewhere. State changes are printed on
standard error and the finished run on standard output, so a CI step
can gate on the exit code and keep the run as JSON.

Output
======

``-o`` / ``--output`` chooses the format:

``table``
    Aligned columns (the default on a terminal). Columns that do not
    fit the terminal are left out, with a note naming them.
``json``
    One JSON document (the default when the output is not a terminal).
    A list prints as a JSON array of its items, ready for ``jq``.
``yaml``
    The same document as YAML.
``tsv``
    A header row and one tab-separated row per item.
``raw``
    The server's answer exactly as it was sent.

``--fields a,b,c`` keeps those fields, in that order (``labels.env``
reaches into an object); a field no item has is an error that suggests
the closest one. ``-q`` / ``--quiet`` prints only each item's
identifier, one per line -- the value the noun's ``get`` command takes,
so ``pyc projects list -q`` prints project slugs and
``pyc runs list -q`` prints run ids.

List commands return one page. When there are more items, ``pyc``
says so on standard error; ``--all`` fetches every page and prints the
items as one list, and ``--limit N`` stops after ``N`` items.

Errors and exit codes
=====================

Every failure is one ``error:`` line on standard error: the server's
problem title and detail, the HTTP status, and a **request id** --
``pyc`` sends an ``X-Request-Id`` header with every request and names
the id (the server's own, when it returns one), so a failure can be
found in the server's or a proxy's logs. ``PYC_DEBUG=1`` adds a
traceback for failures inside ``pyc`` itself.

====  =========================================================
Code  Meaning
====  =========================================================
0     Success.
2     Usage: a bad command line, or the server answered 400 / 422.
3     Authentication (401) or permission (403).
4     Not found (404).
5     Conflict (409).
6     Rate limited (429).
7     Server error (5xx), or an answer that is not the API's
      (a redirect to the sign-in page, an HTML page).
8     The server cannot be reached (refused, DNS, TLS, timeout).
10    ``--wait``: the run finished without succeeding.
11    ``--wait``: the run had not finished when the wait timed out.
13    Configuration: nothing configured, or an unreadable or
      corrupt credentials file, or one other users can read.
====  =========================================================

Files and environment
=====================

``pyc`` follows the XDG base-directory layout:

* credentials: ``$XDG_CONFIG_HOME/pychestrate/credentials``
  (``~/.config/pychestrate/credentials``), mode ``0600``. A
  ``~/.pychestrate/credentials`` file from an older ``pyc`` is still
  read when the new one does not exist.
* command-list cache: ``$XDG_CACHE_HOME/pychestrate/openapi/``
  (``~/.cache/pychestrate/openapi/``), refreshed after an hour.

Environment variables: ``PYC_SERVER_URL``, ``PYC_TOKEN``,
``PYC_PROFILE``, ``PYC_CREDENTIALS_PATH`` and ``PYC_OPENAPI_CACHE_DIR``
(override the two locations above), ``XDG_CONFIG_HOME``,
``XDG_CACHE_HOME``, ``PYC_DEBUG``.

Words pyc uses
==============

**Server URL**
    The address of the Pychestrate service, ``https://host[:port]``,
    without ``/api/v1``: ``--server-url``, ``PYC_SERVER_URL``, and
    ``server_url`` in a profile. (The pod client's
    ``pychestrate-client enroll --service-url`` takes the same URL.)
**API token**
    A ``pyc_...`` secret created under Account > API tokens (or for a
    service account) that acts as its owner. ``pyc`` sends it as
    ``Authorization: Bearer``.
**Profile**
    A named section of the credentials file holding a server URL and a
    token.
**Noun, verb**
    The two words of a command: a REST resource and what to do with it.

Extensions
==========

Extension packs can add commands under ``pyc ext <ext-name> <verb>``
(see `Extensions <11-00-extensions.rst>`_ for ``CLISubcommandExtension``).
``pyc ext list`` lists the extension routes the server mounts;
``pyc ext <ext-name> --help`` lists a pack's verbs. The route a verb
calls comes from the server's ``/api/v1/ext`` listing, so a pack
installed next to ``pyc`` only runs what the server actually serves.
