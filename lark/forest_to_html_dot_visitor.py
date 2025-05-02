from lark.parsers.earley_forest import ForestToPyDotVisitor
import networkx as nx
from pyvis.network import Network


class ForestToHtmlDotVisitor(ForestToPyDotVisitor):

    def visit(self, root, filename):
        super(ForestToPyDotVisitor, self).visit(root)

        # Convert pydot to networkx
        nx_graph = nx.nx_pydot.from_pydot(self.graph)

        # Create a pyvis Network
        net = Network(notebook=False, directed=True)
        net.from_nx(nx_graph)

        # Save as html filename
        net.show(filename, notebook=False)
