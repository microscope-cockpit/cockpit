import wx
import wx.propgrid
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


class SettingsEditor(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY)
        self.panel = wx.Panel(self, wx.ID_ANY, style=wx.WANTS_CHARS)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.grid = wx.propgrid.PropertyGrid(self)
        self.populateGrid()
        self.Bind(wx.propgrid.EVT_PG_CHANGED, self.onPropertyChange)
        sizer.Add(self.grid)
        self.SetSizerAndFit(sizer)


    def onPropertyChange(self, event):
        prop = event.GetProperty()
        value = event.GetProperty().GetValue()
        if prop.ClassName == 'wxEnumProperty':
            index = event.GetPropertyValue()
            value = prop.ValueToString(index)
        else:
            value = event.GetPropertyValue()
        name = event.GetPropertyName()
        PROXY.set_setting(name, value)
        self.grid.Clear()
        self.populateGrid()


    def populateGrid(self):
        grid = self.grid
        settings = PROXY.describe_settings()
        current = PROXY.get_all_settings()
        for key, desc in settings:
            value = current[key]
            propType = SETTINGS_TO_PROPTYPES.get(desc['type'])
            #if propType in [wx.propgrid.IntProperty, wx.propgrid.FloatProperty]:
            #    value = current[key]
            #    limits = desc['values']
            #elif propType in [wx.propgrid]
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
    app = MyApp()
    #e = wx.Timer(app, wx.ID_ANY)
    #e.Start(1000)
    #wx.EVT_TIMER(app, e.GetId(), update)  # call the on_timer function
    app.MainLoop()
