from lark import Lark

if __name__ == '__main__':
    # Load a grammar
    with open("../../assets/example_grammars/simple_arithmetic_expression.lark", 'r') as grammar_file:
        grammar = grammar_file.read()

        # Create a lark OALCEP parser instance.
        # Set debug to true to get in the file csspf.html a visualisation of the computed SPPF.
        # Set parser to 'alcep' to use the alcep parser.
        parser = Lark(grammar, parser='oalcep', ambiguity='forest', lexer="basic", debug=False)

        # Start the parser process
        root = parser.parse("++++")

    