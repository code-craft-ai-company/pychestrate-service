.. _10-03-testing-patterns-and-practices:

==============================
Testing Patterns and Practices
==============================

Testing is a crucial part of software development that ensures the reliability and
correctness of code. This section outlines best practices and patterns for writing
effective tests.


Test Granularity
================
Tests should be written to verify the functionality of individual components or
functions in isolation. Each test should focus on a single aspect of the code to
ensure clarity and maintainability.

Tests should NOT serve as a composite test for multiple components or functions where
a sigle test verifies the functionality of multiple components or functions in a series
of assertions.  This practice does not provide adequate isolation and causes checks to be
missed when an assertion fails. Instead, each test should be focused on a single
component or function, allowing for easier debugging and understanding of test failures.

The unittest framework in Python provides setup and tearDown methods that can be
used to establish common conditions that can be shared across multiple tests within
a given test class.  This allows for efficient code reuse while maintaining seperation
of concerns for individual tests.


Unit Tests
==========


TestBase Tests
==============

