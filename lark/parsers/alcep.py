import copy
from typing import TYPE_CHECKING, Callable, Optional, List, Any
from collections import deque

from lark.lexer import TerminalDef
from lark.tree import Tree
from lark.utils import OrderedSet, dedup_list, logger
from lark.grammar import NonTerminal

from lark.parsers.grammar_analysis import GrammarAnalyzer
from lark.parsers.earley_forest import StableSymbolNode, SymbolNode, TokenNode
from lark.parsers.earley_common import Item

from lark.corrections.edit_operations import InsertionOperation, DeletionOperation, ReplacementOperation, ReadOperation

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

    def compute_earley_set(self, i: int, to_scan: set | OrderedSet, earley_sets: list, node_cache: dict):
        """
        Auxiliary function that consists the applying of the completer, predictor and insertion rule to the
        current computed earley set.
        """

        def __add_item(item_to_add):
            """
            Auxiliary function to add an item to the current earley and the items queue if it is not in the current
            earley set. Additionally, the item is also add to the to_scan set if the next expected terminal/
            non-terminal a terminal symbol.

            :param item_to_add: The item that we want to add to above described sets.
            """
            if item_to_add not in current_earley_set:
                current_earley_set.add(item_to_add)
                items.append(item_to_add)

            if item_to_add.expect in self.TERMINALS:
                to_scan.add(item_to_add)

        # Start of the __ compute_earley_set function.
        # Held Completions (the set H).
        held_completions = {}

        # Get a pointer to the current computed earley set
        current_earley_set = earley_sets[i]

        # Init a queue with all items of the current earley set (the set R).
        items = deque(current_earley_set)

        # iterate over all earley items in queue (all items of the current earley set).
        while items:

            item = items.pop()

            # The earley completer rule
            if item.is_complete:

                # Check if no node already assign to the final earley item. If this the case create a symbol node
                # and set them as the item node.
                if item.node is None:
                    label = (item.s, item.start, i)
                    item.node = node_cache[label] if label in node_cache \
                        else node_cache.setdefault(label, self.SymbolNode(*label))
                    item.node.add_family(item.s, item.rule, item.start, None, None)

                # TODO eventuell sinnvoll hier den transitiven completer step von R Joop Leo einzubauen.
                # (https://www.sciencedirect.com/science/article/pii/030439759190180A?ref=pdf_download&fr=RR-2&rr=8e47b1066e67e527)
                # Allerdings wurde dieser nachträglich auch aus der lark generalised version rausgenommen.

                # Regular Earley completer
                # If the also starts at this earley set, we need add this item to the set of held_completions,
                # because all Earley items that are subsequently calculated for the current earley set can possibly
                # be completed with the final item.
                if item.start == i:
                    held_completions[item.rule.origin] = item.node

                # Get for the current final item [B -> ... bullet, j, u] all items in the earley set j
                # of the form [A -> ... bullet B ...]
                originators = [originator for originator in earley_sets[item.start] if
                               originator.expect is not None and originator.expect == item.s]

                for originator in originators:
                    # Create a new item by shift the bullet point one postion to the right of the originator item
                    new_item = originator.advance()

                    # Create the label for the CSPPF node
                    label = (new_item.s, originator.start, i)
                    # Set the node of the new item
                    new_item.node = node_cache[label] if label in node_cache \
                        else node_cache.setdefault(label, self.SymbolNode(*label))

                    # Add the item.node and the originator node as a family of the new node
                    new_item.node.add_family(new_item.s, new_item.rule, originator.start, originator.node, item.node)

                    # Add the new item to the sets.
                    __add_item(item_to_add=new_item)

            # The earley predictor rule
            elif item.expect in self.NON_TERMINALS:

                # Iterate over all rule with the non-terminal, that we expect as next, on the left.
                for rule in self.predictions[item.expect]:
                    new_item = Item(rule, 0, i)

                    # Add the new item to the sets.
                    __add_item(item_to_add=new_item)

                # Process any held completions (H).
                if item.expect in held_completions:
                    new_item = item.advance()
                    label = (new_item.s, item.start, i)
                    new_item.node = node_cache[label] \
                        if label in node_cache else node_cache.setdefault(label, self.SymbolNode(*label))
                    new_item.node.add_family(new_item.s, new_item.rule, new_item.start, item.node,
                                             held_completions[item.expect])

                    # Add the new item to the sets.
                    __add_item(item_to_add=new_item)

            # The insertion rule
            elif item.expect in self.TERMINALS:
                # Create a new item by shift the bullet point one postion to the right
                new_item = item.advance()

                # Create the label for the CSPPF node
                label = (new_item.s, new_item.start, i)

                # Create a label for the insertion node
                ins_terminal = self.lexer_conf.terminals_by_name.get(item.expect.name)
                ins_string = ins_terminal.pattern.value if isinstance(ins_terminal,
                                                                      TerminalDef) else item.expect.name

                ins_token = InsertionOperation(ins_string)

                # Create an insertion token node
                ins_node = TokenNode(ins_token, None, priority=0)

                # Set the node of the new item
                new_item.node = node_cache[label] if label in node_cache \
                    else node_cache.setdefault(label, self.SymbolNode(*label))

                # Add the item.node and the new ins_node as a family of the new node
                new_item.node.add_family(new_item.s, item.rule, new_item.start, item.node, ins_node)

                # Add the new item to the sets.
                __add_item(item_to_add=new_item)

    def scanner_rule(self, i, item, token, node_cache):
        """
        Auxiliary function to apply the scanner rule.
        """
        # Create a new item by shift the bullet point one postion to the right.
        new_item = item.advance()

        # Create the label for the CSPPF node
        label = (new_item.s, new_item.start, i + 1)

        # Create a label for the read node.
        read_token = ReadOperation(letter=token)

        # Create a read token node.
        read_node = TokenNode(read_token, None, priority=0)

        # Set the node of the new item.
        new_item.node = node_cache[label] if label in node_cache \
            else node_cache.setdefault(label, self.SymbolNode(*label))

        # Add the item.node and the new read_node as a family of the new node.
        new_item.node.add_family(new_item.s, item.rule, new_item.start, item.node, read_node)

        # Return the new item
        return new_item

    def replacement_rule(self, i, item, token, node_cache):
        """
        Auxiliary function to apply the replacement rule.
        """
        # Create a new item by shift the bullet point one postion to the right
        new_item = item.advance()

        # Create the label for the CSPPF node
        label = (new_item.s, new_item.start, i + 1)

        # Create a label for the replacement node
        ins_terminal = self.lexer_conf.terminals_by_name.get(item.expect.name)
        ins_string = ins_terminal.pattern.value if isinstance(ins_terminal,
                                                              TerminalDef) else item.expect.name
        replacement_token = ReplacementOperation(letter=token, replaced_by=ins_string)

        # Create a replacement token node
        replacement_node = TokenNode(replacement_token, None, priority=0)

        # Set the node of the new item
        new_item.node = node_cache[label] if label in node_cache \
            else node_cache.setdefault(label, self.SymbolNode(*label))

        # Add the item.node and the new replacement_node as a family of the new node
        new_item.node.add_family(new_item.s, item.rule, new_item.start, item.node, replacement_node)

        # Return the new item
        return new_item

    def deletion_rule(self, i, item, token, node_cache):
        """
        Auxillary function to apply the deletion rule.
        """
        new_item = copy.copy(item)

        # Create the label for the CSPPF node
        label = (new_item.s, new_item.start, i + 1)

        # Create a label for the deletion node
        deletion_token = DeletionOperation(letter=token)

        # Create a deletion token node
        deletion_node = TokenNode(deletion_token, None, priority=0)

        # Set the node of the new item
        new_item.node = node_cache[label] if label in node_cache \
            else node_cache.setdefault(label, self.SymbolNode(*label))

        # Add the item.node and the new deletion_node as a family of the new node
        new_item.node.add_family(new_item.s, item.rule, new_item.start, item.node, deletion_node)

        # Return the new item
        return new_item

    def _init_next_earley_set(self, i: int, to_scan: set | OrderedSet, next_to_scan: set | OrderedSet,
                              earley_sets: list, node_cache: dict, token):
        """
        Auxiliary function that consists the applying of the scanner, replacement and deletion rule to the
        current computed earley set.
        """

        def __add_item(item_to_add):
            """
            Auxiliary function to add an item to the current earley and the items queue if it is not in the current
            earley set. Additionally, the item is also add to the next_to_scan set if the next expected terminal/
            non-terminal a terminal symbol.

            :param item_to_add: The item that we want to add to above described sets.
            """
            # Add the new item to the next set.
            next_set.add(item_to_add)

            # If a terminal symbol on the right of the bullet point add the item to the set to
            # scan for the next earley set initialisation.
            if item_to_add.expect in self.TERMINALS:
                next_to_scan.add(item_to_add)

        # Start to of the _init_next_earley_set function.

        # Init the next earley set.
        next_set = self.Set()
        earley_sets.append(next_set)

        # Iterate over all items that have right to the bullet point a terminal symbol.
        for item in to_scan:

            # The scanner rule
            if self.term_matcher(item.expect, token):
                __add_item(self.scanner_rule(i=i, item=item, token=token, node_cache=node_cache))

            # The replacement rule
            else:
                __add_item(self.replacement_rule(i=i, item=item, token=token, node_cache=node_cache))

        # The deletion rule
        # Iterate over all items of the current earley set
        for item in earley_sets[i]:
            __add_item(self.deletion_rule(i=i, item=item, token=token, node_cache=node_cache))

    def _parse(self, lexer, earley_sets, to_scan, start_symbol):
        """
        Auxiliary function which performs the complete parse process after the initialisation of the first earley set.

        :param lexer: The uses lexer object.
        :param earley_sets: A Map of all earley sets. Key: set number, value: the set itself.
        :param to_scan: A set with all earley items of the first earley set, where terminal/ non-terminal
                        to the right of the bullet point is a terminal.
        :param start_symbol: The start symbol of the grammar as string.
        """

        # Crate a dict that contains all nodes off the CSPPF. Key: the node label, value: the node object.
        node_cache = {}

        # Init a list of items of the next earley set with a terminal to the right of the bullet point.
        # The set N' in the all correction earley parser.
        next_to_scan = self.Set()

        # The index of the current Earley Set
        i = 0

        # The main Earley loop
        # Iterate over all tokens of the input word.
        for token in lexer.lex({item.expect for item in to_scan}):
            # Init the Sets for this parse step
            to_scan = next_to_scan
            next_to_scan = self.Set()

            # Apply the predictor, completer and insertion rule as long as possible to the current earley set.
            self.compute_earley_set(i=i, to_scan=to_scan, earley_sets=earley_sets, node_cache=node_cache)

            # Apply the scanner, replacement and deletion rule to the current earley set to init the next set.
            self._init_next_earley_set(i=i, to_scan=to_scan, next_to_scan=next_to_scan, earley_sets=earley_sets,
                                       node_cache=node_cache, token=token)

            # Update the index of the earley set.
            i += 1

        # Apply the predictor, completer and insertion rule after the last token.
        self.compute_earley_set(i=i, to_scan=to_scan, earley_sets=earley_sets, node_cache=node_cache)

        # Assert that all Earley Sets are computed
        assert i == len(earley_sets) - 1

    def parse(self, lexer, start):
        """
        The parse functionality of the all correction earley parser.

        :param lexer: The uses lexer object.
        :param start: The start symbol of the grammar as string.

        :return: The root node of the computed correction shared packed parse forest.
        """
        # Assert that the start symbol is set.
        assert start, start

        # Create a non-terminal object for the start symbol.
        start_symbol = NonTerminal(start)

        # Init a list of the earley sets
        earley_sets = [self.Set()]

        # Init a list of items of the current set with a terminal to the right of the bullet point.
        # The set N in the all correction earley parser.
        to_scan = self.Set()

        # Init the first earley set and the set to_scan by predict for the start_symbol.
        for rule in self.predictions[start_symbol]:

            # Create af earley Item for the current rule
            item = Item(rule, 0, 0)

            # Add the item to the current earley set
            earley_sets[0].add(item)

            # Check if the next terminal/non-terminal after the bullet point a terminal.
            if item.expect in self.TERMINALS:
                to_scan.add(item)

        # Start the main parse process
        self._parse(lexer, earley_sets=earley_sets, to_scan=to_scan, start_symbol=start)

        # If the parse was successful, the start
        # symbol should have been completed in the last step of the earley cycle, and will be in
        # this earley set. Find the item for the start_symbol, which is the root of the SPPF tree.
        solutions = dedup_list(n.node for n in earley_sets[-1] if
                               n.is_complete and n.node is not None and n.s == start_symbol and n.start == 0)

        # The all correction earley parser always compute a solution if the grammar is not empty.
        if not solutions:
            raise Exception("The all correction earley parser is incorrect implemented "
                            "or the given grammar represents die empty language. ")

        # If the debug mode is one try to crate for the solution a csppf png image.
        if self.debug:
            from lark.forest_to_html_dot_visitor import ForestToHtmlDotVisitor
            try:
                debug_walker = ForestToHtmlDotVisitor()
            except ImportError:
                logger.warning("Cannot find dependency 'pydot', will not generate csppf debug image")
            else:
                for i, s in enumerate(solutions):
                    debug_walker.visit(s, f"csppf{i}.html")

        return solutions[0]
