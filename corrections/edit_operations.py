from lark import Token
import corrections.constants as constants


class EditOperation(Token):
    """
    An edit operation is an operation to edit a token of an input word. So a correction is a sequence of edit
    operations. Therefore, edit operations are the leaves of each correction shared packed parse forest (CSPPF).
    In order to be able to use the data structure of the shared packed parser forest (SPPF see
    lark.parsers.earley_forest) for CSPPFs, edit operations inherit from the Token class.
    """

    def __new__(cls, value):
        """
        Create a new edit operation instance.

        :param value: The string value to represent this node in a graphically representation of an CSPPF.
        """
        return super().__new__(cls, "STR", value=value)


class InsertionOperation(EditOperation):
    def __new__(cls, word):
        """
        Create a new insertion edit operation.

        :param word: The word that are inserted by this operation.
        """
        return super().__new__(cls, value=constants.EDIT_OPERATION_INS_SYMBOL + "'" + word + "'")

    def __init__(self, word):
        self.word = word

    def compare(self, other):
        """
        Comparison function between two insertion operation.
        An insert operation is smaller than another insert operation if the insert word is a scattered subsequence of
        the other insert word.

        :param other: The insert operation with that we want to compare this insert operation.
        :return: The result of the correction. (0 = equals, -1 = incomparable, 1 = self is smaller,
            2 = other is smaller)
        """

        def __is_scattered_subsequence(shorter_word, longer_word):
            """
            Auxiliary function to check if the given shorter word a scattered subsequence of the given longer word.
            Note that only a shorter_word can be a scatterd subword of a longer word.

            :param shorter_word: The word for that we want to check if it is a scatterd subword of the longer word.
            :param longer_word: The other word.
            :return: (0 = both words are equal, 1 = the shorter word is a scatterd subsequence, -1 the shorter word
                is not a scatterd subsequence of the longer word.)
            """

            # Assert that the shorter word is really shorter than the longer word.
            assert len(shorter_word) <= len(longer_word), \
                "the shorter word must be shorter or equal then the longer word. "

            # Check if the words are equal
            if shorter_word == longer_word:
                return constants.CORRECTION_EQUAL

            len_shorter_word = len(shorter_word)
            # If the shorter word the empty word, then it is a scatterd subword of each non-empty word.
            if len_shorter_word == 0:
                return constants.CORRECTION_SMALLER

            i = 0

            # If the shorter word is a non-empty word, then iterate over all the letters of the longer word until the
            # first letter of the shorter word is found in the longer word. Then for the second letter of the shorter
            # word, and so on until the end of the shorter word is reached. In this case, the shorter word is a
            # scattered subword of the longer word. If the last letter is not reached, the shorter word is not a
            # scattered subword of the longer word.
            for letter in longer_word:

                if letter == shorter_word[i]:
                    i += 1

                    if i == len_shorter_word:
                        return constants.CORRECTION_SMALLER

            return constants.CORRECTION_INCOMPARABLE

        # Start of the main compare function.
        # Check that the other operation is from type insertion operation.
        assert isinstance(other, InsertionOperation), \
            "An insertion operation can only compare with an insertion operation. "

        # Check wich of the given words is shorter. Dependence on that call the __is_scatterd_subsequence
        # auxiliary function.
        if len(self.word) <= len(other.word):
            return __is_scattered_subsequence(shorter_word=self.word, longer_word=other.word)
        else:
            res = __is_scattered_subsequence(shorter_word=other.word, longer_word=self.word)

            # If the other word longer we need to flip the result from smaller to bigger.
            if res == constants.CORRECTION_SMALLER:
                return constants.CORRECTION_BIGGER
            else:
                return res


class DeletionOperation(EditOperation):

    def __new__(cls, letter):
        """
        Create a new deletion edit operation.

        :param letter: The letter of the word that this operation should delete.
        """
        instance = super().__new__(cls, value=constants.EDIT_OPERATION_DEL_SYMBOL + "'" + letter + "'")
        return instance

    def __init__(self, letter):
        self.letter = letter

    def compare(self, other):
        """
        Comparison function between a deletion operation and another edit operation.
        Note that deletion operations can only compare with read, deletion and replacement operation but not with
        Insertion operations.

        :param other: The edit operation with that we want to compare this deletion operation.
        :return: The result of the compare. (0 = equals, -1 = incomparable, 1 = self is smaller, 2 = other is smaller)
        """
        # Note isinstance matches only work with Python 3.10 or higher
        match other:
            case ReadOperation():
                if self.letter == other.letter:
                    return 2
                else:
                    return -1
            case DeletionOperation():
                if self.letter == other.letter:
                    return 0
                else:
                    return -1
            case ReplacementOperation():
                return -1
            case InsertionOperation():
                raise Exception("An Deletion operation cannot compare with an Insertion operation. ")


class ReplacementOperation(EditOperation):

    def __new__(cls, letter, replaced_by):
        """
        Create a new replacement edit operation.

        :param letter: The letter that this replacement operation are removed.
        :param replaced_by: The letter that this replacement operation are insertion.
        """
        instance = super().__new__(cls, value=constants.EDIT_OPERATION_REPLACE_SYMBOL1 + "'" + letter + "'" +
                                              constants.EDIT_OPERATION_REPLACE_SYMBOL2 + "'" + replaced_by + "'")
        return instance

    def __init__(self, letter, replaced_by):
        self.letter = letter
        self.replaced_by = replaced_by

    def compare(self, other):
        """
        Comparison function between a replacement operation and another edit operation.
        Note that replacement operations can only compare with read, deletion and replacement operation but not with
        Insertion operations.

        :param other: The edit operation with that we want to compare this replacement operation.
        :return: The result of the compare. (0 = equals, -1 = incomparable, 1 = self is smaller, 2 = other is smaller)
        """

        # Note isinstance matches only work with Python 3.10 or higher
        match other:
            case ReadOperation():
                if self.letter == other.letter:
                    return 2
                else:
                    return -1
            case DeletionOperation():
                return -1
            case ReplacementOperation():
                if self.letter == other.letter and self.replaced_by == other.replaced_by:
                    return 0
                else:
                    return -1
            case InsertionOperation():
                raise Exception("An Replacement operation cannot compare with an Insertion operation. ")


class ReadOperation(EditOperation):
    def __new__(cls, letter):
        """
        Create a new Read operation.

        :param letter: The letter that this read operation are read.
        """
        instance = super().__new__(cls, value=constants.EDIT_OPERATION_READ_SYMBOL + "'" + letter + "'")
        return instance

    def __init__(self, letter):
        self.letter = letter

    def compare(self, other):
        """
        Comparison function between a read operation and another edit operation.
        Note that read operations can only compare with read, deletion and replacement operation but not with
        Insertion operations.

        :param other: The edit operation with that we want to compare this read operation.
        :return: The result of the compare. (0 = equals, -1 = incomparable, 1 = self is smaller, 2 = other is smaller)
        """

        # Note isinstance matches only work with Python 3.10 or higher
        match other:
            case ReadOperation():
                if self.letter == other.letter:
                    return 0
                else:
                    return -1
            case DeletionOperation():
                if self.letter == other.letter:
                    return 1
                else:
                    return -1
            case ReplacementOperation():
                if self.letter == other.letter:
                    return 1
                else:
                    return -1
            case InsertionOperation():
                raise Exception("An Read operation cannot compare with an Insertion operation. ")
