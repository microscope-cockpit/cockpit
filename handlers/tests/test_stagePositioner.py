import unittest
import mock

import handlers.stagePositioner

class testStagePositioner(unittest.TestCase):

    def setUp(self):
        self.callbacks = mock.MagicMock()
        self.args = {'name':'name', 'groupName':'grpname',
                     'isEligibleForExperiments':True,
                     'callbacks':self.callbacks,
                     'axis':0, 'stepSizes':range(10), 'stepIndex':1,
                     'hardLimits':(-10, 10)}

    def test_soft_limits(self):
        PH = handlers.stagePositioner.PositionerHandler(**self.args)
        self.assertEqual(PH.softlimits, self.args['hardlimits'])

    def test_soft_limits_present(self):
        self.args['softlimits'] = (-5, 5)
        PH = handlers.stagePositioner.PositionerHandler(**self.args)
        self.assertEqual(PH.softlimits, (-5, 5))
