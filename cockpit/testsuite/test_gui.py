#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

import unittest
import unittest.mock

import wx

import cockpit.events
import cockpit.gui


class WxTestCase(unittest.TestCase):
    def setUp(self):
        self.app = wx.App()
        self.frame = wx.Frame(None)

    def tearDown(self):
        def cleanup():
            for tlw in wx.GetTopLevelWindows():
                if tlw:
                    if isinstance(tlw, wx.Dialog) and tlw.IsModal():
                        tlw.EndModal(0)
                    else:
                        tlw.Close(force=True)
                    wx.CallAfter(tlw.Destroy)
            wx.WakeUpIdle()

        wx.CallLater(100, cleanup)
        self.app.MainLoop()
        del self.app


class TestCockpitEvents(WxTestCase):
    def setUp(self):
        super().setUp()
        self.mock_function = unittest.mock.Mock()

    def create_and_bind(self, window):
        emitter = cockpit.gui.EvtEmitter(window, 'test gui')
        emitter.Bind(cockpit.gui.EVT_COCKPIT, self.mock_function)

    def trigger_event(self):
        cockpit.events.publish('test gui')
        self.app.ProcessPendingEvents()

    def test_bind(self):
        self.create_and_bind(self.frame)
        self.trigger_event()
        self.mock_function.assert_called_once()

    def test_parent_destroy(self):
        window = wx.Frame(self.frame)
        self.create_and_bind(window)
        window.ProcessEvent(wx.CommandEvent(wx.wxEVT_DESTROY))
        self.trigger_event()
        self.mock_function.assert_not_called()


if __name__ == '__main__':
    unittest.main()
