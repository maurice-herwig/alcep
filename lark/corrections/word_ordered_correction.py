from lark.corrections.edit_operations import ReadOperation, DeletionOperation, InsertionOperation, ReplacementOperation
import lark.corrections.constants as constants


class WordOrderedCorrection:
    """
    An word_ordered correction represents a sequence of insert operation in a special form.
    1: An insertion operation. That represent that word that we want to insert in front of the first letter of the
    input word.
    2: An read/replace or deletion operation. That describe how the first letter of the input word should be handled,
    i.e. whether it should be deleted or read, for example.
    3: An insertion operation. That  represent that word that we want to insert after the first letter of the input word
    and in front of the second letter of the input word.
    ....
    2n + 1: The insertion after the last letter of the input word.

    n = the length of the input word.
    """

    def __init__(self, operations: list, validate_word_ordered: bool = False):
        """
        The constructor of word_ordered corrections.

        :param operations: A list of the edit operations of this word_ordered correction.
        :param validate_word_ordered: If this value is true, then the constructor validate that a given list of edit
            operations is in the above described form.
        """

        self.operations = operations

        # Validate that the edit operations list in the right form.
        if validate_word_ordered:
            assert len(self.operations) % 2 == 1, "The number of edit operations of the corrections is not odd."

            for i in range(len(self.operations)):
                if i % 2 == 0:
                    if not isinstance(self.operations[i], InsertionOperation):
                        raise Exception("The corrections must be an alternating sequence of insertion "
                                        "and non-insertion operations.")
                else:
                    if not type(self.operations[i]) in {ReadOperation, ReplacementOperation, DeletionOperation}:
                        raise Exception("The corrections must be an alternating sequence of insertion "
                                        "and non-insertion operations.")

    def apply(self):
        """
        The application of an word_ordered correction on an input word.
        Note that each word_ordered correction is only applicable on exactly one input word. Therefor we assume that we
        want to apply this word_ordered correction on that input word.

        :return: The corrected word.
        """

        res = ""

        # Iterate over all edit operations and apply them.
        for operation in self.operations:

            # Note isinstance matches only work with Python 3.10 or higher
            match operation:
                case ReadOperation():
                    res += operation.letter
                case DeletionOperation():
                    pass
                case InsertionOperation():
                    res += operation.word
                case ReplacementOperation():
                    res += operation.replaced_by
                case _:
                    raise Exception(f'Unknown edit operation {operation}')
        return res

    def concatenate(self, other, simplify=False):
        """
        Concatenate two word_ordered corrections.
        We assume that both word_ordered corrections are given in a valid format.

        :param other: The word_ordered correction that we want to add at the end of the self correction.
        :param simplify: If this value is True the method return only the concatenated correction if this is in
            simplified form.

        :return: The concatenated word_ordered correction or None if the concatenated correction is not in simplified form
            and to simplify parameter is true.
        """

        # If one of the correction is an empty correction. We can return the other correction.
        if not self.operations or not other.operations:
            if not self.operations:
                return other
            elif not other.operations:
                return self
            else:
                return self

        # Check possible if the resulting correction can be simplified.
        if simplify and self.can_simplify(other=other):
            return None
        else:
            # Return the concatenated correction.
            return WordOrderedCorrection(operations=
                                       self.operations[:-1]
                                       + [InsertionOperation(word=self.operations[-1].word + other.operations[0].word)]
                                       + other.operations[1:])

    def can_simplify(self, other):
        """
        Auxiliary method to check if the by the concatenation fo the two given correction the resulting correction
        is in simplified form or not.

        !!! This method assume that both given corrections are already in simplified form!!!

        :param self: The front part of the concatenated correction.
        :param other: The rear part of the concatenated correction.

        :return: A boolean if the resulting correction is in simplified form or not.
        """

        # TODO eventuelle Optimierung: HashMap aller bereits durchgeführten Simplifizierungen.

        # Get the last edit operation of the self correction and the first edit operation of the other correction.
        # Note that both edit operations are insertion edit operations.
        self_last_operation = self.operations[-1]
        other_first_operation = other.operations[0]

        # If both the insertion word of both insertion operation is not empty then we cannot simplify the
        # corrections.
        if self_last_operation.word and other_first_operation.word:
            return False

        # The insertion word of the others first correction is empty.
        elif self_last_operation.word and not other_first_operation.word:

            # If the other corrections consists only of empty insertion, the correction cannot be simplified.
            if len(other) == 1:
                return False

            # Note isinstance matches only work with Python 3.10 or higher
            match other.operations[1]:
                case DeletionOperation():
                    return True
                case ReplacementOperation():
                    return self_last_operation.word.endswith(other.operations[1].letter)
                case _:
                    return False

        elif not self_last_operation.word and other_first_operation.word:

            # IF the self correction consists only of an empty insertion, the correction cannot be simplified.
            if len(self) == 1:
                return False

            # Note isinstance matches only work with Python 3.10 or higher
            match self.operations[-2]:
                case DeletionOperation():
                    return True
                case ReplacementOperation():
                    return other_first_operation.word.startswith(self.operations[-2].replaced_by)
                case _:
                    return False

        else:
            # If one of the corrections consists only of the empty insertion, the correction cannot be simplified.
            if len(other) == 1 or len(self) == 1:
                return False

            # Note isinstance matches only work with Python 3.10 or higher
            match self.operations[-2]:
                case ReplacementOperation():

                    match other.operations[1]:
                        case DeletionOperation():
                            return self.operations[-2].replaced_by == other.operations[
                                1].letter
                        case _:
                            return False
                case _:
                    return False

    def compare(self, other):
        """
        Compare two word_ordered corrections.
        !!! only word_ordered corrections of the same length can compare!!!
        A correction is smaller than another correction iff the edit operation ath each index is smaller or equal as the
        edit operation of the other correction at the same index and a lest one index is the edit operatio real smaller.

        :param other: The correction with that we want to compare.
        :return: The result of the correction. (0 = equals, -1 = incomparable, 1 = self is smaller,
            2 = other is smaller)
        """

        # Check that the correction have the same length.
        assert len(self) == len(other), "Only word_ordered corrections of the same length can be compared."

        # The current status of the comparison
        current_comparison = constants.CORRECTION_EQUAL

        # Iterate over all edit operations of both corrections and compare the edit operation. Update after each compare
        # the current comparison status.
        for edit_i_self, edit_i_other in zip(self.operations, other.operations):
            match edit_i_self.compare(edit_i_other):
                case constants.CORRECTION_INCOMPARABLE:
                    return constants.CORRECTION_INCOMPARABLE
                case constants.CORRECTION_SMALLER:
                    match current_comparison:
                        case constants.CORRECTION_EQUAL:
                            current_comparison = constants.CORRECTION_SMALLER
                        case constants.CORRECTION_BIGGER:
                            return constants.CORRECTION_INCOMPARABLE
                case constants.CORRECTION_BIGGER:
                    match current_comparison:
                        case constants.CORRECTION_EQUAL:
                            current_comparison = constants.CORRECTION_BIGGER
                        case constants.CORRECTION_SMALLER:
                            return constants.CORRECTION_INCOMPARABLE

        return current_comparison

    def __len__(self):
        return len(self.operations)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str([operation.value for operation in self.operations])
