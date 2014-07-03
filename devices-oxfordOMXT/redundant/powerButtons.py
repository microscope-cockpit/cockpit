# Provides a GUI for controlling power to the lasers, diffuser wheel motor,
# fiber shaker motor, and TIRF control.  Also provides a PYRO-wrapped
# PowerButtonsList for remotely controlling the power to the devices.  The
# GUI runs separately from OMX cockpit application because that application is
# frequently started and stopped and would like the power status for the
# devices to not be affected by that.

# HACK: modify the path so we can import wx
#import sys
#sys.path.append('C:/Python27/Lib/site-packages')
#import os
#os.environ['PATH'] += ';C:/Python27/Lib/site-packages/wx-2.8-msw-unicode'
#sys.path.append('C:/Python27/Lib/site-packages/wx-2.8-msw-unicode/wx/lib')
#sys.path.append('C:/Python27/Lib/site-packages/wx-2.8-msw-unicode/wxPython')

#import dataprobe
#import dialogs
import gui.toggleButton

import Pyro4
import socket
import threading
import wx

#IMD 5/4/2013 added to get modules code working.
import device


CLASS_NAME= "PulseLaser"
IP_OMX_DRILL = '172.16.0.21'

## Colors that roughly correspond to the lasers, in order
#LASER_COLORS = [(180, 30, 230),
#                (40, 130, 180), 
#                (40, 230, 40),
#                (255, 40, 40)]

LASER_COLORS = [(40, 130, 180)]

class PowerButtonsList:
    """Represents a list of power controls.  They can be indexed by position or by their name."""
    def __init__(self, button_obj_list):
        self.button_list = button_obj_list

    def get_index(self, index):
        """Convert index into a number if needed."""
        for i, button in enumerate(self.button_list):
            if index == i or index == button.get_label():
                return i
        raise ValueError("Invalid index %s" % index)

    def is_on(self, index):
        """Returns the status of the button given by index."""
        return self.button_list[self.get_index(index)].is_on()

    def turn_on(self, index):
        """Turns on the button given by index."""
        return self.button_list[self.get_index(index)].turn_on()

    def turn_off(self, index):
        """Turns on the button given by index."""
        self.button_list[self.get_index(index)].turn_off()

    def turn_all_off(self):
        """Turn off all devices."""
        for i in xrange(len(self.button_list)):
            # Save the diffuser wheel for last.
            if 'iffuser' in self.button_list[i].get_label():
                continue
            self.button_list[i].turn_off()
#        self.button_list[self.get_index('Diffuser')].turn_off()

    def get_is_diffuser_on(self):
        return self.is_on(self.get_index('Diffuser'))

    def attach(self, index, notification):
        """Registers a callable object which will be called when the state of the button given by index changes.

        Returns an integer ID which can be used with the ignore() method to
        cancel future notifications."""
        return self.button_list[self.get_index(index)].attach(notification)

    def detach(self, index, notify_id):
        """Cancels future notifications to a callable object previously registered with attach()."""
        self.button_list[self.get_index(index)].detach(notify_id)


class Observable:
    """Implements the observer pattern from Design Patterns, Gamma et. al."""
    def __init__(self):
        # Holds pairs of notification IDs and callable objects.
        self.__nd = dict()
        # This is the notification ID to try to assign to the next callable
        # object registered.
        self.__last_id = 0
        # Tracks the number of in-progress calls to notify().  When this is
        # non-zero, attach() and detach() defer adding or deleting
        # notifications so that the iteration done in notify() does not fail.
        self.__in_progress_notify = 0
        # Holds operations deferred by attach() and detach() because calls to
        # notify() were in progress.
        self.__pending_op = []
        # Holds IDs assigned by deferred attach() calls.
        self.__pending_id = []

    def attach(self, notification):
        """Adds a callable object, notification, that will be invoked whenever notify() is called.

        When notify() is called, notification will be passed the observed
        object and the ID generated when notification was registered with
        attach().

        attach() returns a integer ID which can be used with detach() to
        cancel notifications.  That same ID will be passed to the callable
        object, notification, when notify() is called."""
        while self.__last_id in self.__nd or self.__last_id in self.__pending_id:
            try:
                self.__last_id = self.__last_id + 1
            except:
                self.__last_id = 0
        id = self.__last_id
        if self.__in_progress_notify == 0:
            self.__nd[id] = notification
        else:
            self.__pending_op.append( ( id, notification ) )
            self.__pending_id.append(id)
        try:
            self.__last_id = self.__last_id + 1
        except:
            self.__last_id = 0
        return id

    def detach(self, notify_id):
        """Removes a callable object previously added with attach()."""
        if self.__in_progress_notify == 0:
            del self.__nd[notify_id]
        else:
            self.__pending_op.append( ( notify_id, None ) )

    def notify(self):
        """Causes all callable objects registered with attach() to be invoked.

        Makes no guarantee about the order of the invocations."""
        self.__in_progress_notify = self.__in_progress_notify + 1
        for i in self.__nd.iteritems():
            (notification_id, callable) = i
            callable(self, notification_id)
        self.__in_progress_notify = self.__in_progress_notify - 1
        if self.__in_progress_notify == 0:
            for i in range(len(self.__pending_op)):
                (id, value) = self.__pending_op[i]
                if value != None:
                    self.__nd[id] = value
                else:
                    del self.__nd[id]
            self.__pending_op = []
            self.__pending_id = []

##class SerialBootBarConnector(Observable):
##    """Hooks up a device controlled by a Serial BootBar from Dataprobe, Inc."""
##    def __init__(self, bootbar_obj, outlet_index, label):
##        self.bootbar = bootbar_obj
##        self.outlet_index = outlet_index
##        self.label = label
##        Observable.__init__(self)
##
##    def is_on(self):
##        return self.bootbar.get_outlet_state(self.outlet_index) == dataprobe.SerialBootBar.OUTLET_ON;
##
##    def turn_on(self):
##        self.bootbar.set_outlet(self.outlet_index, dataprobe.SerialBootBar.OUTLET_ON)
##        Observable.notify(self)
##        return True
##
##    def turn_off(self):
##        self.bootbar.set_outlet(self.outlet_index, dataprobe.SerialBootBar.OUTLET_OFF)
##        Observable.notify(self)
##
##    def get_label(self):
##        return self.label
##
##
##class VFLaserConnector(Observable):
##    """Hooks up a visual fiber laser."""
##    def __init__(self, vfl_obj, label, uses_acc=True, level=5400, poll_interval=5):
##        self.__vl = vfl_obj
##        self.label = label
##        self.__ac = uses_acc
##        if uses_acc:
##            self.__cu = level
##        else:
##            self.__pw = level
##        self.poll_interval = poll_interval
##        self.details_dialog = None
##        Observable.__init__(self)
##        if self.is_on():
##            if self.__ac:
##                self.__vl.set_current_setpoint(self.__cu)
##                self.__vl.enter_acc_mode()
##            else:
##                self.__vl.set_power_setpoint(self.__pw)
##                self.__vl.enter_apc_mode()
##            self.__vl.enable()
##        else:
##            self.__vl.disable()
##
##    def is_on(self):
##        return self.__vl.is_enabled()
##
##    def turn_on(self):
##        if self.__ac:
##            self.__vl.set_current_setpoint(self.__cu)
##            self.__vl.enter_acc_mode()
##        else:
##            self.__vl.set_power_setpoint(self.__pw)
##            self.__vl.enter_apc_mode()
##        self.__vl.enable()
##        if self.details_dialog != None:
##            self.details_dialog.update_dialog()
##        Observable.notify(self)
##        return True
##
##    def turn_off(self):
##        self.__vl.disable()
##        if self.details_dialog != None:
##            self.details_dialog.update_dialog()
##        Observable.notify(self)
##
##    def get_label(self):
##        return self.label
##
##    def create_details_dialog(self, parent, id=-1, pos=wx.DefaultPosition,
##                              size=wx.DefaultSize,
##                              style=wx.DEFAULT_DIALOG_STYLE, name="dialogBox"):
##        if self.details_dialog == None:
##            self.details_dialog = dialogs.VFLaserDialog(self.__vl, False, self.poll_interval,
##                                      parent=parent, id=id,
##                                      title=self.label + " Details", pos=pos,
##                                      size=size, style=style, name=name)
##        self.details_dialog.Show()
##
##
##class MPC6000Connector(Observable):
##    def __init__(self, mp6000_obj, label, on=False, poll_interval=5):
##        self.mp_obj = mp6000_obj
##        self.label = label
##        self.poll_interval = poll_interval
##        self.details_dialog = None
##        # Can not read back whether or not the laser has been enabled yet
##        # so maintain a variable to track the state.
##        self.is_device_on = on;
##        Observable.__init__(self)
##        if self.is_device_on:
##            self.mp_obj.enable()
##        else:
##            self.mp_obj.disable()
##
##    def is_on(self):
##        return self.is_device_on
##
##    def turn_on(self):
##        self.mp_obj.enable()
##        self.is_device_on = True
##        Observable.notify(self)
##        if self.details_dialog != None:
##            self.details_dialog.update_dialog()
##        return True
##
##    def turn_off(self):
##        self.mp_obj.disable()
##        self.is_device_on = False
##        Observable.notify(self)
##        if self.details_dialog != None:
##            self.details_dialog.update_dialog()
##
##    def get_label(self):
##        return self.label
##
##    def create_details_dialog(self, parent, id = -1, pos = wx.DefaultPosition,
##            size = wx.DefaultSize,
##            style = wx.DEFAULT_DIALOG_STYLE, name = "dialogBox"):
##        if self.details_dialog == None:
##            self.details_dialog = dialogs.MPC6000Dialog(self.mp_obj, False, 
##                    self.poll_interval, parent = parent, id = id,
##                    title = self.label + " Details", pos = pos,
##                    size = size, style = style, name = name)
##        self.details_dialog.Show()
##

class PulseLaser(Observable):
    def __init__(self, connection, label):
        self.label = label
        Observable.__init__(self)
        self.connection = connection


    def is_on(self):
        return self.connection.getIsOn()


    def turn_on(self):
        if not self.connection.enable():
            wx.MessageDialog(None,
                    "The laser cannot be turned on. Make certain that the " +
                    "key is turned and the standby switch has been flipped.",
                    "Couldn't enable laser.",
                    wx.OK | wx.STAY_ON_TOP | wx.ICON_EXCLAMATION).ShowModal()
            return False
        return True


    def turn_off(self):
        self.connection.disable()


    def get_label(self):
        return self.label

        

class DeviceOnOffButton(gui.toggleButton.ToggleButton):
    def __init__(self, parent, control_obj, *args, **kwargs):
        self.control_obj = control_obj
        self.eventType = wx.NewEventType()
        self.eventBinder = wx.PyEventBinder(self.eventType, 1)
        gui.toggleButton.ToggleButton.__init__(self, parent = parent,
                activeLabel = 'On', inactiveLabel = 'Off',
                textSize = 10, size = (74, -1))
        if self.control_obj.is_on():
            self.activate()
        self.Bind(wx.EVT_LEFT_DOWN, self.handle_button_press)
        self.Bind(self.eventBinder, self.handle_external_change)
        self.control_obj.attach(self.notify_of_external_change)
        self.update_label()

    def ignore_event(self, event):
        pass

    def handle_button_press(self, event):
        isOn = False
        if not self.getIsActive():
            isOn = self.control_obj.turn_on()
        else:
            self.control_obj.turn_off()
        self.setActive(isOn)
        self.update_label()

    def handle_external_change(self, event):
        self.setActive(self.control_obj.is_on())
        self.update_label()

    def notify_of_external_change(self, observed_obj, notification_id):
        ev = wx.CommandEvent(self.eventType)
        wx.PostEvent(self, ev)

    def update_label(self):
        if self.getIsActive():
            self.SetLabel("On")
        else:
            self.SetLabel("Off")

class DeviceDetailsButton(wx.Button):
    def __init__(self, control_obj, *args, **kwargs):
        self.control_obj = control_obj
        wx.Button.__init__(self, *args, **kwargs)
        if getattr(self.control_obj, "create_details_dialog", None) != None:
            self.Bind(wx.EVT_BUTTON, self.handle_button_press)
        else:
            self.Disable()

    def handle_button_press(self, event):
        self.control_obj.create_details_dialog(parent=self)

class PowerButtonsFrame(wx.Frame):
    def __init__(self, button_obj_list, *args, **kwargs):
        self.button_list = button_obj_list
        wx.Frame.__init__(self, *args, **kwargs)
        self.create_controls()

    def create_controls(self):
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.static_boxes = [ None ] * len(self.button_list)
        self.vert_sizer = [ None ] * len(self.button_list)
        self.horiz_sizer = [ None ] * (2 * len(self.button_list))
        self.on_off_buttons = [ None ] * len(self.button_list)
        self.details_buttons = [ None ] * len(self.button_list)
        for i in range(len(self.button_list)):
            self.static_boxes[i] = wx.StaticBox(self, -1, self.button_list[i].get_label())
            if i > 2:
                # Color the box with the laser color
                self.static_boxes[i].SetBackgroundColour(LASER_COLORS[i])
            self.vert_sizer[i] = wx.StaticBoxSizer(self.static_boxes[i], wx.VERTICAL)
            self.horiz_sizer[i + i] = wx.BoxSizer(wx.HORIZONTAL)
            self.on_off_buttons[i] = DeviceOnOffButton(self, self.button_list[i])
            self.horiz_sizer[i + i].Add(self.on_off_buttons[i], 1)
            self.horiz_sizer[i + i + 1] = wx.BoxSizer(wx.HORIZONTAL)
            self.details_buttons[i] = DeviceDetailsButton(
                self.button_list[i], self, label="Details...", size=(74,-1))
            self.horiz_sizer[i + i + 1].Add(self.details_buttons[i])
            self.vert_sizer[i].Add(self.horiz_sizer[i + i])
            self.vert_sizer[i].AddSpacer((0, 5))
            self.vert_sizer[i].Add(self.horiz_sizer[i + i + 1], 1, wx.EXPAND)
            self.sizer.Add(self.vert_sizer[i], 1, wx.EXPAND)
        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.SetMinSize(self.sizer.GetMinSize())

class PowerButtonsApp(wx.App):
    def __init__(self, button_obj_list):
        self.button_list = button_obj_list
        try:
            wx.App.__init__(self)
        except Exception, e:
            print "Failed:",e
            import traceback
            traceback.print_exc()

    def OnInit(self):
        frame = PowerButtonsFrame(self.button_list, None, title="OMX Power Control")
        frame.Show()
        self.SetTopWindow(frame)
        return True


from optparse import OptionParser

parser = OptionParser()
# NB these default options are important, since we no longer run this
# script from a Priithon shell
parser.add_option("-p", "--port", type="int", dest="net_port", default=7769, help="TCP port to listen on for service", metavar="PORT_NUMBER")
parser.add_option("-i", "--host", dest="hostname", default='172.16.0.1', help="name of host providing service", metavar="HOSTNAME")
parser.add_option("-n", "--name", dest="service_name", default='PowerButtonList', help="name of service", metavar="NAME")
(options, args) = parser.parse_args()

#bb = Pyro4.Proxy('PYRO:%s@%s:%d' % ("SerialBootBar", IP_OMX_DRILL, 7774))
#laser560 = Pyro4.Proxy('PYRO:%s@%s:%d' % ("560Laser", IP_OMX_DRILL, 7773))
deepstar488 = Pyro4.Proxy('PYRO:%s@%s:%d' % ('pyro488DeepstarLaser', IP_OMX_DRILL, 7776))
# bl = [
    # SerialBootBarConnector(bb, 6, "Fiber Shaker"),
    # SerialBootBarConnector(bb, 7, "Diffuser"),
    # SerialBootBarConnector(bb, 8, "TIRF Box"),
    # SerialBootBarConnector(bb, 1, "405 Laser"),
    # PulseLaser(deepstar488, "488 Laser"),
    # VFLaserConnector(laser560, "560 Laser"),
    # SerialBootBarConnector(bb, 5, "640 Laser"),
bl = [ PulseLaser(deepstar488, "488 Laser")
    ]
wrapped_bl = PowerButtonsList(bl)
daemon = Pyro4.Daemon(port = 7770, host = '172.16.0.1')
runThread = threading.Thread(target = Pyro4.Daemon.serveSimple,
        args = [{wrapped_bl: 'pyroPowerButtonsList'}],
        kwargs = {'daemon': daemon, 'ns': False, 'verbose': True})
runThread.daemon = True
runThread.start()

app = PowerButtonsApp(bl)
app.GetTopWindow().SetPosition((1186, 1099))
app.GetTopWindow().Show()
app.MainLoop()
