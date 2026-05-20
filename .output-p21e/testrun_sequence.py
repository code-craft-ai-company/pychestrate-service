"""
    ======================================= CODE GENERATED - DO NOT EDIT =======================================
    This is a code generated execution sequence document, do not manually edit this document.  The 'testbase'
    test framework generates this document in order to layout the test run scopes, parameter creations, and
    test calls in a user ledgible way which is easy to read and also to debug.
"""

__traceback_format_policy__ = "Brief"

import logging

from automojo.xmodules.xlogging.enhancedloggers import getEnhancedLogger

from automojo.testbase.constraints import ConstraintsCatalog

logger = getEnhancedLogger()

constraints_catalog = ConstraintsCatalog()



def session(sequencer):
    """
    This is the entry point for the test run sequence document.
    """

    with sequencer.enter_session_scope_context() as ssc:


        scope_automojo(sequencer)

    return

def scope_automojo(sequencer):
    """
    This is the entry point for the 'automojo' test scope.
    """

    with sequencer.enter_module_scope_context("automojo") as msc:
        scope_automojo_tests(sequencer)

    return

def scope_automojo_tests(sequencer):
    """
    This is the entry point for the 'automojo_tests' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests") as msc:
        scope_automojo_tests_singlehost(sequencer)

    return

def scope_automojo_tests_singlehost(sequencer):
    """
    This is the entry point for the 'automojo_tests_singlehost' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost") as msc:
        scope_automojo_tests_singlehost_pychestrate(sequencer)

    return

def scope_automojo_tests_singlehost_pychestrate(sequencer):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate") as msc:
        scope_automojo_tests_singlehost_pychestrate_webservice(sequencer)

    return

def scope_automojo_tests_singlehost_pychestrate_webservice(sequencer):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice") as msc:
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12(sequencer)

    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12(sequencer):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12") as msc:
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p21e_ops_ui_in_shell(sequencer)

    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p21e_ops_ui_in_shell(sequencer):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p21e_ops_ui_in_shell' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_blast_radius_guards_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_blast_radius_guards_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell import test_blast_radius_guards_page_renders_inside_site_shell

            test_blast_radius_guards_page_renders_inside_site_shell()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_ops_bundle_is_served_as_javascript ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_ops_bundle_is_served_as_javascript"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell import test_ops_bundle_is_served_as_javascript

            test_ops_bundle_is_served_as_javascript()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_release_channels_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_release_channels_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell import test_release_channels_page_renders_inside_site_shell

            test_release_channels_page_renders_inside_site_shell()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_slos_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_slos_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell import test_slos_page_renders_inside_site_shell

            test_slos_page_renders_inside_site_shell()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_webhooks_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell#test_webhooks_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p21e_ops_ui_in_shell import test_webhooks_page_renders_inside_site_shell

            test_webhooks_page_renders_inside_site_shell()


    return
