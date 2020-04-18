#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

import threading
import time
import unittest
import unittest.mock

import cockpit.events

class TestEvents(unittest.TestCase):
    def setUp(self):
        # Ideally, we would have a Publisher class and we would use a
        # new instance.  However, cockpit.events does not work like
        # that yet (see issue #461) so we need to patch the module to
        # get it it indo a clean state and revert it back at the end.
        # And we can't decorate the class with patch because then the
        # patching happens after setUp and before the test case, which
        # so clears the subscription we do on setUp.  That is why we
        # patch manually here on setUp.
        self.patches = [
            unittest.mock.patch.dict(cockpit.events.eventToSubscriberMap,
                                     clear=True),
            unittest.mock.patch.dict(cockpit.events.eventToOneShotSubscribers,
                                     clear=True)
        ]
        for patch in self.patches:
            patch.start()

        self.event_name = 'test events'


class TestSubscriptions(TestEvents):
    def setUp(self):
        super().setUp()
        self.subscriber = unittest.mock.Mock()
        cockpit.events.subscribe(self.event_name, self.subscriber)

    def test_not_called(self):
        """When nothing is published, nothing is called"""
        self.subscriber.assert_not_called()

    def test_subscribe(self):
        """Publishing event calls the subscriber"""
        cockpit.events.publish(self.event_name)
        self.subscriber.assert_called_once_with()

    def test_subscribe_with_args(self):
        """Publishing event with args calls the subscriber with args"""
        args = [1, 2]
        kwargs = {'foo': 'bar'}
        cockpit.events.publish(self.event_name, *args, **kwargs)
        self.subscriber.assert_called_once_with(*args, **kwargs)

    def test_unsubscribe(self):
        """Subscriber stops being called after unsubscription"""
        cockpit.events.unsubscribe(self.event_name, self.subscriber)
        cockpit.events.publish(self.event_name)
        self.subscriber.assert_not_called()

    def test_no_subscription(self):
        """Is not called for subscriptions it is not subscribed"""
        cockpit.events.publish('other ' + self.event_name)
        self.subscriber.assert_not_called()

    def test_multiple_subscribers(self):
        extra_subscribers = [unittest.mock.Mock() for i in range(5)]
        for subscriber in extra_subscribers:
            cockpit.events.subscribe(self.event_name, subscriber)
        cockpit.events.publish(self.event_name)
        for subscriber in [self.subscriber] + extra_subscribers:
            subscriber.assert_called_once()


class TestOneShotSubscriptions(TestEvents):
    def setUp(self):
        super().setUp()
        # A side effect of having to patch the events module to get it
        # "clean" is that we lose the subscription that cleans the one
        # shot subscribers, so we need to put it back.  It's a bit
        # redundant to test it was there before, but we hope we can
        # remove it soon by having the events functions in a class
        # (see issue #461).
        cockpit.events.subscribe(cockpit.events.USER_ABORT,
                                 cockpit.events.clearOneShotSubscribers)

        self.subscriber = unittest.mock.Mock()
        cockpit.events.oneShotSubscribe(self.event_name, self.subscriber)

    def test_called_only_once(self):
        """One shot subscriptions are not called on second publication"""
        cockpit.events.publish(self.event_name)
        cockpit.events.publish(self.event_name)
        self.subscriber.assert_called_once_with()

    def test_clear_after_abort(self):
        """One shot subscriptions cleared if user abort is published before"""
        cockpit.events.publish(cockpit.events.USER_ABORT)
        cockpit.events.publish(self.event_name)
        self.subscriber.assert_not_called()


class TestExecuteAndWait(TestEvents):
    def setUp(self):
        super().setUp()
        cockpit.events.subscribe(cockpit.events.USER_ABORT,
                                 cockpit.events.clearOneShotSubscribers)

    def mock_publisher(self, event_name):
        def side_effect(*args, **kwargs):
            # ignore args and kwargs
            cockpit.events.publish(event_name)
        return unittest.mock.Mock(side_effect=side_effect)

    def test_wait_for_event(self):
        """Waiting for specified event"""
        # A mock subscriber to test that the event went caused by the
        # function provided, went to other subscribers and not only to
        # the wait releaser.
        self.subscriber = unittest.mock.Mock()
        cockpit.events.subscribe(self.event_name, self.subscriber)

        args = [1, 2]
        kwargs = {'foo': 'bar'}
        publisher = self.mock_publisher(self.event_name)
        cockpit.events.executeAndWaitFor(self.event_name, publisher,
                                         *args, **kwargs)

        publisher.assert_called_once_with(*args, **kwargs)
        self.subscriber.assert_called_once_with()

    def test_abort_wait_for_event(self):
        """User abort event stops waiting for an event"""
        # Another mock subscriber to test that the waited event did
        # not happen and the release was caused by the abort event.
        self.subscriber = unittest.mock.Mock()
        cockpit.events.subscribe(self.event_name, self.subscriber)

        publisher = self.mock_publisher(cockpit.events.USER_ABORT)
        cockpit.events.executeAndWaitFor(self.event_name, publisher)

        self.subscriber.assert_not_called()
        publisher.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
