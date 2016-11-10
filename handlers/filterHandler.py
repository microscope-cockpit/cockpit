import deviceHandler
import depot
import events
import gui
import wx
from config import config


class Filter(object):
    """An individual filter."""

    def __init__(self, position, *args):
        self.position = position
        # args describes the filter.
        # The description can be one of
        #   label, value
        #   (label, value)
        #   label
        if hasattr(args[0], '__iter__'):
            self.label = args[0][0]
            if len(args[0]) > 1:
                self.value = args[0][1]
            else:
                self.value = None
        else:
            self.label = args[0]
            self.value = args[1]

    def __repr__(self):
        if self.value:
            return '%d: %s, %s' % (self.position, self.label, self.value)
        else:
            return '%d: %s' % (self.position, self.label)


class FilterHandler(deviceHandler.DeviceHandler):
    """A handler for emission and ND filter wheels."""
    def __init__(self, device, groupName):
        self._device = device
        self.name = device.name
        deviceHandler.DeviceHandler.__init__(self,
                self.name, groupName, False, {},
                deviceType=depot.GENERIC_DEVICE)


    ### UI functions ####
    def makeUI(self, parent):
        self.display = gui.toggleButton.ToggleButton(
                        parent=parent, label='', isBold=False)
        self.display.Bind(wx.EVT_LEFT_DOWN, self.menuFunc)
        self.display.Bind(wx.EVT_RIGHT_DOWN, self._device.showSettings)
        self.updateDisplay()
        return self.display


    def updateDisplay(self, *args):
        # Accept *args so that can be called directly as a Pyro callback
        # or an event handler.
        self.display.SetLabel('%s\n%s' % (self.name, self._device.getFilter()))
        if self._device.cameras:
            # Emission filter
            drawer = depot.getHandlersOfType(depot.DRAWER)[0]
            f = self._device.getFilter()
            for camera in self._device.cameras:
                drawer.changeFilter(camera, f.label, f.value)
            events.publish("drawer change", drawer)

        if self._device.lights:
            # Excitation filter
            pass


    def menuFunc(self, evt=None):
        items = [str(f) for f in self._device.filters]
        menu = gui.device.Menu(items, self.menuCallback)
        menu.show(evt)


    def menuCallback(self, index, item):
        self._device.setFilterByIndex(index, callback=self.updateDisplay)