from datetime import datetime
import unittest
from shipproto import main


class MyTest(unittest.TestCase):
    def test__testable_function__is_correct(self) -> None:
        # Arrange
        current_time = datetime(1970, 1, 1, 13, 00)

        # Act
        result = main.testable_function(current_time)

        # Assert
        expected_result = datetime(1970, 1, 1, 14, 00)
        self.assertEqual(expected_result, result)

