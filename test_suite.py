'''
Master test runner for cockpit.

Imports unittest.TestCases from each module, and then unittest discovers them.

USAGE:
python test_suite.py

or, for a coverage report:
coverage run --source=experiment/,handlers/,util/ --omit='*/test*','.*','*/.*','*__init__.py' test_suite.py
coverage report

Thomas Parks 2015
thomas.parks@diamond.ac.uk
thomasparks@outlook.com
'''

import unittest

from experiment.tests.test_experiment import TestExperiment
from experiment.tests.test_actionTable import TestActionTable
from experiment.tests.test_dataSaver import TestDataSaver

from util.tests.test_colors import TestWavelengthToColor, TestHsvToRgb

from util.tests.test_datadoc import TestDataDoc


if __name__ == '__main__':
    unittest.main()
