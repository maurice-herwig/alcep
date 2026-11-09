from unittest import TestCase
from unittest.mock import patch

from lark import Lark
from lark.corrections.edit_operations import (
    DeletionOperation,
    InsertionOperation,
    ReadOperation,
    ReplacementOperation,
)
from lark.exceptions import GrammarError


class TestALCIEP(TestCase):
    @staticmethod
    def make_parser(grammar):
        return Lark(grammar, parser="alciep", lexer="basic", ambiguity="forest")

    @staticmethod
    def parse_with_choices(parser, text, choices):
        with patch("builtins.input", side_effect=[str(choice) for choice in choices]), \
                patch("builtins.print"):
            return parser.parse(text)

    @staticmethod
    def parse_with_operations(parser, text, operations):
        printed = []
        remaining_operations = list(operations)

        def record_print(*args):
            printed.append(" ".join(str(arg) for arg in args))

        def choose_operation(_prompt=""):
            marker = max(index for index, line in enumerate(printed)
                         if line == "Possible edit operations:")
            available = printed[marker + 1:]
            operation = remaining_operations.pop(0)
            for line in available:
                if operation in line:
                    return line.split(":", 1)[0]
            raise AssertionError(
                f"Operation {operation!r} not available in {available!r}"
            )

        with patch("builtins.input", side_effect=choose_operation), \
                patch("builtins.print", side_effect=record_print):
            correction = parser.parse(text)

        self_remaining = remaining_operations
        if self_remaining:
            raise AssertionError(f"Unused operation choices: {self_remaining!r}")
        return correction

    def test_predictor_completion_and_read(self):
        parser = self.make_parser("""
            start: expression
            expression: A
            A: "a"
        """)

        correction = self.parse_with_choices(parser, "a", [1, 0])

        self.assertEqual(correction.apply(), "A")
        self.assertIsInstance(correction.operations[0], ReadOperation)

    def test_invalid_interactive_choices_are_rejected(self):
        parser = self.make_parser('start: A\nA: "a"')

        correction = self.parse_with_choices(parser, "a", ["invalid", 99, 1, 0])

        self.assertEqual(correction.apply(), "A")

    def test_replacement(self):
        parser = self.make_parser('start: A\nA: "a"')

        # Force the terminal matcher to reject the input token. This isolates
        # the replacement transition from the lexer token type.
        parser.parser.parser.term_matcher = lambda _terminal, _token: False
        correction = self.parse_with_choices(parser, "a", [1, 0])

        self.assertEqual(correction.apply(), "A")
        self.assertIsInstance(correction.operations[0], ReplacementOperation)

    def test_insertion(self):
        parser = self.make_parser("""
            start: A B
            A: "a"
            B: "b"
        """)

        correction = self.parse_with_choices(parser, "b", [2, 1, 0])

        self.assertEqual(correction.apply(), "AB")
        self.assertIsInstance(correction.operations[0], InsertionOperation)
        self.assertIsInstance(correction.operations[1], ReadOperation)

    def test_deletion_does_not_advance_target_position(self):
        parser = self.make_parser("""
            start: A B
            A: "a"
            B: "b"
        """)

        # Delete the leading B, read A, insert B, then finish.
        correction = self.parse_with_choices(parser, "ba", [0, 1, 0, 0])

        self.assertEqual(correction.apply(), "AB")
        self.assertIsInstance(correction.operations[0], DeletionOperation)
        self.assertIsInstance(correction.operations[1], ReadOperation)
        self.assertIsInstance(correction.operations[2], InsertionOperation)

    def test_empty_derivation_can_finish_without_input(self):
        parser = self.make_parser("""
            start: A?
            A: "a"
        """)

        correction = self.parse_with_choices(parser, "", [1])

        self.assertEqual(correction.operations, [])
        self.assertEqual(correction.apply(), "")

    def test_multiple_held_completions(self):
        parser = self.make_parser("""
            start: expression
            expression: A | A B?
            A: "a"
            B: "b"
        """)

        # Both alternatives can complete expression after reading A.
        correction = self.parse_with_choices(parser, "a", [1, 1])

        self.assertEqual(correction.apply(), "A")

    def test_nested_recursive_grammar(self):
        parser = self.make_parser("""
            start: LPAR start RPAR | N
            LPAR: "("
            RPAR: ")"
            N: "n"
        """)

        correction = self.parse_with_operations(
            parser,
            "(n)",
            ["READ 'LPAR'", "READ 'N'", "READ 'RPAR'", "Finish Correction"],
        )

        self.assertEqual(correction.apply(), "LPARNRPAR")

    def test_nullable_nonterminal_between_terminals(self):
        parser = self.make_parser("""
            start: A middle B
            middle: C?
            A: "a"
            B: "b"
            C: "c"
        """)

        correction = self.parse_with_operations(
            parser,
            "ab",
            ["READ 'A'", "READ 'B'", "Finish Correction"],
        )

        self.assertEqual(correction.apply(), "AB")

    def test_multiple_deletions_keep_same_earley_state(self):
        parser = self.make_parser("""
            start: A A
            A: "a"
        """)

        correction = self.parse_with_operations(
            parser,
            "aaaa",
            ["DEL 'A'", "DEL 'A'", "READ 'A'", "READ 'A'", "Finish Correction"],
        )

        self.assertEqual(correction.apply(), "AA")
        self.assertEqual(sum(isinstance(operation, DeletionOperation)
                             for operation in correction.operations), 2)

    def test_arithmetic_correction_with_deletion(self):
        parser = self.make_parser("""
            start: expression
            expression: N (PLUS N)*
            N: "n"
            PLUS: "+"
        """)

        correction = self.parse_with_operations(
            parser,
            "n++n",
            ["READ 'N'", "READ 'PLUS'", "DEL 'PLUS'", "READ 'N'", "Finish Correction"],
        )

        self.assertEqual(correction.apply(), "NPLUSN")
        self.assertTrue(any(isinstance(operation, DeletionOperation)
                            for operation in correction.operations))

    def test_only_productive_rules_are_retained(self):
        parser = self.make_parser("""
            start: good | bad
            good: B
            bad: A bad
            A: "a"
            B: "b"
        """)

        implementation = parser.parser.parser
        productive_origins = {rule.origin.name for rule in implementation.productive_rules}

        self.assertIn("start", productive_origins)
        self.assertIn("good", productive_origins)
        self.assertNotIn("bad", productive_origins)

    def test_unproductive_start_is_rejected(self):
        with self.assertRaises(GrammarError):
            self.make_parser("""
                start: bad
                bad: A bad
                A: "a"
            """)

    def test_rule_priorities_are_rejected(self):
        with self.assertRaises(Exception):
            self.make_parser("""
                start.1: A
                A: "a"
            """)


if __name__ == "__main__":
    import unittest
    unittest.main()
