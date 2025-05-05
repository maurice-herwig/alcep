from lark import Lark
import itertools
import timeit
from lark.corrections.utils.equality_of_correction_sppfs import equal
import matplotlib.pyplot as plt
import os
import tikzplotlib

"""
Settings
"""
# The parser_types that we want to compare
PARSER_TYPES = ['oalcep', 'alcep']

# Boolean if we additionally check equality of the CSPPFs computed by the different parser types
CHECK_EQUALITY = True

# Number of executions per parse process
NUMBER_OF_EXECUTIONS = 1

# The maximum length of the test words
WORDS_UP_TO_LENGTH = 30

if __name__ == '__main__':
    # Load a grammar
    with open("../../assets/example_grammars/simple_arithmetic_expression.lark", 'r') as grammar_file:
        grammar = grammar_file.read()

    # A dictionary that contains for all parser types the computation time for each length of input word.
    times = {k: {} for k in PARSER_TYPES}

    # TODO mehr Wörter in unterschiedlichen Längen testen

    for i in range(WORDS_UP_TO_LENGTH):
        input_word = '+' * i

        # A dictionary that contains for all parser types the root node
        csppfs_root_nodes = {}

        for parser_type in PARSER_TYPES:

            # create a parser for the parser typer
            parser = Lark(grammar, parser=parser_type, ambiguity='forest', lexer="basic", debug=False)

            # parse the input word
            execution_time = timeit.timeit('parser.parse(input_word)', globals=globals(), number=NUMBER_OF_EXECUTIONS)
            times[parser_type][i] = execution_time

            if CHECK_EQUALITY:
                root = parser.parse(input_word)
                csppfs_root_nodes[parser_type] = root

        # Check if all computed CSPPFs are equal
        for (parser_1, root_1), (parser_2, root_2) in itertools.combinations(csppfs_root_nodes.items(), 2):
            if not equal(root_1, root_2):
                raise Exception(
                    f'The computed SPPFs for the word: {input_word} are not equal for {parser_1} and {parser_2}')

    # Create a plot for the measured times
    x_values = [i for i in range(WORDS_UP_TO_LENGTH)]
    for parser, parser_times in times.items():
        y_values = [parser_times[i] for i in range(WORDS_UP_TO_LENGTH)]
        plt.plot(x_values, y_values, label=parser)

    plt.xlabel("word length")
    plt.ylabel("runtime [sec]")

    # Create a tmp directory if it not exists.
    os.makedirs("../../tmp", exist_ok=True)

    # Save the plot as a tikz picture.
    tikzplotlib.save(f'../../tmp/alcep_vs_oalcep.tex')

    plt.show()
