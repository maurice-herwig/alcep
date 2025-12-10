from typing import TYPE_CHECKING, Callable, Optional, List, Any
from lark.tree import Tree
from lark.utils import OrderedSet
from lark.parsers.grammar_analysis import GrammarAnalyzer
from lark.parsers.earley_forest import StableSymbolNode, SymbolNode

if TYPE_CHECKING:
    from lark.common import LexerConf, ParserConf


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

        # Compute the set of terminals and non-terminals
        # These could be moved to the grammar analyzer. Pre-computing these is *much* faster than
        # the slow 'isupper' in is_terminal.
        self.TERMINALS = {sym for r in parser_conf.rules for sym in r.expansion if sym.is_term}
        self.NON_TERMINALS = {sym for r in parser_conf.rules for sym in r.expansion if not sym.is_term}

        # Create a dictionary for all productions rules in the form
        # key: non-terminal S value: list of rules S -> xyz
        self.predictions = {}

        # Iterate over all production rules to create the set of predictions
        for rule in parser_conf.rules:
            if rule.origin not in self.predictions:
                self.predictions[rule.origin] = [x.rule for x in analysis.expand_rule(rule.origin)]

            # Detect if any rules/terminals have priorities set.
            # The all correction earley parser don't support priorities.
            if rule.options.priority is not None:
                raise Exception("The all correction earley parser don't support priorities.")

        # Check terminals for priorities
        for term in self.lexer_conf.terminals:
            if term.priority:
                raise Exception("The all correction earley parser don't support priorities.")


    def parse(self, lexer, start):
        """
        The parse functionality of the all correction interactive earley parser.

        :param lexer: The uses lexer object.
        :param start: The start symbol of the grammar as string.

        :return: The root node of the computed correction shared packed parse forest.
        """
        raise NotImplementedError()
