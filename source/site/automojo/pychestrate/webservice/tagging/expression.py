"""
.. module:: tagging.expression
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Boolean tag-expression compiler for 2-tagging M2 search.

.. moduleauthor:: Automation Mojo LLC

The expression grammar is intentionally small:

- Terminal: ``taxonomy:value`` matches entities that have that tag.
- Prefix NOT: ``!term``.
- Infix AND/OR: ``term AND term``, ``term OR term``.
- Parentheses: ``(term OR term) AND term``.

The compiler walks the expression AST and emits a predicate that accepts
a ``set`` of canonicalized ``taxonomy:value`` strings owned by an entity.
Callers batch-load the tag rows for the candidate entity kind and then
filter by the predicate.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from dataclasses import dataclass
from typing import Callable, FrozenSet, List, Optional

from automojo.pychestrate.webservice.tagging.exceptions import TagValueValidationError


TagPredicate = Callable[[FrozenSet[str]], bool]


_TOKEN_PATTERN = re.compile(
    r"""
    \s*(?:
        (?P<lparen>\() |
        (?P<rparen>\)) |
        (?P<op_and>AND\b) |
        (?P<op_or>OR\b) |
        (?P<op_not>!) |
        (?P<term>[a-z][a-z0-9_]{0,31}:[A-Za-z0-9_\-\.]+)
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Token:
    """
        Lexer output.
    """
    kind: str
    value: str


def compile_tag_expression(*, expression: str) -> TagPredicate:
    """
        Compile an expression string into a predicate over a tag set.

        :param expression: Boolean tag expression.

        :returns: A callable ``predicate(tag_set) -> bool``.
        :raises: TagValueValidationError on parse error.
    """
    if expression is None or len(expression.strip()) == 0:
        raise TagValueValidationError("Tag expression is empty")

    tokens = _tokenize(expression=expression)
    parser = _Parser(tokens=tokens)
    rtnval = parser.parse()
    if parser.index != len(tokens):
        err_msg_lines = ["Unparsed trailing input in tag expression."]
        err_msg_lines.append("EXPRESSION: {}".format(expression))
        err_msg = os.linesep.join(err_msg_lines)
        raise TagValueValidationError(err_msg)

    return rtnval


def _tokenize(*, expression: str) -> List[_Token]:
    """
        Convert an expression into a token list.
    """
    rtnval: List[_Token] = []
    position = 0
    while position < len(expression):
        match = _TOKEN_PATTERN.match(expression, position)
        if match is None:
            if expression[position].isspace() is True:
                position += 1
                continue
            err_msg_lines = ["Unexpected character in tag expression."]
            err_msg_lines.append("POSITION: {}".format(position))
            err_msg_lines.append("EXPRESSION: {}".format(expression))
            err_msg = os.linesep.join(err_msg_lines)
            raise TagValueValidationError(err_msg)

        for kind, value in match.groupdict().items():
            if value is not None:
                rtnval.append(_Token(kind=kind, value=value))
                break

        position = match.end()

    return rtnval


class _Parser:
    """
        Recursive-descent parser for the tag expression grammar.
    """

    def __init__(self, *, tokens: List[_Token]) -> None:
        self.tokens: List[_Token] = tokens
        self.index: int = 0
        return

    def parse(self) -> TagPredicate:
        rtnval = self._parse_or()
        return rtnval

    def _peek(self) -> Optional[_Token]:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def _advance(self) -> _Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _parse_or(self) -> TagPredicate:
        left = self._parse_and()
        while True:
            token = self._peek()
            if token is None or token.kind != "op_or":
                break
            self._advance()
            right = self._parse_and()
            left = _or_predicate(left=left, right=right)
        return left

    def _parse_and(self) -> TagPredicate:
        left = self._parse_not()
        while True:
            token = self._peek()
            if token is None or token.kind != "op_and":
                break
            self._advance()
            right = self._parse_not()
            left = _and_predicate(left=left, right=right)
        return left

    def _parse_not(self) -> TagPredicate:
        token = self._peek()
        if token is not None and token.kind == "op_not":
            self._advance()
            inner = self._parse_not()
            rtnval = _not_predicate(inner=inner)
            return rtnval
        rtnval = self._parse_primary()
        return rtnval

    def _parse_primary(self) -> TagPredicate:
        token = self._peek()
        if token is None:
            raise TagValueValidationError("Unexpected end of tag expression")

        if token.kind == "lparen":
            self._advance()
            inner = self._parse_or()
            closing = self._peek()
            if closing is None or closing.kind != "rparen":
                raise TagValueValidationError("Missing closing parenthesis")
            self._advance()
            return inner

        if token.kind == "term":
            self._advance()
            rtnval = _term_predicate(term=token.value.lower())
            return rtnval

        err_msg_lines = ["Unexpected token in tag expression."]
        err_msg_lines.append("TOKEN: {} ({})".format(token.kind, token.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise TagValueValidationError(err_msg)


def _term_predicate(*, term: str) -> TagPredicate:
    def _pred(tags: FrozenSet[str]) -> bool:
        rtnval = term in tags
        return rtnval
    return _pred


def _not_predicate(*, inner: TagPredicate) -> TagPredicate:
    def _pred(tags: FrozenSet[str]) -> bool:
        rtnval = not inner(tags)
        return rtnval
    return _pred


def _and_predicate(*, left: TagPredicate, right: TagPredicate) -> TagPredicate:
    def _pred(tags: FrozenSet[str]) -> bool:
        rtnval = left(tags) and right(tags)
        return rtnval
    return _pred


def _or_predicate(*, left: TagPredicate, right: TagPredicate) -> TagPredicate:
    def _pred(tags: FrozenSet[str]) -> bool:
        rtnval = left(tags) or right(tags)
        return rtnval
    return _pred
