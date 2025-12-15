from lark import Lark

if __name__ == '__main__':
    # Example for a simple arithmetic expression grammar
    with open("../../assets/example_grammars/simple_arithmetic_expression.lark", 'r') as grammar_file:
        grammar = grammar_file.read()

        # Create a lark ALCIEP parser instance.
        parser = Lark(grammar, parser='alciep', ambiguity='forest', lexer="basic", debug=False)

        # Start the parser process
        correction = parser.parse("++++")

        # Print the computed/chosen correction
        print(f'Correction: {correction}')
        print(f'Corrected word: {correction.apply()}')


    # Example for the Python grammar
    with open("../../lark/grammars/python.lark", 'r') as grammar_file:
        grammar = grammar_file.read()

        # Create a lark ALCIEP parser instance.
        parser = Lark(grammar, parser='alciep', ambiguity='forest', lexer="basic", debug=False, start='single_input')

        # Start the parser process
        correction = parser.parse("if")

        # Print the computed/chosen correction
        print(f'Correction: {correction}')
        print(f'Corrected word: {correction.apply()}')
