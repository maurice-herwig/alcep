# All Correction Earley Parser (ALCEP)

The All Correction Earley Parser is an error-correcting parser which, for a word and a context-free grammar,
computes in cubic time a datastructures containing the (possible) infinite set of corrections.
This datastructures is called SPPF (Shared Packer Parse Forest) where we label the leaves with corrections. 
The implementation of ALCEP is based on the [lark-parser](https://github.com/lark-parser/lark).

## Setup

[Python](https://www.python.org/) version 3.10 or higher is required.

Firstly, the required Python packages must be installed using [pip](https://pip.pypa.io/en/stable/).

```bash
pip install -r requirements.txt 
```

Secondly, [Graphviz](https://graphviz.org/download/) must be installed and added to the path variables on the local
machine.

## Usage

An example of the usage is shown in the [example.py](examples/corrections_parser/example.py) file.
Additionally, grammars you can find [here].(./assets/example_grammars).