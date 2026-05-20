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

        from automojo.testshared.factories.browsers.playwright_browser import create_playwright_browser

        for browser in create_playwright_browser():
            scope_automojo(sequencer, browser)

    return

def scope_automojo(sequencer, browser):
    """
    This is the entry point for the 'automojo' test scope.
    """

    with sequencer.enter_module_scope_context("automojo") as msc:
        scope_automojo_tests(sequencer, browser)

    return

def scope_automojo_tests(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests") as msc:
        scope_automojo_tests_singlehost(sequencer, browser)

    return

def scope_automojo_tests_singlehost(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost") as msc:
        scope_automojo_tests_singlehost_pychestrate(sequencer, browser)

    return

def scope_automojo_tests_singlehost_pychestrate(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate") as msc:
        scope_automojo_tests_singlehost_pychestrate_webservice(sequencer, browser)

    return

def scope_automojo_tests_singlehost_pychestrate_webservice(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice") as msc:
        scope_automojo_tests_singlehost_pychestrate_webservice_phase11(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12(sequencer, browser)

    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase11(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase11' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase11") as msc:
        scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15a_post_completion_smoke_m1(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15b_login_page_browser_m1(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15c_login_flow_httpx_m1(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15d_login_flow_browser_m1(sequencer, browser)

    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15a_post_completion_smoke_m1(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15a_post_completion_smoke_m1' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_admin_page_returns_404_after_wizard_completion ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_admin_page_returns_404_after_wizard_completion"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1 import test_admin_page_returns_404_after_wizard_completion

            test_admin_page_returns_404_after_wizard_completion()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_login_page_advertises_html_content_type ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_login_page_advertises_html_content_type"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1 import test_login_page_advertises_html_content_type

            test_login_page_advertises_html_content_type()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_login_page_html_mentions_login ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_login_page_html_mentions_login"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1 import test_login_page_html_mentions_login

            test_login_page_html_mentions_login()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_login_page_returns_200 ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_login_page_returns_200"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1 import test_login_page_returns_200

            test_login_page_returns_200()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_root_url_redirects_to_login_not_setup_after_completion ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_root_url_redirects_to_login_not_setup_after_completion"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1 import test_root_url_redirects_to_login_not_setup_after_completion

            test_root_url_redirects_to_login_not_setup_after_completion()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_unlock_page_returns_404_after_wizard_completion ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1#test_unlock_page_returns_404_after_wizard_completion"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15a_post_completion_smoke_m1 import test_unlock_page_returns_404_after_wizard_completion

            test_unlock_page_returns_404_after_wizard_completion()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15b_login_page_browser_m1(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15b_login_page_browser_m1' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1#test_login_page_has_username_password_inputs ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1#test_login_page_has_username_password_inputs"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1 import test_login_page_has_username_password_inputs

            test_login_page_has_username_password_inputs(browser)

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1#test_login_page_renders_with_login_in_title ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1#test_login_page_renders_with_login_in_title"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1 import test_login_page_renders_with_login_in_title

            test_login_page_renders_with_login_in_title(browser)

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1#test_root_url_does_not_redirect_to_setup_unlock ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1#test_root_url_does_not_redirect_to_setup_unlock"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15b_login_page_browser_m1 import test_root_url_does_not_redirect_to_setup_unlock

            test_root_url_does_not_redirect_to_setup_unlock(browser)


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15c_login_flow_httpx_m1(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15c_login_flow_httpx_m1' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1#test_authenticated_session_grants_dashboard_access ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1#test_authenticated_session_grants_dashboard_access"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1 import test_authenticated_session_grants_dashboard_access

            test_authenticated_session_grants_dashboard_access()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1#test_login_post_with_valid_credentials_redirects_to_safe_target ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1#test_login_post_with_valid_credentials_redirects_to_safe_target"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1 import test_login_post_with_valid_credentials_redirects_to_safe_target

            test_login_post_with_valid_credentials_redirects_to_safe_target()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1#test_login_post_with_wrong_password_does_not_authenticate ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1#test_login_post_with_wrong_password_does_not_authenticate"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15c_login_flow_httpx_m1 import test_login_post_with_wrong_password_does_not_authenticate

            test_login_post_with_wrong_password_does_not_authenticate()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15d_login_flow_browser_m1(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase11_test_p15d_login_flow_browser_m1' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15d_login_flow_browser_m1") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15d_login_flow_browser_m1#test_login_form_submission_lands_on_post_login_page ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15d_login_flow_browser_m1#test_login_form_submission_lands_on_post_login_page"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15d_login_flow_browser_m1 import test_login_form_submission_lands_on_post_login_page

            test_login_form_submission_lands_on_post_login_page(browser)

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15d_login_flow_browser_m1#test_login_form_with_wrong_password_stays_on_login_page ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15d_login_flow_browser_m1#test_login_form_with_wrong_password_stays_on_login_page"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase11.test_p15d_login_flow_browser_m1 import test_login_form_with_wrong_password_stays_on_login_page

            test_login_form_with_wrong_password_stays_on_login_page(browser)


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12") as msc:
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17d_shell_document_renders(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17e_admin_in_shell(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17f_shell_m2_smoke(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19m_runs_in_shell(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19n_run_detail_in_shell(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19p_test_catalog_in_shell(sequencer, browser)
        scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p20c_builds_in_shell(sequencer, browser)

    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17d_shell_document_renders(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17d_shell_document_renders' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders#test_anonymous_root_path_redirects_to_login ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders#test_anonymous_root_path_redirects_to_login"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders import test_anonymous_root_path_redirects_to_login

            test_anonymous_root_path_redirects_to_login()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders#test_root_path_serves_site_shell_document ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders#test_root_path_serves_site_shell_document"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders import test_root_path_serves_site_shell_document

            test_root_path_serves_site_shell_document()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders#test_shell_bundle_is_served_as_javascript ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders#test_shell_bundle_is_served_as_javascript"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17d_shell_document_renders import test_shell_bundle_is_served_as_javascript

            test_shell_bundle_is_served_as_javascript()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17e_admin_in_shell(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17e_admin_in_shell' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17e_admin_in_shell") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17e_admin_in_shell#test_admin_bundle_is_served_as_javascript ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17e_admin_in_shell#test_admin_bundle_is_served_as_javascript"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17e_admin_in_shell import test_admin_bundle_is_served_as_javascript

            test_admin_bundle_is_served_as_javascript()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17e_admin_in_shell#test_admin_dashboard_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17e_admin_in_shell#test_admin_dashboard_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17e_admin_in_shell import test_admin_dashboard_renders_inside_site_shell

            test_admin_dashboard_renders_inside_site_shell()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17f_shell_m2_smoke(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p17f_shell_m2_smoke' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17f_shell_m2_smoke") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17f_shell_m2_smoke#test_admin_dashboard_still_renders_inside_shell_with_m2_bundle ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17f_shell_m2_smoke#test_admin_dashboard_still_renders_inside_shell_with_m2_bundle"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17f_shell_m2_smoke import test_admin_dashboard_still_renders_inside_shell_with_m2_bundle

            test_admin_dashboard_still_renders_inside_shell_with_m2_bundle()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17f_shell_m2_smoke#test_shell_bundle_carries_m2_palette_module ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17f_shell_m2_smoke#test_shell_bundle_carries_m2_palette_module"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p17f_shell_m2_smoke import test_shell_bundle_carries_m2_palette_module

            test_shell_bundle_carries_m2_palette_module()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19m_runs_in_shell(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19m_runs_in_shell' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19m_runs_in_shell") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19m_runs_in_shell#test_runs_bundle_is_served_as_javascript ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19m_runs_in_shell#test_runs_bundle_is_served_as_javascript"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19m_runs_in_shell import test_runs_bundle_is_served_as_javascript

            test_runs_bundle_is_served_as_javascript()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19m_runs_in_shell#test_runs_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19m_runs_in_shell#test_runs_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19m_runs_in_shell import test_runs_page_renders_inside_site_shell

            test_runs_page_renders_inside_site_shell()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19n_run_detail_in_shell(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19n_run_detail_in_shell' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19n_run_detail_in_shell") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19n_run_detail_in_shell#test_run_detail_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19n_run_detail_in_shell#test_run_detail_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19n_run_detail_in_shell import test_run_detail_page_renders_inside_site_shell

            test_run_detail_page_renders_inside_site_shell()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19p_test_catalog_in_shell(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p19p_test_catalog_in_shell' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19p_test_catalog_in_shell") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19p_test_catalog_in_shell#test_test_catalog_bundle_is_served_as_javascript ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19p_test_catalog_in_shell#test_test_catalog_bundle_is_served_as_javascript"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19p_test_catalog_in_shell import test_test_catalog_bundle_is_served_as_javascript

            test_test_catalog_bundle_is_served_as_javascript()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19p_test_catalog_in_shell#test_test_catalog_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19p_test_catalog_in_shell#test_test_catalog_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p19p_test_catalog_in_shell import test_test_catalog_page_renders_inside_site_shell

            test_test_catalog_page_renders_inside_site_shell()


    return

def scope_automojo_tests_singlehost_pychestrate_webservice_phase12_test_p20c_builds_in_shell(sequencer, browser):
    """
    This is the entry point for the 'automojo_tests_singlehost_pychestrate_webservice_phase12_test_p20c_builds_in_shell' test scope.
    """

    with sequencer.enter_module_scope_context("automojo.tests.singlehost.pychestrate.webservice.phase12.test_p20c_builds_in_shell") as msc:
        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p20c_builds_in_shell#test_builds_bundle_is_served_as_javascript ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p20c_builds_in_shell#test_builds_bundle_is_served_as_javascript"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p20c_builds_in_shell import test_builds_bundle_is_served_as_javascript

            test_builds_bundle_is_served_as_javascript()

        # ================ Test Scope: automojo.tests.singlehost.pychestrate.webservice.phase12.test_p20c_builds_in_shell#test_builds_page_renders_inside_site_shell ================

        test_scope_name = "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p20c_builds_in_shell#test_builds_page_renders_inside_site_shell"

        with sequencer.enter_test_scope_context(test_scope_name) as tscope:
            from automojo.tests.singlehost.pychestrate.webservice.phase12.test_p20c_builds_in_shell import test_builds_page_renders_inside_site_shell

            test_builds_page_renders_inside_site_shell()


    return
