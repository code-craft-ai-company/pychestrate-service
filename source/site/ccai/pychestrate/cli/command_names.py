"""
.. module:: cli.command_names
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The ``pyc <noun> <verb>`` names of the server's REST
               operations.

.. moduleauthor:: Code Craft AI LLC

Every operation of the server's OpenAPI document is one
``pyc <noun> <verb>`` command. Its name comes from, in order:

1. the operation's ``x-cli`` extension in the OpenAPI document
   (``x-cli: {noun: rpa-jobs, verb: trigger}``), so the REST contract
   can name its own commands;
2. :data:`COMMAND_NAMES` below, for the operations whose derived name
   reads badly: a tag that groups several REST resources (``rpa``
   holds job types, specifications and jobs), or a verb that repeats
   the resource (``notifications list-channels``);
3. derivation (see :mod:`cli.parser`): the first tag is the noun and
   the ``operationId`` without the tag prefix is the verb, with the
   :data:`VERB_SYNONYMS` spellings (``read`` and ``get-by-<x>`` are
   ``get``, ``patch`` is ``update``) when that verb is still free.

Nouns are the plural REST resource names (``projects``,
``rpa-jobs``); a singular noun is accepted too. The derived name always
stays an alias, so ``pyc projects get-by-slug demo`` still works next
to ``pyc projects get demo``.

The table is keyed by ``operationId``; the REST <-> CLI parity test
(``test_p27p_pyc_command_names_m3``) fails when an entry names an
operation the document no longer has, or when two operations end up
with the same name.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Dict, Optional, Tuple


#: The OpenAPI operation extension that names an operation's command.
X_CLI_EXTENSION: str = "x-cli"

#: Derived verbs spelled with the standard verb instead, when free.
VERB_SYNONYMS: Dict[str, str] = {
    "read": "get",
    "patch": "update",
}

#: ``get-by-<anything>`` (``get-by-slug``, ``get-by-id``) is ``get``.
GET_BY_VERB_PATTERN = re.compile(r"^get-by-[a-z0-9-]+$")

#: Explicit names: ``operationId`` -> ``(noun, verb)``.
COMMAND_NAMES: Dict[str, Tuple[str, str]] = {
    # agents: agent rollouts, and the capability records of clients.
    "agents_create_rollout": ("agent-rollouts", "create"),
    "agents_start_rollout": ("agent-rollouts", "start"),
    "agents_get_client_capabilities": ("clients", "get-capabilities"),
    "agents_put_client_capabilities": ("clients", "set-capabilities"),
    "agents_get_client_inventory": ("clients", "inventory"),

    # api_tokens
    "api_tokens_read_mine": ("api-tokens", "get-mine"),

    # artifacts, and the result-upload calls pods make (tag results).
    "artifacts_get_entry": ("artifacts", "get"),
    "artifacts_list_for_run": ("artifacts", "list"),
    "artifacts_local_upload": ("artifacts", "local-upload"),
    "artifacts_presign_upload": ("artifacts", "presign-upload"),
    "results_post_complete": ("results", "complete"),

    # dispatch: the envelope-signing keys pods verify jobs with, and
    # the acknowledgement a pod sends for a dispatched run.
    "envelope_signing_keys_jwks": ("envelope-signing-keys", "jwks"),
    "envelope_signing_keys_list": ("envelope-signing-keys", "list"),
    "dispatch_ack_run": ("runs", "ack-dispatch"),

    # progress: the live-progress frames a pod posts for a run.
    "progress_post_frame": ("runs", "post-progress"),

    # drift
    "drift_check_trigger": ("drift", "check"),
    "drift_status_read": ("drift", "status"),

    # enrollment: tokens pods enroll with.
    "enrollment_create_token": ("enrollment-tokens", "create"),
    "enrollment_delete_token": ("enrollment-tokens", "delete"),
    "enrollment_list_tokens": ("enrollment-tokens", "list"),
    "enrollment_redeem": ("enrollment-tokens", "redeem"),
    "enrollment_revoke_client": ("enrollment-tokens", "revoke-client"),

    # flags
    "flags_get_history": ("flags", "history"),

    # me
    "me_get_identity": ("me", "get"),
    "me_get_navigation": ("me", "navigation"),
    "me_get_permissions": ("me", "permissions"),
    "me_ui_surfaces_read": ("me", "get-ui-surfaces"),
    "me_ui_surfaces_update": ("me", "set-ui-surfaces"),
    "me_ui_surfaces_delete": ("me", "delete-ui-surfaces"),

    # metrics
    "metrics_catalog_list": ("metrics", "catalog"),
    "metrics_test_read": ("metrics", "tests"),
    "metrics_timeseries_query": ("metrics", "query"),

    # notifications: notification channels.
    "notifications_create_channel": ("notification-channels", "create"),
    "notifications_get_channel": ("notification-channels", "get"),
    "notifications_list_channels": ("notification-channels", "list"),

    # pipelines: pipeline runs are their own resource.
    "pipeline_runs_list": ("pipeline-runs", "list"),
    "pipeline_runs_read": ("pipeline-runs", "get"),
    "pipeline_runs_trigger": ("pipeline-runs", "trigger"),

    # pods: pod definitions and pod templates are their own resources.
    "pods_create_definition": ("pod-definitions", "create"),
    "pods_get_definition": ("pod-definitions", "get"),
    "pods_list_definitions": ("pod-definitions", "list"),
    "pods_create_template": ("pod-templates", "create"),
    "pods_delete_template": ("pod-templates", "delete"),
    "pods_list_templates": ("pod-templates", "list"),
    "pods_materialize_template": ("pod-templates", "materialize"),
    "pods_update_template_parameters": ("pod-templates", "set-parameters"),
    "pods_apply_state_transition": ("pods", "transition"),
    "pods_get_registration": ("pods", "registration"),
    "pods_list_registrations": ("pods", "registrations"),
    "pods_get_state": ("pods", "state"),
    "pods_get_state_history": ("pods", "state-history"),
    "pods_get_topology": ("pods", "topology"),

    # provisioning: provisioning runs.
    "provisioning_runs_list": ("provisioning-runs", "list"),
    "provisioning_runs_read": ("provisioning-runs", "get"),
    "provisioning_runs_trigger": ("provisioning-runs", "trigger"),

    # resources
    "resources_list_usage_history": ("resources", "usage-history"),
    "resources_read_health": ("resources", "health"),
    "resources_transition_state": ("resources", "transition"),

    # retention: retention policies.
    "retention_create": ("retention-policies", "create"),
    "retention_get_by_id": ("retention-policies", "get"),
    "retention_list": ("retention-policies", "list"),
    "retention_publish": ("retention-policies", "publish"),

    # rpa: job types (and their versions), specifications, jobs.
    "rpa_execution_modes_list": ("rpa-execution-modes", "list"),
    "rpa_job_type_versions_deprecate": ("rpa-job-types", "deprecate-version"),
    "rpa_job_type_versions_publish": ("rpa-job-types", "publish-version"),
    "rpa_job_type_versions_retire": ("rpa-job-types", "retire-version"),
    "rpa_job_types_create": ("rpa-job-types", "create"),
    "rpa_job_types_list": ("rpa-job-types", "list"),
    "rpa_job_types_read": ("rpa-job-types", "get"),
    "rpa_job_types_retire": ("rpa-job-types", "retire"),
    "rpa_job_types_update": ("rpa-job-types", "update"),
    "rpa_jobs_cancel": ("rpa-jobs", "cancel"),
    "rpa_jobs_list": ("rpa-jobs", "list"),
    "rpa_jobs_logs": ("rpa-jobs", "logs"),
    "rpa_jobs_read": ("rpa-jobs", "get"),
    "rpa_jobs_trigger": ("rpa-jobs", "trigger"),
    "rpa_specs_create": ("rpa-specs", "create"),
    "rpa_specs_delete": ("rpa-specs", "delete"),
    "rpa_specs_list": ("rpa-specs", "list"),
    "rpa_specs_read": ("rpa-specs", "get"),
    "rpa_specs_update": ("rpa-specs", "update"),

    # runs
    "runs_subscribe_events": ("runs", "events"),

    # system
    "system_health_read": ("system", "health"),

    # tagging: the /tags resource.
    "tagging_attach": ("tags", "attach"),
    "tagging_detach": ("tags", "detach"),
    "tagging_list_for_entity": ("tags", "list"),
    "tagging_list_taxonomies": ("tags", "taxonomies"),
    "tagging_search": ("tags", "search"),

    # variables
    "variables_delete_one": ("variables", "delete"),
    "variables_get_effective": ("variables", "effective"),
    "variables_get_one": ("variables", "get"),
    "variables_list_scope": ("variables", "list"),
    "variables_put_one": ("variables", "set"),

    # webhooks: inbound integrations and outbound subscriptions.
    "webhooks_in_create_integration": ("webhook-integrations", "create"),
    "webhooks_in_list_integrations": ("webhook-integrations", "list"),
    "webhooks_in_update_integration": ("webhook-integrations", "update"),
    "webhooks_in_list_deliveries": ("webhook-integrations", "deliveries"),
    "webhooks_in_receive": ("webhook-integrations", "receive"),
    "webhooks_out_create_subscription": ("webhook-subscriptions", "create"),
    "webhooks_out_delete_subscription": ("webhook-subscriptions", "delete"),
    "webhooks_out_list_deliveries": ("webhook-subscriptions", "deliveries"),
    "webhooks_out_list_subscriptions": ("webhook-subscriptions", "list"),
    "webhooks_out_read_subscription": ("webhook-subscriptions", "get"),
    "webhooks_out_test_subscription": ("webhook-subscriptions", "test"),
    "webhooks_out_update_subscription": ("webhook-subscriptions", "update"),
}

#: A well-formed noun or verb: lower-case words joined by ``-``.
COMMAND_WORD_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def synonym_verb(verb: str) -> Optional[str]:
    """
        The standard spelling of a derived verb (``read`` -> ``get``,
        ``get-by-slug`` -> ``get``, ``patch`` -> ``update``), or
        ``None`` when the verb is already standard.

        :param verb: Derived, normalized verb.

        :returns: Standard verb or ``None``.
    """
    if verb in VERB_SYNONYMS:
        rtnval: Optional[str] = VERB_SYNONYMS[verb]
        return rtnval
    if GET_BY_VERB_PATTERN.match(verb) is not None:
        rtnval = "get"
        return rtnval
    rtnval = None
    return rtnval


def is_well_formed_word(word: str) -> bool:
    """
        Whether ``word`` is a well-formed noun or verb (lower case,
        ``-`` between words, no spaces or underscores).

        :param word: Noun or verb.

        :returns: Boolean.
    """
    rtnval = COMMAND_WORD_PATTERN.match(word or "") is not None
    return rtnval


__all__ = [
    "COMMAND_NAMES",
    "COMMAND_WORD_PATTERN",
    "VERB_SYNONYMS",
    "X_CLI_EXTENSION",
    "is_well_formed_word",
    "synonym_verb",
]
