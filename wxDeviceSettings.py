import wx
import wx.propgrid
from collections import OrderedDict
from itertools import ifilter
import Pyro4

PROXY = Pyro4.Proxy('PYRO:DeviceServer@127.0.0.1:8002')
SETTINGS_TO_PROPTYPES = {'int': wx.propgrid.IntProperty,
                         'float': wx.propgrid.FloatProperty,
                         'bool': wx.propgrid.BoolProperty,
                         'enum': wx.propgrid.EnumProperty,
                         'str': wx.propgrid.StringProperty,
                         str(int): wx.propgrid.IntProperty,
                         str(float): wx.propgrid.FloatProperty,
                         str(bool): wx.propgrid.BoolProperty,
                         str(str): wx.propgrid.StringProperty,}

Pyro4.config.SERIALIZER='pickle'

class SettingsEditor(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY)
        self.settings = None
        #self.panel = wx.Panel(self, wx.ID_ANY, style=wx.WANTS_CHARS)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.grid = wx.propgrid.PropertyGrid(self, )
        self.populateGrid()
        self.Bind(wx.propgrid.EVT_PG_CHANGED, self.onPropertyChange)
        sizer.Add(self.grid, 1, wx.EXPAND | wx.ALIGN_LEFT | wx.ALIGN_TOP)

        sizer.AddSpacer(2)
        closeButton = wx.Button(self, id=wx.ID_OK)
        closeButton.Bind(wx.EVT_BUTTON, self.onClose)
        sizer.Add(closeButton, 0, wx.ALIGN_RIGHT)

        self.SetSizerAndFit(sizer)
        self.SetMaxSize((self.GetMinWidth(), -1))


    def onClose(self, evt):
        self.Close()
        # Do stuff to update local device state.

    def onPropertyChange(self, event):
        prop = event.GetProperty()
        name = event.GetPropertyName()
        setting = self.settings[name]
        # Fetch and validate the value.
        if prop.ClassName == 'wxEnumProperty':
            index = event.GetPropertyValue()
            # Look up value as the original type, not as str from the wxProperty.
            # setting['values'] only contains allowed values, so this also
            # serves as validation for enums.
            value = setting['values'][index]
        elif setting['type'] in (str(int), str(float), 'int', 'float'):
            value = event.GetPropertyValue()
            # Bound to min/max.
            lims = setting['values']
            value = sorted(lims + (value,))[1]
        elif setting['type'] in (str(str), 'str'):
            # Limit string length.
            value = value[0, setting['values']]
        elif setting['type'] in (str(bool), 'bool'):
            value = event.GetPropertyValue()
        else:
            raise Exception('Unsupported type.')

        PROXY.set_setting(name, value)
        #self.grid.SelectProperty(prop)
        self.Freeze()
        self.updateGrid()
        self.Thaw()
        #self.Refresh()


    def updateGrid(self):
        grid = self.grid
        self.settings = OrderedDict(PROXY.describe_settings())
        current = PROXY.get_all_settings()
        # Update all values.
        # grid.SetValues(current)
        # Enable/disable
        for prop in grid.Properties:
            name = prop.GetName()
            desc = self.settings[name]
            if desc['type'] in ('enum'):
                prop.SetChoices([str(v) for v in desc['values']],
                                range(len(desc['values'])))
                prop.SetValue(desc['values'].index(current[name]))
            else:
                value = current[name]
                if type(value) is long:
                    value = int(value)
                prop.SetValue(value)
            try:
                prop.Enable(not self.settings[name]['readonly'])
            except wx._core.PyAssertionError:
                # Bug in wx in stc.EnsureCaretVisible, could not convert to a long.
                pass



    def populateGrid(self):
        grid = self.grid
        self.settings = OrderedDict(PROXY.describe_settings())
        current = PROXY.get_all_settings()
        for key, desc in self.settings.iteritems():
            value = current[key]
            propType = SETTINGS_TO_PROPTYPES.get(desc['type'])
            if propType is wx.propgrid.EnumProperty:
                prop = wx.propgrid.EnumProperty(label=key, name=key,
                                                labels=[str(v) for v in desc['values']],
                                                values=range(len(desc['values'])),
                                                value=desc['values'].index(value))
            else:
                try:
                    prop = propType(label=key, name=key, value=(value or 0))
                except OverflowError:
                    # Int too large.
                    prop = wx.propgrid.FloatProperty(label=key, name=key, value=(value or 0))
            if desc['readonly']:
                prop.Enable(False)
            grid.Append(prop)


class MyApp(wx.App):
    def __init__(self, redirect=False, filename=None):
        wx.App.__init__(self, redirect, filename)
        self.frame = wx.Frame(None, wx.ID_ANY, title='My Title')
        self.panel = wx.Panel(self.frame, wx.ID_ANY)
        self.panel.Bind(wx.EVT_LEFT_DOWN, self.onLeftClick)
        self.panel.Bind(wx.EVT_RIGHT_DOWN, self.onRightClick)
        self.frame.Show(True)


    def onLeftClick(self, evt):
        settings = PROXY.describe_settings()
        editor = SettingsEditor()
        editor.Show()


    def onRightClick(self, evt):
        pass


def update(*args, **kwargs):
    pass


if __name__ == '__main__':
    import wx.lib.inspection
    app = MyApp()
    wx.lib.inspection.InspectionTool().Show()
    #e = wx.Timer(app, wx.ID_ANY)
    #e.Start(1000)
    #wx.EVT_TIMER(app, e.GetId(), update)  # call the on_timer function
    app.MainLoop()
