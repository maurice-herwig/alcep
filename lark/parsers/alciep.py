from typing import TYPE_CHECKING, Callable, Optional, List, Any
from lark.tree import Tree
from lark.utils import OrderedSet
from lark.parsers.grammar_analysis import GrammarAnalyzer
from lark.parsers.earley_forest import StableSymbolNode, SymbolNode
from lark.parsers.earley_common import Item
from lark.grammar import NonTerminal, Terminal
from lark.exceptions import GrammarError
from collections import deque

if TYPE_CHECKING:
    from lark.common import LexerConf, ParserConf

FINISH_CORRECTION = "Finish Correction"


class BaseParser:
    lexer_conf: 'LexerConf'
    parser_conf: 'ParserConf'
    debug: bool

    def __init__(self, lexer_conf: 'LexerConf', parser_conf: 'ParserConf', term_matcher: Callable, debug: bool = False,
                 tree_class: Optional[Callable[[str, List], Any]] = Tree, ordered_sets: bool = True):

        """
                Constructor of the all correction earley Parser.

                :param lexer_conf: The configuration of the Lexer.
                :param parser_conf: The configuration of the Lexer.
                :param term_matcher: A matcher function.
                :param debug: A boolean value that specifies whether the debug mode of the parser should be used,
                :param tree_class: The used tree class.
                :param ordered_sets: A boolean if ordered sets are used instead of normal sets.
                """

        # set the attributes
        self.lexer_conf = lexer_conf
        self.parser_conf = parser_conf
        self.debug = debug
        self.Tree = tree_class
        self.Set = OrderedSet if ordered_sets else set
        self.SymbolNode = StableSymbolNode if ordered_sets else SymbolNode
        self.term_matcher = term_matcher

        # analyse the given grammar
        analysis = GrammarAnalyzer(parser_conf)

        # self.FIRST := For a grammar symbol 𝑋, First(X) is the set of terminals that can appear at the beginning of
        #               strings derived from 𝑋. If 𝑋 can derive the empty string 𝜖 then ϵ is included in First(X).
        self.FIRST = analysis.FIRST

        # self.NULLABLE := The set of non-terminals from which we can derive the empty string 𝜖.
        self.NULLABLE = analysis.NULLABLE

        # Compute the productive non-terminals independently of FIRST.  A
        # non-empty FIRST set alone is not sufficient: for example,
        # A -> "a" A has FIRST(A) = {"a"} but derives no finite word.
        productive_non_terminals = set()
        changed = True
        while changed:
            changed = False
            for rule in parser_conf.rules:
                if (rule.origin not in productive_non_terminals
                        and all(symbol.is_term or symbol in productive_non_terminals
                                for symbol in rule.expansion)):
                    productive_non_terminals.add(rule.origin)
                    changed = True

        def is_productive_rule(rule):
            return (rule.origin in productive_non_terminals
                    and all(symbol.is_term or symbol in productive_non_terminals
                            for symbol in rule.expansion))

        self.productive_rules = {
            rule for rule in parser_conf.rules if is_productive_rule(rule)
        }

        if any(not any(rule.origin == NonTerminal(start)
                       for rule in self.productive_rules)
               for start in parser_conf.start):
            raise GrammarError(
                "At least one start symbol of the ALCIEP grammar is not productive."
            )

        # Compute the set of terminals and non-terminals
        # These could be moved to the grammar analyzer. Pre-computing these is *much* faster than
        # the slow 'isupper' in is_terminal.
        self.TERMINALS = {sym for r in self.productive_rules for sym in r.expansion if sym.is_term}
        self.NON_TERMINALS = {sym for r in self.productive_rules for sym in r.expansion if not sym.is_term}

        # Create a dictionary for all productions rules in the form
        # key: non-terminal S value: list of rules S -> xyz
        self.predictions = {}

        # Iterate over all production rules to create the set of predictions
        for rule in parser_conf.rules:
            if rule.origin not in self.predictions:
                self.predictions[rule.origin] = [
                    x.rule for x in analysis.expand_rule(rule.origin)
                    if x.rule in self.productive_rules
                ]

            # Detect if any rules/terminals have priorities set.
            # The all correction earley parser don't support priorities.
            if rule.options.priority is not None:
                raise Exception("The all correction earley parser don't support priorities.")

        # Check terminals for priorities
        #for term in self.lexer_conf.terminals:
        #    if term.priority:
        #        raise Exception("The all correction earley parser don't support priorities.")

    def _complete_earley_set(self, i, earley_sets, to_scan):
        """Close one Earley set under prediction and completion."""
        held_completions = {}
        current_earley_set = earley_sets[i]
        items = deque(current_earley_set)

        while items:
            item = items.pop()

            if item.is_complete:
                if item.start == i:
                    held_completions.setdefault(item.rule.origin, set()).add(item)

                originators = [originator for originator in earley_sets[item.start]
                               if originator.expect is not None and originator.expect == item.s]
                for originator in originators:
                    new_item = originator.advance()
                    if new_item not in current_earley_set:
                        current_earley_set.add(new_item)
                        items.append(new_item)
                        if new_item.expect in self.TERMINALS:
                            to_scan.setdefault(new_item.expect, self.Set()).add(new_item)

            elif item.expect in self.NON_TERMINALS:
                for rule in self.predictions[item.expect]:
                    new_item = Item(rule, 0, i)
                    if new_item not in current_earley_set:
                        current_earley_set.add(new_item)
                        items.append(new_item)
                        if new_item.expect in self.TERMINALS:
                            to_scan.setdefault(new_item.expect, self.Set()).add(new_item)

                for _completion in held_completions.get(item.expect, ()):
                    new_item = item.advance()
                    if new_item not in current_earley_set:
                        current_earley_set.add(new_item)
                        items.append(new_item)
                        if new_item.expect in self.TERMINALS:
                            to_scan.setdefault(new_item.expect, self.Set()).add(new_item)

        return to_scan

    def parse(self, lexer, start):
        """
        The parse functionality of the all correction interactive earley parser.

        :param lexer: The uses lexer object.
        :param start: The start symbol of the grammar as string.

        :return: The selected correction as WordOrderedCorrection object.
        """

        # Assert that the start symbol is set.
        assert start, start

        # Create a non-terminal object for the start symbol.
        start_symbol = NonTerminal(start)

        # Init a list of the earley sets
        earley_sets = [self.Set()]

        # Init a list of items of the current set with a terminal to the right of the bullet point.
        # The set N in the all correction earley parser.
        to_scan = {}

        # Init the first earley set and the set to_scan by predict for the start_symbol.
        for rule in self.predictions[start_symbol]:

            # Create af earley Item for the current rule
            item = Item(rule, 0, 0)

            # Add the item to the current earley set
            earley_sets[0].add(item)

            # Check if the next terminal/non-terminal after the bullet point a terminal.
            if item.expect in self.TERMINALS:
                if item.expect in to_scan:
                    to_scan[item.expect].add(item)
                else:
                    to_scan[item.expect] = self.Set([item])

        # The initial set must already be closed under prediction and
        # completion before the first interactive choice is offered.
        to_scan = self._complete_earley_set(i=0, earley_sets=earley_sets, to_scan=to_scan)

        # The index of the current Earley Set
        i = 0

        # Compute the tokens of the input and set j index for the current token
        tokens = [token for token in lexer.lex({})]
        n = len(tokens)
        j = 0

        # The resulting correction
        end_correction = False
        correction = []

        from ..corrections.edit_operations import InsertionOperation, DeletionOperation, ReplacementOperation, \
            ReadOperation
        from lark.corrections import word_ordered_correction

        while not end_correction:

            next_token = tokens[j] if j < n else None

            # Compute the next possible edit options
            edit_options = []

            # Option 1: Delete the next token
            if next_token is not None:
                edit_options.append(DeletionOperation(next_token.type))

                for terminal in to_scan.keys():
                    # Option 2 and 3: Read or Replace the next token
                    if self.term_matcher(terminal, next_token):
                        edit_options.append(ReadOperation(terminal.name))
                    else:
                        edit_options.append(ReplacementOperation(next_token, terminal.name))

            # Option 4: Insert a terminal before the next token
            for terminal in to_scan.keys():
                edit_options.append(InsertionOperation(terminal.name))

            # Option 5: If there is a final item for the start symbol and the complete word a seen,
            # finish the correction
            if j == n:
                if any((item.is_complete and item.rule.origin == start_symbol and item.start == 0) for item in
                       earley_sets[i]):
                    edit_options.append(FINISH_CORRECTION)

            # Print the corrections to the console
            edit_dict = {i: edit for i, edit in zip(range(len(edit_options)), edit_options)}
            print("Possible edit operations:")
            for key, value in edit_dict.items():
                print(f"{key}: {value} ")

            # Let the user choose an edit operation
            while True:
                try:
                    chosen_option = int(input("Choose an edit operation by its number: "))
                    if chosen_option in edit_dict:
                        break
                    else:
                        print("Invalid option. Please choose a valid number.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
            chosen_edit = edit_dict[chosen_option]
            correction.append(chosen_edit)

            # Apply the chosen edit operation
            if chosen_edit == FINISH_CORRECTION:
                end_correction = True
                continue

            if type(chosen_edit) in [ReadOperation, ReplacementOperation, DeletionOperation]:
                j += 1

            # Apply deletion operation
            if type(chosen_edit) == DeletionOperation:
                # Deletion consumes an input token but does not produce a
                # token in the corrected word. Therefore, the target-word
                # position i and the current Earley set remain unchanged.
                continue

            # Read, replacement, and insertion each produce one token in the
            # corrected word and therefore advance the target-word position.
            earley_sets.append(self.Set())
            i += 1

            new_to_scan = {}
            # Apply read, replacement or insertion operation
            if type(chosen_edit) in [ReadOperation, ReplacementOperation, InsertionOperation]:

                if type(chosen_edit) == ReadOperation:
                    terminal = Terminal(chosen_edit.letter)
                elif type(chosen_edit) == ReplacementOperation:
                    terminal = Terminal(chosen_edit.replaced_by)
                elif type(chosen_edit) == InsertionOperation:
                    terminal = Terminal(chosen_edit.word)
                else:
                    raise Exception("Unknown edit operation.")

                for item in to_scan[terminal]:
                    new_item = item.advance()
                    earley_sets[i].add(new_item)

                    if new_item.expect in self.TERMINALS:
                        if new_item.expect in new_to_scan:
                            new_to_scan[new_item.expect].add(new_item)
                        else:
                            new_to_scan[new_item.expect] = self.Set([new_item])
            to_scan = new_to_scan

            # Complete the current Earley set by prediction and completion.
            new_to_scan = self._complete_earley_set(
                i=i, earley_sets=earley_sets, to_scan=new_to_scan
            )

        # Return the computed correction
        return word_ordered_correction.WordOrderedCorrection(correction[:-1])
