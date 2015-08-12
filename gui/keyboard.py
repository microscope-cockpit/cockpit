import wx

import gui.camera.window
import gui.guiUtils
import gui.mosaic.window
import interfaces.stageMover
import util.user

## Given a wx.Window instance, set up keyboard controls for that instance.
def setKeyboardHandlers(window):
    accelTable = wx.AcceleratorTable([
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_MULTIPLY, 6903), # Rescale cameras
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DIVIDE, 6904), # Switch stage control
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DECIMAL, 6905), # Transfer image to mosaic

        # Move the stage with the keypad
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD1, 6311), # Z down
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD2, 6312), # Y down
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD3, 6313), # Decrease delta
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD4, 6314), # X up
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD5, 6315), # Stop motion
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD6, 6316), # X down
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD7, 6317), # Z up
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD8, 6318), # Y up
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD9, 6319), # Increase delta

        # Take an image
        (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ADD, 6320),
		(wx.ACCEL_NORMAL, wx.WXK_NUMPAD0, 6320),
		

        # Pop up a menu to help the user find hidden windows.
        (wx.ACCEL_CTRL, ord('M'), 6321),
    ])
    window.SetAcceleratorTable(accelTable)
    for eventId, direction in [(6314, (1, 0, 0)), (6316, (-1, 0, 0)),
            (6312, (0, -1, 0)), (6318, (0, 1, 0)), (6311, (0, 0, -1)),
            (6317, (0, 0, 1))]:
        wx.EVT_MENU(window, eventId,
                lambda event, direction = direction: interfaces.stageMover.step(direction))
    wx.EVT_MENU(window, 6903, 
            lambda event: gui.camera.window.rescaleViews())
    wx.EVT_MENU(window, 6904, 
            lambda event: interfaces.stageMover.changeMover())
    wx.EVT_MENU(window, 6905,
            lambda event: gui.mosaic.window.transferCameraImage())

    wx.EVT_MENU(window, 6313, 
            lambda event: interfaces.stageMover.changeStepSize(-1))
    wx.EVT_MENU(window, 6319, 
            lambda event: interfaces.stageMover.changeStepSize(1))
    
    wx.EVT_MENU(window, 6320, 
            lambda event: interfaces.imager.takeImage())

    wx.EVT_MENU(window, 6321,
            lambda event: martialWindows(window))


## Pop up a menu under the mouse that helps the user find a window they may
# have lost.
def martialWindows(parent):
    primaryWindows = wx.GetApp().primaryWindows
    secondaryWindows = wx.GetApp().secondaryWindows
    otherWindows = [w for w in wx.GetTopLevelWindows() 
                        if w not in (primaryWindows + secondaryWindows)]
    # windows = wx.GetTopLevelWindows()
    menu = wx.Menu()
    menuId = 1
    menu.Append(menuId, "Reset window positions")
    wx.EVT_MENU(parent, menuId,
            lambda event: util.user.setWindowPositions())
    menuId += 1
    #for i, window in enumerate(windows):
    for i, window in enumerate(primaryWindows):
        if not window.GetTitle():
            # Sometimes we get bogus top-level windows; no idea why.
            # Just skip them.
            # \todo Figure out where these windows come from and either get
            # rid of them or fix them so they don't cause trouble here.
            continue
        subMenu = wx.Menu()
        subMenu.Append(menuId, "Raise to top")
        wx.EVT_MENU(parent, menuId,
                lambda event, window = window: window.Raise())
        menuId += 1
        subMenu.Append(menuId, "Move to mouse")
        wx.EVT_MENU(parent, menuId,
                lambda event, window = window: window.SetPosition(wx.GetMousePosition()))
        menuId += 1
        subMenu.Append(menuId, "Move to top-left corner")
        wx.EVT_MENU(parent, menuId,
                lambda event, window = window: window.SetPosition((0, 0)))
        menuId += 1
        # Some windows have very long titles (e.g. the Macro Stage View),
        # so just take the first 50 characters.
        menu.AppendMenu(menuId, str(window.GetTitle())[:50], subMenu)
        menuId += 1

    menu.AppendSeparator()
    for i, window in enumerate(secondaryWindows):
        if not window.GetTitle():
            # Sometimes we get bogus top-level windows; no idea why.
            # Just skip them.
            # \todo Figure out where these windows come from and either get
            # rid of them or fix them so they don't cause trouble here.
            continue
        subMenu = wx.Menu()
        subMenu.Append(menuId, "Show/Hide")
        wx.EVT_MENU(parent, menuId,
                lambda event, window = window: (window.Restore() if window.IsIconized() 
                                                else window.Show(not window.IsShown()) ) )
        menuId += 1
        # Some windows have very long titles (e.g. the Macro Stage View),
        # so just take the first 50 characters.
        menu.AppendMenu(menuId, str(window.GetTitle())[:50], subMenu)
        menuId += 1

    menu.AppendSeparator()
    for i, window in enumerate(otherWindows):
        if not window.GetTitle():
            # Sometimes we get bogus top-level windows; no idea why.
            # Just skip them.
            # \todo Figure out where these windows come from and either get
            # rid of them or fix them so they don't cause trouble here.
            continue
        subMenu = wx.Menu()
        subMenu.Append(menuId, "Raise to top")
        wx.EVT_MENU(parent, menuId,
                lambda event, window = window: window.Raise())
        menuId += 1
        subMenu.Append(menuId, "Move to mouse")
        wx.EVT_MENU(parent, menuId,
                lambda event, window = window: window.SetPosition(wx.GetMousePosition()))
        menuId += 1
        subMenu.Append(menuId, "Move to top-left corner")
        wx.EVT_MENU(parent, menuId,
                lambda event, window = window: window.SetPosition((0, 0)))
        menuId += 1
        # Some windows have very long titles (e.g. the Macro Stage View),
        # so just take the first 50 characters.
        menu.AppendMenu(menuId, str(window.GetTitle())[:50], subMenu)
        menuId += 1



    gui.guiUtils.placeMenuAtMouse(parent, menu)

