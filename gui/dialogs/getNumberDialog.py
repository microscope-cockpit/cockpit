import gui.guiUtils

import wx


## This class allows for prompting the user for a number, similar to
# wx.GetNumberFromUser except that we allow for floating point values as well.
class GetNumberDialog(wx.Dialog):
    def __init__(self, parent, title, prompt, default, atMouse=False):
        # Nothing checks how the window was closed, so the OK button should
        # be the only way to close it.
        style = wx.CAPTION
        if atMouse:
            mousePos = wx.GetMousePosition()
            wx.Dialog.__init__(self, parent, -1, title, mousePos, style=style)
        else:
            wx.Dialog.__init__(self, parent, -1, title, style=style)
        
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        self.value = gui.guiUtils.addLabeledInput(
                parent = self, sizer = mainSizer,
                label = prompt,
                defaultValue = str(default),
                size = (70, -1), minSize = (150, -1), 
                shouldRightAlignInput = True, border = 3, 
                controlType = wx.TextCtrl)

        buttonsBox = wx.BoxSizer(wx.HORIZONTAL)

        #cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        #cancelButton.SetToolTip(wx.ToolTip("Close this window"))
        #buttonsBox.Add(cancelButton, 0, wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Okay")
        buttonsBox.Add(startButton, 0, wx.ALL, 5)
        
        mainSizer.Add(buttonsBox, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        self.SetSizer(mainSizer)
        self.SetAutoLayout(True)
        mainSizer.Fit(self)


    def getValue(self):
        return self.value.GetValue()



## As above, but we can accept any number of prompts for multiple numbers.
class GetManyNumbersDialog(wx.Dialog):
    def __init__(self, parent, title, prompts, defaultValues, atMouse=False):
        # Nothing checks how the window was closed, so the OK button should
        # be the only way to close it.
        style = wx.CAPTION
        if atMouse:
            mousePos = wx.GetMousePosition()
            wx.Dialog.__init__(self, parent, -1, title, mousePos, style=style)
        else:
            wx.Dialog.__init__(self, parent, -1, title, style=style)
        
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        self.controls = []
        for i, prompt in enumerate(prompts):
            control = gui.guiUtils.addLabeledInput(
                    parent = self, sizer = mainSizer,
                    label = prompt,
                    defaultValue = str(defaultValues[i]),
                    size = (70, -1), minSize = (150, -1), 
                    shouldRightAlignInput = True, border = 3, 
                    controlType = wx.TextCtrl)
            self.controls.append(control)

        buttonsBox = wx.BoxSizer(wx.HORIZONTAL)

        #cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        #cancelButton.SetToolTip(wx.ToolTip("Close this window"))
        #buttonsBox.Add(cancelButton, 0, wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Okay")
        buttonsBox.Add(startButton, 0, wx.ALL, 5)
        
        mainSizer.Add(buttonsBox, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        self.SetSizer(mainSizer)
        self.SetAutoLayout(True)
        mainSizer.Fit(self)


    def getValues(self):
        return [control.GetValue() for control in self.controls]


        
def getNumberFromUser(parent, title, prompt, default, atMouse=True):
    dialog = GetNumberDialog(parent, title, prompt, default, atMouse)
    dialog.ShowModal()
    return dialog.getValue()
    

def getManyNumbersFromUser(parent, title, prompts, defaultValues, atMouse=True):
    dialog = GetManyNumbersDialog(parent, title, prompts, defaultValues, atMouse)
    dialog.ShowModal()
    return dialog.getValues()
