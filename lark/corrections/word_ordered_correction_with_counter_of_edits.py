from .word_ordered_correction import WordOrderedCorrection
from lark.corrections.edit_operations import InsertionOperation


class WordOrderedCorrectionWithCounterOfEdits(WordOrderedCorrection):
    # Class Attributs.
    # -1 = A newly created object is not checked to see whether it exceeds the maximum number of operations.
    max_number_of_insertions = -1
    max_number_of_replacement = -1
    max_number_of_deletions = -1
    max_number_of_edits = -1

    def __init__(self, operations: list, validate_word_ordered: bool = False):
        """
        Constructor.

        :param operations: A list of the edit operations of this word_ordered correction.
        :param validate_word_ordered: If this value is true, then the constructor validate that a given list of edit
            operations is in the above described form.
        """
        # Init an word_ordered Corrections object.
        super().__init__(operations=operations, validate_word_ordered=validate_word_ordered)

        # Init the initial counters
        self.counter_of_insertions = 0
        self.counter_of_replacements = 0
        self.counter_of_deletions = 0

    def concatenate(self, other, simplify=False):
        """
        Concatenate two word_ordered corrections_parser.
        We assume that both word_ordered corrections_parser are given in a valid format.

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
        if simplify and super().can_simplify(other=other):
            return None
        else:

            # Compute the new counters of corrections_parser and check if they are greater than the maximum values.
            new_counter_of_insertions = self.counter_of_insertions + other.counter_of_insertions
            if WordOrderedCorrectionWithCounterOfEdits.max_number_of_insertions != -1 \
                    and new_counter_of_insertions > WordOrderedCorrectionWithCounterOfEdits.max_number_of_insertions:
                return None

            new_counter_of_deletions = self.counter_of_deletions + other.counter_of_deletions
            if WordOrderedCorrectionWithCounterOfEdits.max_number_of_deletions != -1 \
                    and new_counter_of_deletions > WordOrderedCorrectionWithCounterOfEdits.max_number_of_deletions:
                return None

            new_counter_of_replacements = self.counter_of_replacements + other.counter_of_replacements
            if WordOrderedCorrectionWithCounterOfEdits.max_number_of_replacement != -1 \
                    and new_counter_of_replacements > WordOrderedCorrectionWithCounterOfEdits.max_number_of_replacement:
                return None

            if WordOrderedCorrectionWithCounterOfEdits.max_number_of_edits != -1:
                sum_of_edits = new_counter_of_insertions + new_counter_of_deletions + new_counter_of_replacements
                if sum_of_edits > WordOrderedCorrectionWithCounterOfEdits.max_number_of_edits:
                    return None

            # Create the concatenated corrections_parser
            new_correction_with_counter = WordOrderedCorrectionWithCounterOfEdits(
                operations=self.operations[:-1]
                           + [InsertionOperation(word=self.operations[-1].word + other.operations[0].word)]
                           + other.operations[1:])

            # Set the counters
            new_correction_with_counter.counter_of_insertions = new_counter_of_insertions
            new_correction_with_counter.counter_of_replacements = new_counter_of_replacements
            new_correction_with_counter.counter_of_deletions = new_counter_of_deletions

            return new_correction_with_counter

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return super().__str__() + f' with {self.counter_of_insertions} insertions, {self.counter_of_deletions} ' \
                                   f'deletions and {self.counter_of_replacements} replacements'
