from lark.utils import OrderedSet
from lark.parsers.earley_forest import SymbolNode, TokenNode, PackedNode
from collections import deque, defaultdict
from corrections.edit_operations import InsertionOperation, ReplacementOperation, ReadOperation
from corrections.word_ordered_correction import WordOrderedCorrection
from corrections.word_ordered_correction_with_counter_of_edits import WordOrderedCorrectionWithCounterOfEdits
from itertools import product

import corrections.constants as constants


class CSPPFToCorrectionTransformer:

    def __init__(self, only_simplified: bool = False,
                 only_smallest: bool = True,
                 smallest_dynamically: bool = False,
                 ordered_sets: bool = True,
                 corrections_with_edit_counter: bool = False,
                 max_number_of_insertions: int = -1,
                 max_number_of_replacement: int = -1,
                 max_number_of_deletions: int = -1,
                 max_number_of_edits=-1):
        """
        The constructor of an CSPPFToCorrectionTransformer.
        Such an object can compute all indexless corrections that are stored in a CSPPF (we use a Lark forest with
        special token nodes see edit_operations.py) without a node in the CSPPF appearing more than once in the
        derivation of a correction.

        :param only_simplified: If this parameter is true, then the algorithm calculates only indexless corrections,
                which are simplified.
        :param only_smallest: If this parameter is true, the algorithm only calculates indexless corrections so that no
            sub-correction for this correction is also saved in the CSPPF.
        :param smallest_dynamically: If this parameter is true and the only_smallest parameter is also true, then
            the algorithm removes all non-smallest corrections after calculating all indexless corrections that can be
            derived from a node. If this parameter is false and the only_smallest parameter is true, then the algorithm
            removes all non-smallest corrections after computing of all corrections (the computation of the root node).
        :param ordered_sets: A boolean if ordered sets are used instead of normal sets.
        :param corrections_with_edit_counter: A boolean if corrections with edit operation counter are used or normal
            indexless corrections.
        :param max_number_of_insertions: The maximum number of insertion operations that a correction may have.
            Parameter is only taken into account if corrections with edit counter are used.
        :param max_number_of_replacement: The maximum number of replacement operations that a correction may have.
            Parameter is only taken into account if corrections with edit counter are used.
        :param max_number_of_deletions: The maximum number of deletion operations that a correction may have. Parameter
            is only taken into account if corrections with edit counter are used.
        :param max_number_of_edits: The maximum number of edit operations that a correction may have. Parameter is only
            taken into account if corrections with edit counter are used.
        """

        # Set the attributes.
        self.corrections = defaultdict(dict)
        self.only_simplified = only_simplified
        self.only_smallest = only_smallest
        self.smallest_dynamically = smallest_dynamically
        self.Set = OrderedSet if ordered_sets else set
        self.use_corrections_with_edit_counter = corrections_with_edit_counter

        # If we use corrections with a counter of the edit operations, set the class variables for the maximum number
        # of each operation of the IndexlessCorrectionWithCounterOfEdits class.
        if self.use_corrections_with_edit_counter:
            WordOrderedCorrectionWithCounterOfEdits.max_number_of_edits = max_number_of_edits
            WordOrderedCorrectionWithCounterOfEdits.max_number_of_insertions = max_number_of_insertions
            WordOrderedCorrectionWithCounterOfEdits.max_number_of_replacement = max_number_of_replacement
            WordOrderedCorrectionWithCounterOfEdits.max_number_of_deletions = max_number_of_deletions

    def transform(self, root):
        """
        Transform a correction shared packed parse forst (CSPPF) to the set of corrections, that can be derived from
        the CSPPF without loops.

        :param root: The root node of the CSPPF
        :return: The set of corrections.
        """
        assert isinstance(root, SymbolNode), \
            "The CSPPFToCorrectionTransformer can only compute the set of corrections for an SymbolNode"

        # Call the super visit method, this method organises the visit of all nodes in and out.
        self.__visit(root=root)

        # Get the corrections for the root node.
        corrections = self.corrections[hash(root)].get(None, self.Set())

        # If we only want the smallest corrections, and we have not dynamically removed the non-smallest corrections,
        # then we need just now to remove all non-smallest corrections.
        if self.only_smallest and not self.smallest_dynamically:
            return self.__compute_smallest_corrections(set_of_corrections=corrections)

        return corrections

    def __visit(self, root):
        """
        Auxiliary method that organise the visit of all nodes in the CSPPF in a certain order.

        :param root: The root node of the CSPPF on that the visiting starts.
        :return: None
        """
        # Visiting is a list of tuples of the hash value of a node and a path, to the node since the first symbol node
        # with start == end, currently in the stack. It serves two purposes: to detect when we 'recurse' in and out
        # of a symbol/intermediate so that we can process both up and down. Also, since the CSPPF can have cycles it
        # allows us to detect if we're trying to recurse into a node that's already on the stack (infinite recursion).
        visiting = self.Set()

        # Set of all symbol/intermediate and packed that have been visited
        visited = self.Set()

        # Set of all visited token nodes
        visited_token_nodes = self.Set()

        # A list of nodes that are currently being visited. Used to detect cycle.
        path = []

        # We do not use recursion here to walk the Forest due to the limited stack size in python.
        # Therefore, input_stack is essentially our stack. We initialise them with the root node and not yet a specific
        # path starting from the first symbol node with start == end.
        input_stack = deque([(root, None)])

        # It is much faster to cache these as locals since they are called many times in large parses.
        vis_packed_node_out = getattr(self, 'visit_packed_node_out')
        vis_packed_node_in = getattr(self, 'visit_packed_node_in')
        vis_symbol_node_out = getattr(self, 'visit_symbol_node_out')
        vis_symbol_node_in = getattr(self, 'visit_symbol_node_in')
        vis_token_node = getattr(self, 'visit_token_node')

        # As long as the stack is not empty, visit the next node/the next iterable object.
        while input_stack:

            # Get the next object from the input_stack.
            # This is either a tuple consists of a node and a specific path to this node, a generator object or
            # an iterable list.
            current_object = next(reversed(input_stack))

            try:
                # Try to get the next object from the generator/iterator object.
                next_object = next(current_object)
            except StopIteration:
                # If the iterator reach the end, remove it from the stack.
                input_stack.pop()
                continue
            except TypeError:
                # If the current_object is not an iterator, the current_object is a tuple consists of a node and a path.
                current_node, path_to_current_node = current_object
            else:

                # Check that the next object is not none
                if next_object is None:
                    continue

                # Get the node and the path to this node of the next object.
                # Note that the path_to_the_next_node contains instead of the path only symbol nodes. Thereby the
                # sequence of symbol nodes are enough to identify the part unique.
                next_node, path_to_next_node = next_object

                # Check if this tuple are already visited.
                if (hash(next_node), path_to_next_node) in visiting or next_node in path:
                    continue

                # If we have get successfully the next object from the stack, add this object at first element to the
                # stack such that by the next call of the reversed input stack this element are get.
                input_stack.append(next_object)
                continue

            # Note that this code are only reached if the above try except block ens with a type error, therefore the
            # current_node is set.
            # Check if the current_node is a TokenNode (wich represent in our case an edit operation). Is this the case
            # we can visit this node, because each TokenNode are only visited once.
            if isinstance(current_node, TokenNode):

                hash_value_current_node = hash(current_node)

                # If the node not already visited, visit it.
                if hash_value_current_node not in visited_token_nodes:
                    vis_token_node(node=current_node.token)
                    visited_token_nodes.add(hash_value_current_node)

                # Remove the token node from the input stack and
                input_stack.pop()
                continue

            # The id of the current object, to check if it is already visited.
            current_id = (id(current_node), path_to_current_node)

            # Check if the current_node with the current path is visited exactly one. Then this time the out visit
            # method of this node is visited.
            if current_id in visiting:

                # Depending on the node type call the responding out visit method.
                if isinstance(current_node, PackedNode):
                    vis_packed_node_out(node=current_node, path_to_node=path_to_current_node)
                # In our use case intermediate nodes are also symbol nodes.
                else:
                    vis_symbol_node_out(node=current_node, path_to_node=path_to_current_node)

                # Remove the current node from the stack and shorten the path from the root node to the current node
                # by one.
                input_stack.pop()
                path.pop()

                # Remove the current object from the set of objects that are visited only once and add it to the set of
                # that are already visited twice.
                visiting.remove(current_id)
                visited.add(current_id)

            # If the current object are already visited twice, we have nothing to do for it.
            elif current_id in visited:
                input_stack.pop()

            # If the note don't visited up to now, call the corresponding visit in method.
            else:

                # Add the current object to the nodes that are visited exactly once.
                visiting.add(current_id)

                # Add the current node to the path from the root node to the current node.
                path.append(current_node)

                # Depending on the node type call the responding out visit method.
                if isinstance(current_node, PackedNode):
                    next_object = vis_packed_node_in(node=current_node, path_to_node=path_to_current_node)
                # In our case intermediate nodes are also symbol nodes.
                else:
                    next_object = vis_symbol_node_in(node=current_node, path_to_node=path_to_current_node)

                # Add the next_object at the end of the input stack.
                input_stack.append(next_object)

    def visit_packed_node_in(self, node: PackedNode, path_to_node: tuple = None):
        """
        This visit method is called if no child has visited this node yet. Therefore, this method create only a
        yield of the left and right child.

        :param node: The visited node of type PackedNode (see lark.earley_forest).
        :param path_to_node: The path to this node.
        :return: None
        """

        # The left child does not necessarily have to exist.
        if node.left:
            yield node.left, path_to_node

        # The right child must exist. But if we use the dynamic parse process, it can happen that they are packed with
        # node without a right child.
        if node.right:
            yield node.right, path_to_node

    def visit_packed_node_out(self, node: PackedNode, path_to_node: tuple = None):
        """
        The visit method of a packed node.
        This visit method is called after that all children of this node are also visited (in and out).

        This method calculates all corrections that can be derived from the given node by forming the cross product of
        all corrections of the left child and all corrections of the right child.

        :param node: The visited node of type PackedNode (see lark.earley_forest).
        :param path_to_node: The path to this node.
        :return: None
        """

        # Get the sets of the right and the left children.
        # The right child of a packed node always exists.
        hash_value_node_right = hash(node.right)
        if isinstance(node.right, TokenNode):
            if None not in self.corrections[hash_value_node_right]:
                return
            right_corrections = self.corrections[hash_value_node_right][None]

        else:
            if path_to_node not in self.corrections[hash_value_node_right]:
                return
            right_corrections = self.corrections[hash_value_node_right][path_to_node]

        # The left child does not necessarily have to exist.
        if node.left:
            hash_value_node_left = hash(node.left)
            # Note the left node cannot be from type TokenNode
            if path_to_node not in self.corrections[hash_value_node_left]:
                return
            left_corrections = self.corrections[hash_value_node_left][path_to_node]

        else:
            self.corrections[hash(node)][path_to_node] = right_corrections
            return

        # Compute the cross product of all corrections of the left child and all corrections of the right child.
        at_least_one = False
        corrections = self.Set()
        for (left_correction, right_correction) in product(left_corrections, right_corrections):
            new_correction = left_correction.concatenate(other=right_correction, simplify=self.only_simplified)
            if new_correction:
                corrections.add(new_correction)
                at_least_one = True

        # If at least one correction is calculated, add the set of corrections to the corrections dict self.corrections.
        if at_least_one:

            # Eventually remove all non smallest corrections from the set of corrections, by using the auxiliary
            # function __compute_smallest_corrections.
            if self.only_smallest and self.smallest_dynamically:
                self.corrections[hash(node)][path_to_node] = self.__compute_smallest_corrections(
                    set_of_corrections=corrections)
            else:
                self.corrections[hash(node)][path_to_node] = corrections

    def visit_symbol_node_in(self, node: SymbolNode, path_to_node: tuple = None):
        """
        The visit method of a symbol (and intermediate) node.
        This visit method is called if no child has visited this node yet. Therefore, this method create iterable object
        of the node children (a set of packe node).

        :param node: The visited node of type PackedNode (see lark.earley_forest).
        :param path_to_node: The path to this node.
        :return: An iterable object of the node children (a set of packe node).
        """
        if path_to_node:
            new_path_to_node = path_to_node + (node,)
        else:
            if node.start == node.end:
                new_path_to_node = (node,)
            else:
                new_path_to_node = None
        return iter([(child, new_path_to_node) for child in node.children])

    def visit_symbol_node_out(self, node: SymbolNode, path_to_node: tuple = None):
        """ The visit method of a symbol (and intermediate) node.
        This visit method is called after that all children of this node are also visited (in and out).

        This method calculates all corrections that can be derived from the given node by union the corrections that
        can be derived from the children (packed node).


        :param node: The visited node of type PackedNode (see lark.earley_forest).
        :param path_to_node: The path to this node.
        :return: None
        """
        if path_to_node:
            new_path_to_node = path_to_node + (node,)
        else:
            if node.start == node.end:
                new_path_to_node = (node,)
            else:
                new_path_to_node = None

        at_least_one = False
        corrections = self.Set()

        # Iterate over all children and at there set of corrections to the corrections set.
        for child in node.children:
            hash_value_child = hash(child)
            if new_path_to_node in self.corrections[hash_value_child]:
                corrections = corrections.union(self.corrections[hash_value_child][new_path_to_node])
                at_least_one = True

        # If at least one correction is calculated, add the set of corrections to the corrections dict self.corrections.
        if at_least_one:

            # Eventually remove all non smallest corrections from the set of corrections, by using the auxiliary
            # function __compute_smallest_corrections.
            if self.only_smallest and self.smallest_dynamically:
                self.corrections[hash(node)][path_to_node] = self.__compute_smallest_corrections(
                    set_of_corrections=corrections)
            else:
                self.corrections[hash(node)][path_to_node] = corrections

    def visit_token_node(self, node: TokenNode):
        """
        The visit method of a token node.
        As token nodes are the leaves of the CSPPF, they are only visited once, unlike the other node types.

        :param node: The visited node of type EditOperation (see corrections.edit_operations.py)
        :return: None
        """

        corrections = self.Set()

        # Create an Indexless correction for the token node.
        if self.use_corrections_with_edit_counter:
            # In the case that we use indexless corrections with counter of edit operations, in addition to the creation
            # of a new indexless correction initialise the counters.
            match node:
                case InsertionOperation():
                    new_corrections = WordOrderedCorrectionWithCounterOfEdits([node])
                    new_corrections.counter_of_insertions = 1
                case ReplacementOperation():
                    new_corrections = WordOrderedCorrectionWithCounterOfEdits(
                        [InsertionOperation(word=""), node, InsertionOperation(word="")])
                    new_corrections.counter_of_replacements = 1
                case ReadOperation():

                    # TODO eventuell geht es auch einfacher als eine die read operation aufzutrennen
                    operations = [InsertionOperation(word="")]
                    for char in node.letter:
                        operations += [ReadOperation(letter=char), InsertionOperation(word="")]

                    new_corrections = WordOrderedCorrectionWithCounterOfEdits(operations)

                case _:
                    new_corrections = WordOrderedCorrectionWithCounterOfEdits(
                        [InsertionOperation(word=""), node, InsertionOperation(word="")])
                    new_corrections.counter_of_deletions = 1

            corrections.add(new_corrections)
        else:
            match node:
                case InsertionOperation():
                    corrections.add(WordOrderedCorrection([node]))
                case _:
                    corrections.add(
                        WordOrderedCorrection([InsertionOperation(word=""), node, InsertionOperation(word="")]))

        self.corrections[hash(node)][None] = corrections

    def __compute_smallest_corrections(self, set_of_corrections):
        """ Auxiliary function to calculate the set of the smallest corrections for the given set of corrections.
        A correction is the smallest corresponding to the given set if there is no correction in the set that is
        smaller. A correction is smaller than another fixup if they are all equal or smaller and at least one is really
        smaller. For the cases where an edit operation is smaller than another edit operation see edit_operation.py.

        :param set_of_corrections: The set of corrections for that we want to compute the set of the smallest
            corrections.
        :return: The set of the smallest corrections.
        """

        # The set of the computed the smallest corrections
        smallest_corrections = self.Set()

        # Create a copy of the given set of corrections, so that the set is not changed outside of this method.
        # From this set we remove each correction for that we have found a sub-correction.
        possible_smallest = set_of_corrections.copy()

        # Also crate an iterable list of the given set. Note that the constructor of a list create also a copy.
        possible_smallest_list = list(set_of_corrections)

        # Iterate over all corrections in the set of possible smallest list. Note that the list is not changed in the
        # loop body.
        for i, correction1 in zip(range(len(possible_smallest_list)), possible_smallest_list):

            # If the correction is already removed from the set of possible smallest corrections. We don't need to check
            # if the current correction one of the smallest correction.
            if correction1 in possible_smallest:

                exist_no_smaller = True

                # Iterate over all other possible smallest corrections to check if one of them a sub-correction, then
                # the current correction cannot one of the smallest corrections.
                for j in range(i + 1, len(possible_smallest_list)):

                    correction2 = possible_smallest_list[j]

                    # Compare correction1 and correction2 if one of them smaller than another, then we can remove the
                    # smaller one from the set of the possible smallest corrections. Additionally, if correction2 is
                    # smaller, then we know that correction1 cannot one of the smallest corrections.
                    match correction1.compare(correction2):
                        case constants.CORRECTION_SMALLER:
                            if correction2 in possible_smallest:
                                possible_smallest.remove(correction2)
                        case constants.CORRECTION_BIGGER:
                            possible_smallest.remove(correction1)
                            exist_no_smaller = False
                            break

                if exist_no_smaller:
                    smallest_corrections.add(correction1)

        return smallest_corrections
