from lark.parsers.earley_forest import SymbolNode, PackedNode, TokenNode
from collections import deque


def equal_node_without_child(node1, node2):
    if node1 is None and node2 is None:
        return True

    if not type(node1) == type(node2):
        return False

    if isinstance(node1, SymbolNode) and isinstance(node2, SymbolNode):
        if node1.is_intermediate == node2.is_intermediate and node1.start == node2.start and node1.s == node2.s and node1.end == node2.end:
            return True

        else:
            return False

    if isinstance(node1, TokenNode) and isinstance(node2, TokenNode):
        if node1.token == node2.token:
            return True
        else:
            return False


def equal_children(node1: SymbolNode, node2: SymbolNode):
    if len(node1.children) != len(node2.children):
        return False

    for child in node1.children:

        pairs = []

        found = False
        for child2 in node2.children:

            if isinstance(child, PackedNode) and isinstance(child2, PackedNode):
                if child.s == child2.s and child.start == child2.start \
                        and equal_node_without_child(child.left, child2.left) \
                        and equal_node_without_child(child.right, child2.right):
                    found = True
                    pairs.append((child, child2))
            else:
                return False

        if not found:
            return False

    return pairs


def equal(root_node1, root_node2):
    if not equal_node_without_child(root_node1, root_node2):
        return False

    visited_nodes = {root_node1}

    q = deque()
    q.append((root_node1, root_node2))

    while q:
        node1, node2 = q.pop()

        if not equal_node_without_child(node1, node2):
            return False

        if isinstance(node1, SymbolNode):

            child_pairs = equal_children(node1, node2)
            if not child_pairs:
                return False

            for child1, child2 in child_pairs:
                if child1 not in visited_nodes:
                    q.append((child1.left, child2.left))
                    q.append((child1.right, child2.right))
                    visited_nodes.add(child1)

    return True
