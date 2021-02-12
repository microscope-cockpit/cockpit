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

import unittest
import unittest.mock

import cockpit.events


class TestEvents(unittest.TestCase):
    def setUp(self):
        # While we do have classes for Publisher and OneShotPublisher,
        # Cockpit makes use of a singleton of each.  To avoid missing
        # issues in those, we patch the module to get it into a clean
        # state before each test.
        #
        # We can't decorate the class with the patches because then
        # the patching happens between setUp and the individual test
        # code, which would clear the subscription we do on setUp.
        # That is why we patch manually here on setUp.
        self.patches = [
            unittest.mock.patch('cockpit.events._publisher',
                                new_callable=cockpit.events.Publisher),
            unittest.mock.patch('cockpit.events._one_shot_publisher',
                                new_callable=cockpit.events.OneShotPublisher),
        ]
        for patch in self.patches:
            patch.start()

        # Clearing the singleton OneShotPublisher is something that
        # the Cockpit singleton does.  Because we just patched it, we
        # need to do this ourselves.  This does mean that if the
        # subcription on the singleton is ever broken, this tests
        # won't catch that issue.
        cockpit.events.subscribe(cockpit.events.USER_ABORT,
                                 cockpit.events._one_shot_publisher.clear)

        self.subscriber = unittest.mock.Mock()
        self.event_name = 'test events'


class TestSubscriptions(TestEvents):
    def setUp(self):
        super().setUp()
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
        cockpit.events.subscribe(self.event_name, self.subscriber)

    def mock_emitter(self, event_name):
        def side_effect(*args, **kwargs):
            # ignore args and kwargs
            cockpit.events.publish(event_name)
        return unittest.mock.Mock(side_effect=side_effect)

    def test_wait_for_event(self):
        """Waiting for specified event"""
        args = [1, 2]
        kwargs = {'foo': 'bar'}
        emitter = self.mock_emitter(self.event_name)
        cockpit.events.executeAndWaitFor(self.event_name, emitter,
                                         *args, **kwargs)
        emitter.assert_called_once_with(*args, **kwargs)

        # We check the mock subscriber to test that the publication
        # caused by the emitter, went to other subscribers and not
        # only to the executeAndWaitFor releaser.
        self.subscriber.assert_called_once_with()

    def test_abort_wait_for_event(self):
        """User abort event stops waiting for an event"""
        emitter = self.mock_emitter(cockpit.events.USER_ABORT)
        cockpit.events.executeAndWaitFor(self.event_name, emitter)
        emitter.assert_called_once_with()

        # We check the mock subscriber to test the event was not
        # published and the release was caused by the abort event.
        self.subscriber.assert_not_called()


if __name__ == '__main__':
    unittest.main()
