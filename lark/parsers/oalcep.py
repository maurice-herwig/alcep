from lark.parsers.alcep import BaseParser

from typing import TYPE_CHECKING
from collections import deque

from lark.utils import logger
from lark.grammar import NonTerminal
from lark.parsers.earley_forest import TokenNode
from lark.parsers.earley_common import Item
from lark.lexer import TerminalDef

if TYPE_CHECKING:
    from lark.common import LexerConf, ParserConf


class OptimizedBaseParser(BaseParser):
    lexer_conf: 'LexerConf'
    parser_conf: 'ParserConf'
    debug: bool

    def __compute_q0_xi(self, start_items):
        """
        Auxiliary function to computed based on a set of items (start_items) the set q_o and x_i.

        :param start_items: The set of items with that we start to compute q_o and x_i
        :return: The sets q_o and x_i
        """

        def __add_item(item_to_add):
            """
            Auxiliary function to add an item to the sets q_0 and x_i

            :param item_to_add: The item that we want to add to above described sets.
            """
            if item_to_add not in q_0:
                q_0.add(item_to_add)
                items.append(item_to_add)
            x_i.add(item_to_add)

        # Start of the main compute_q0_and_xi method
        # Init the to calculate sets
        q_0 = self.Set(start_items)
        x_i = self.Set()

        # Held Completions (the set H).
        held_completions = set()

        # Init a queue with all start items.
        items = deque(start_items)

        # iterate over all earley items in the queue.
        while items:
            item = items.pop()

            # The earley completer rule
            if item.is_complete:
                # Because we only consider items in the first earley set each complete item can directly add to the
                # held completions set.
                held_completions.add(item.rule.origin)

                # Get for the current final item [B -> ... bullet, j, u] all items in the earley set j
                # of the form [A -> ... bullet B ...]
                originators = [originator for originator in q_0 if
                               originator.expect is not None and originator.expect == item.s]

                for originator in originators:
                    # Create a new item by shift the bullet point one postion to the right of the originator item
                    # Add the new item to the sets q_o and x_i
                    __add_item(item_to_add=originator.advance())

            # The earley predictor rule
            elif item.expect in self.NON_TERMINALS:
                # Iterate over all rule with the non-terminal, that we expect as next, on the left.
                for rule in self.predictions[item.expect]:
                    # Add the new item to the sets q_o and x_i
                    __add_item(item_to_add=Item(rule, 0, 0))

                # Process any held completions (H).
                if item.expect in held_completions:
                    # Add the new item to the sets q_o and x_i
                    __add_item(item_to_add=item.advance())

            # The insertion rule
            elif item.expect in self.TERMINALS:
                # Create a new item by shift the bullet point one postion to the right
                # Add the new item to the sets q_o and x_i
                __add_item(item_to_add=item.advance())

        # Return the computed sets
        return q_0, x_i

    def compute_nodes(self, q_0, x_i, n):
        """
        Auxiliary function to compute all nodes of the CSPPF based on the set of q_0, x_i and the length of the input
        word.

        :param q_0: The set of earley items q_0.
        :param x_i: The set of earley items x_i.
        :param n: The length of the input word.
        :return: A dictionary that contains all nodes.
        """
        # Init a dictionary that contains all symbol and intermediate nodes
        nodes_dict = {}
        for i in range(n + 1):
            nodes_dict[i] = {j: {} for j in range(i + 1)}

        # Create for each item in the first earley set one intermediate or symbol node
        for item in q_0:
            item_s = item.s

            if item.ptr == 0:
                nodes_dict[0][0][item_s] = None
            else:
                nodes_dict[0][0][item_s] = self.SymbolNode(item_s, 0, 0)

            for i in range(1, n + 1):
                nodes_dict[i][0][item_s] = self.SymbolNode(item_s, 0, i)

        # Create for each item in the set x_i all nodes
        for item in x_i:
            item_s = item.s
            for i in range(1, n + 1):
                for j in range(1, i):
                    nodes_dict[i][j][item_s] = self.SymbolNode(item_s, j, i)

                if item.ptr == 0:
                    nodes_dict[i][i][item_s] = None
                else:
                    nodes_dict[i][i][item_s] = self.SymbolNode(item_s, i, i)

        return nodes_dict

    def __compute_edges(self, q_0, x_i, nodes_dict, n, tokens):
        """
        Auxiliary method to add all edges to the CSPPF

        :param q_0: The set of earley items q_0
        :param x_i: The set of earley items x_i
        :param nodes_dict: The previous computed nodes of the CSPPF
        :param n: The length of the input word
        :param tokens: A list of tokens of the input word
        :return: None
        """

        """
        Add all edges for deletions.
        """
        from ..corrections.edit_operations import InsertionOperation, DeletionOperation, ReplacementOperation, \
            ReadOperation

        for item in q_0:
            item_s = item.s

            for i in range(n):
                # Create a deletion token node
                deletion_node = TokenNode(DeletionOperation(letter=tokens[0]), None, priority=0)

                # Get the node on that the deletion rule is applied.
                left_node = nodes_dict[i][0][item_s]

                # Add a new edge
                nodes_dict[i + 1][0][item_s].add_family(item_s, item.rule, 0, left_node, deletion_node)

        for item in x_i:
            item_s = item.s
            for i in range(1, n):
                for j in range(1, i + 1):
                    # Create a deletion token node
                    deletion_node = TokenNode(DeletionOperation(letter=tokens[0]), None, priority=0)

                    # Get the node on that the deletion rule is applied.
                    left_node = nodes_dict[i][j][item_s]

                    # Add a new edge
                    nodes_dict[i + 1][j][item_s].add_family(item_s, item.rule, j, left_node, deletion_node)

        """
        Add all edges for insertions
        """
        for item in q_0:

            if item.expect in self.TERMINALS:
                item_s = item.s
                item_advance_s = item.advance().s

                # Create a label for the insertion node
                ins_terminal = self.lexer_conf.terminals_by_name.get(item.expect.name)
                ins_string = ins_terminal.pattern.value if isinstance(ins_terminal,
                                                                      TerminalDef) else item.expect.name

                for i in range(n + 1):
                    # Create a insertion token node
                    insertion_node = TokenNode(InsertionOperation(ins_string), None, priority=0)

                    # Get the node on that the deletion rule is applied.
                    left_node = nodes_dict[i][0][item_s]

                    # Add a new edge
                    nodes_dict[i][0][item_advance_s].add_family(item_advance_s, item.rule, 0, left_node, insertion_node)

        for item in x_i:
            if item.expect in self.TERMINALS:
                item_s = item.s
                item_advance_s = item.advance().s

                # Create a label for the insertion node
                ins_terminal = self.lexer_conf.terminals_by_name.get(item.expect.name)
                ins_string = ins_terminal.pattern.value if isinstance(ins_terminal,
                                                                      TerminalDef) else item.expect.name

                for i in range(n + 1):
                    for j in range(1, i + 1):
                        # Create a insertion token node
                        insertion_node = TokenNode(InsertionOperation(ins_string), None, priority=0)

                        # Get the node on that the insertion rule is applied.
                        left_node = nodes_dict[i][j][item_s]

                        # Add a new edge
                        nodes_dict[i][j][item_advance_s].add_family(item_advance_s, item.rule, j, left_node,
                                                                    insertion_node)
        """
        Add all edges for replacement and read
        """
        for item in q_0:

            expect_terminal = item.expect

            if expect_terminal in self.TERMINALS:
                item_s = item.s
                item_advance_s = item.advance().s

                # Create a label for the possible replacement node
                ins_terminal = self.lexer_conf.terminals_by_name.get(item.expect.name)
                ins_string = ins_terminal.pattern.value if isinstance(ins_terminal,
                                                                      TerminalDef) else item.expect.name

                for i in range(n):

                    token_i = tokens[i]

                    # The scanner rule
                    if self.term_matcher(item.expect, token_i):
                        # Create a read token node
                        operation_node = TokenNode(ReadOperation(letter=token_i), None, priority=0)

                    # The replacement rule
                    else:
                        # Create a replacement token node
                        operation_node = TokenNode(ReplacementOperation(letter=token_i, replaced_by=ins_string),
                                                   None, priority=0)

                    # Get the node on that the read or replacement rule is applied.
                    left_node = nodes_dict[i][0][item_s]

                    # Add a new edge
                    nodes_dict[i + 1][0][item_advance_s].add_family(item_advance_s, item.rule, 0, left_node,
                                                                    operation_node)

        for item in x_i:
            expect_terminal = item.expect

            if expect_terminal in self.TERMINALS:
                item_s = item.s
                item_advance_s = item.advance().s

                # Create a label for the possible replacement node
                ins_terminal = self.lexer_conf.terminals_by_name.get(item.expect.name)
                ins_string = ins_terminal.pattern.value if isinstance(ins_terminal,
                                                                      TerminalDef) else item.expect.name

                for i in range(n):
                    token_i = tokens[i]

                    for j in range(1, i + 1):

                        # The scanner rule
                        if self.term_matcher(item.expect, token_i):
                            # Create a read token node
                            operation_node = TokenNode(ReadOperation(letter=token_i), None, priority=0)

                        # The replacement rule
                        else:
                            # Create a replacement token node
                            operation_node = TokenNode(ReplacementOperation(letter=token_i, replaced_by=ins_string),
                                                       None, priority=0)

                        # Get the node on that the read or replacement rule is applied.
                        left_node = nodes_dict[i][j][item_s]

                        # Add a new edge
                        nodes_dict[i + 1][j][item_advance_s].add_family(item_advance_s, item.rule, j, left_node,
                                                                        operation_node)
        """
        Add all edges for completer
        """
        for item in q_0:

            if item.is_complete:
                item_s = item.s

                for item2 in q_0:
                    if item2.expect is not None and item2.expect == item_s:
                        item2_s = item2.s
                        new_item = item2.advance()
                        new_advance_s = new_item.s

                        # left node
                        left_node = nodes_dict[0][0][item2_s]

                        for i in range(n + 1):
                            # right node
                            right_node = nodes_dict[i][0][item_s]

                            # Add a new edge
                            nodes_dict[i][0][new_advance_s].add_family(new_advance_s, new_item.rule, 0, left_node,
                                                                       right_node)

        for item in x_i:

            if item.is_complete:
                item_s = item.s

                for item2 in x_i:
                    if item2.expect is not None and item2.expect == item_s:
                        item2_s = item2.s
                        new_item = item2.advance()
                        new_advance_s = new_item.s

                        for i in range(n + 1):
                            for j in range(1, i + 1):

                                # right node
                                right_node = nodes_dict[i][j][item_s]

                                for k in range(1, j + 1):
                                    # left node
                                    left_node = nodes_dict[j][k][item2_s]

                                    # Add a new edge
                                    nodes_dict[i][k][new_advance_s].add_family(new_advance_s, new_item.rule, k,
                                                                               left_node, right_node)

                for item2 in q_0:
                    if item2.expect is not None and item2.expect == item_s:
                        item2_s = item2.s
                        new_item = item2.advance()
                        new_advance_s = new_item.s

                        for i in range(n + 1):
                            for j in range(1, i + 1):
                                # right node
                                right_node = nodes_dict[i][j][item_s]

                                # left node
                                left_node = nodes_dict[j][0][item2_s]

                                # Add a new edge
                                nodes_dict[i][0][new_advance_s].add_family(new_advance_s, new_item.rule, 0,
                                                                           left_node, right_node)

    def parse(self, lexer, start):
        """
        The parse functionality of the optimized all correction earley parser.

        :param lexer: The uses lexer object.
        :param start: The start symbol of the grammar as string.

        :return: The root node of the computed correction shared packed parse forest.
        """
        # Assert that the start symbol is set.
        assert start, start

        # Create a non-terminal object for the start symbol.
        start_symbol = NonTerminal(start)

        # Create a set that contains all start items
        start_items = self.Set()

        # Init the first earley set and the set to_scan by predict for the start_symbol.
        for rule in [r for r in self.predictions[start_symbol] if r.origin == start_symbol]:
            # Create af earley Item for the current rule
            item = Item(rule, 0, 0)

            # Add the item to the current earley set
            start_items.add(item)

        # Compute the tokens of the input word and the length of the input word
        tokens = [token for token in lexer.lex({})]
        n = len(tokens)

        # 1. Compute the first earley set and the set X_i
        q_0, x_i = self.__compute_q0_xi(start_items=start_items)

        # 2. Compute all intermediate and symbol nodes of the CSPPF
        nodes_dict = self.compute_nodes(q_0=q_0, x_i=x_i, n=n)

        # 3. Compute all edges and edit operations
        self.__compute_edges(q_0=q_0, x_i=x_i, nodes_dict=nodes_dict, n=n, tokens=tokens)

        # Get the root node of the CSPPF
        root_node = nodes_dict[n][0][start_symbol]

        # If the debug mode is one try to crate for the solution a csppf png image.
        if self.debug:
            from lark.forest_to_html_dot_visitor import ForestToHtmlDotVisitor
            try:
                debug_walker = ForestToHtmlDotVisitor()
            except ImportError:
                logger.warning("Cannot find dependency 'pydot', will not generate csppf debug image")
            else:
                debug_walker.visit(root_node, f"sppf.html")

        return root_node
