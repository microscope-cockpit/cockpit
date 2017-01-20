"""
Copyright 2014-2015 Mick Phillips (mick.phillips at gmail dot com)
and Nicholas Hall (nicholas.hall at dtc dot ox dot ac dot uk)

Based on code by rdb released under the Unlicense (unlicense.org)
Further reading about the WinMM Joystick API:
http://msdn.microsoft.com/en-us/library/windows/desktop/dd757116(v=vs.85).aspx

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
=============================================================================
"""

from math import floor, ceil
import time
import ctypes
import threading
import device
import events
import interfaces.stageMover
import gui.mosaic.window
import gui.camera
import depot

#patch from David to stop it breaking when not on windows.
import os
if os.name is 'nt':
    import _winreg as winreg
    from ctypes.wintypes import WORD, UINT, DWORD
    from ctypes.wintypes import WCHAR as TCHAR
else:
    from ctypes import c_ushort as WORD
    from ctypes import c_uint as UINT
    from ctypes import c_ulong as DWORD
    from ctypes import c_wchar as TCHAR

CLASS_NAME = 'WindowsJoystickDevice'

# Fetch function pointers
if os.name is 'nt':
    joyGetNumDevs = ctypes.windll.winmm.joyGetNumDevs
    joyGetPos = ctypes.windll.winmm.joyGetPos
    joyGetPosEx = ctypes.windll.winmm.joyGetPosEx
    joyGetDevCaps = ctypes.windll.winmm.joyGetDevCapsW
else:
    joyGetNumDevs = lambda : 0

#end of patch from David


# Define constants
MAXPNAMELEN = 32
MAX_JOYSTICKOEMVXDNAME = 260

JOY_RETURNX = 0x1
JOY_RETURNY = 0x2
JOY_RETURNZ = 0x4
JOY_RETURNR = 0x8
JOY_RETURNU = 0x10
JOY_RETURNV = 0x20
JOY_RETURNPOV = 0x40
JOY_RETURNBUTTONS = 0x80
JOY_RETURNRAWDATA = 0x100
JOY_RETURNPOVCTS = 0x200
JOY_RETURNCENTERED = 0x400
JOY_USEDEADZONE = 0x800
JOY_RETURNALL = JOY_RETURNX | JOY_RETURNY | JOY_RETURNZ | JOY_RETURNR | JOY_RETURNU | JOY_RETURNV | JOY_RETURNPOV | JOY_RETURNBUTTONS

# This is the mapping for my XBox 360 controller.
button_names = ['a', 'b', 'x', 'y', 'lb', 'rb', 'back', 'start', 'thumbl', 'thumbr']
povbtn_names = ['dpad_up', 'dpad_right', 'dpad_down', 'dpad_left']

# Define some structures from WinMM that we will use in function calls.
class JOYCAPS(ctypes.Structure):
    _fields_ = [
        ('wMid', WORD),
        ('wPid', WORD),
        ('szPname', TCHAR * MAXPNAMELEN),
        ('wXmin', UINT),
        ('wXmax', UINT),
        ('wYmin', UINT),
        ('wYmax', UINT),
        ('wZmin', UINT),
        ('wZmax', UINT),
        ('wNumButtons', UINT),
        ('wPeriodMin', UINT),
        ('wPeriodMax', UINT),
        ('wRmin', UINT),
        ('wRmax', UINT),
        ('wUmin', UINT),
        ('wUmax', UINT),
        ('wVmin', UINT),
        ('wVmax', UINT),
        ('wCaps', UINT),
        ('wMaxAxes', UINT),
        ('wNumAxes', UINT),
        ('wMaxButtons', UINT),
        ('szRegKey', TCHAR * MAXPNAMELEN),
        ('szOEMVxD', TCHAR * MAX_JOYSTICKOEMVXDNAME),
    ]

class JOYINFO(ctypes.Structure):
    _fields_ = [
        ('wXpos', UINT),
        ('wYpos', UINT),
        ('wZpos', UINT),
        ('wButtons', UINT),
    ]

class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ('dwSize', DWORD),
        ('dwFlags', DWORD),
        ('dwXpos', DWORD),
        ('dwYpos', DWORD),
        ('dwZpos', DWORD),
        ('dwRpos', DWORD),
        ('dwUpos', DWORD),
        ('dwVpos', DWORD),
        ('dwButtons', DWORD),
        ('dwButtonNumber', DWORD),
        ('dwPOV', DWORD),
        ('dwReserved1', DWORD),
        ('dwReserved2', DWORD),
    ]


class WindowsJoystickDevice(device.Device):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.isActive = True
        self.priority = 100
        # Get the number of supported devices (usually 16).
        self.num_devs = joyGetNumDevs()
        if self.num_devs == 0:
            print("Joystick driver not loaded.")
            #drop out of driver as we have no joystick (maybe not windows?)
            return

        # Number of the joystick to open.
        joy_id = 0
        # Check if the joystick is plugged in.
        self.info = JOYINFO()
        self.p_info = ctypes.pointer(self.info)

        if joyGetPos(0, self.p_info) != 0:
            print("Joystick %d not plugged in." % (joy_id + 1))

        # Get device capabilities.
        self.caps = JOYCAPS()
        if joyGetDevCaps(joy_id, ctypes.pointer(self.caps),
                         ctypes.sizeof(JOYCAPS)) != 0:

            print("Failed to get device capabilities.")

        print "Driver name:", self.caps.szPname


        # Fetch the name from registry.
        self.key = None
        if len(self.caps.szRegKey) > 0:
            try:
                self.key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "System\\CurrentControlSet\\Control\\MediaResources\\Joystick\\%s\\CurrentJoystickSettings" % (self.caps.szRegKey))
            except WindowsError:
                self.key = None

        if self.key:
            self.oem_name = winreg.QueryValueEx(self.key, "Joystick%dOEMName" % (joy_id + 1))
            if self.oem_name:
                key2 = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "System\\CurrentControlSet\\Control\\MediaProperties\\PrivateProperties\\Joystick\\OEM\\%s" % (self.oem_name[0]))
                if key2:
                    self.oem_name = winreg.QueryValueEx(key2, "OEMName")
                key2.Close()

        # Set the initial button states.
        self.button_states = {}
        for b in range(self.caps.wNumButtons):
            name = button_names[b]
            if (1 << b) & self.info.wButtons:
                self.button_states[name] = True
            else:
                self.button_states[name] = False

        for name in povbtn_names:
            self.button_states[name] = False

        # Initialise the JOYINFOEX structure.
        self.info = JOYINFOEX()
        self.info.dwSize = ctypes.sizeof(JOYINFOEX)
        self.info.dwFlags = JOY_RETURNBUTTONS | JOY_RETURNCENTERED | JOY_RETURNPOV | JOY_RETURNU | JOY_RETURNV | JOY_RETURNX | JOY_RETURNY | JOY_RETURNZ
        self.p_info = ctypes.pointer(self.info)

        self.enable_read = True

    def initialize(self):
        ##test to see if we have a joystick
        if (self.num_devs > 0):
            ## Prepare a thread the reads joystick data and dispatches move events accordingly.
            self.joystickThread = threading.Thread(target = self.readJoystickThread)
            events.subscribe("cockpit initialization complete", self.start)
            events.subscribe("stage position", self.onStageMoved)
            events.subscribe("stage stopped", self.onStageStopped)

        else:
            pass

    def onStageMoved(self, axis, target):
        #self.enable_read = False
        pass


    def onStageStopped(self, axis):
        self.enable_read = True


    def start(self):
        if (self.num_devs >0):
            self.joystickThread.start()
        else:
            pass


    def readJoystickThread(self):
        # Fetch new joystick data until it returns non-0 (that is, it has been unplugged)
        buttons_text = " "
        curPosition = interfaces.stageMover.getPosition()
        self.mosaic = gui.mosaic.window.window
        self.camera = gui.camera
        x_threshold = 0.075
        y_threshold = 0.075
        multiplier = 1.1
        movement_speed_mosaic = 10
        movement_speed_stage = 10
        #Note that these values are set arbirarily for the moment. In the future
        #they should be defined by the physical limits of the motors which move
        #the stage.
        max_speed_stage = 100
        min_speed_stage = 1
        cameras=depot.getHandlersOfType(depot.CAMERA)

        while joyGetPosEx(0, self.p_info) == 0:

            while not self.enable_read:
                time.sleep(0.05)

            # Remap the values to float
            x = (self.info.dwXpos - 32767) / 32768.0
            y = (self.info.dwYpos - 32767) / 32768.0
            trig = (self.info.dwZpos - 32767) / 32768.0
            rx = (self.info.dwRpos - 32767) / 32768.0
            ry = (self.info.dwUpos - 32767) / 32768.0

            # NB.  Windows drivers give one axis for the trigger, but I want to have
            # two for compatibility with platforms that do support them as separate axes.
            # This means it'll behave strangely when both triggers are pressed, though.
            lt = max(-1.0,  trig * 2 - 1.0)
            rt = max(-1.0, -trig * 2 - 1.0)

            # Figure out which buttons are pressed.
            for b in range(self.caps.wNumButtons):
                pressed = (0 != (1 << b) & self.info.dwButtons)
                name = button_names[b]
                self.button_states[name] = pressed

            # Determine the state of the POV buttons using the provided POV angle.
            if self.info.dwPOV == 65535:
                povangle1 = None
                povangle2 = None
            else:
                angle = self.info.dwPOV / 9000.0
                povangle1 = int(floor(angle)) % 4
                povangle2 = int(ceil(angle)) % 4

            for i, btn in enumerate(povbtn_names):
                if i == povangle1 or i == povangle2:
                    self.button_states[btn] = True
                else:
                    self.button_states[btn] = False

            x = x if (abs(x) > x_threshold) else 0
            y = y if (abs(y) > y_threshold) else 0

            #Uses joystick to move either the mosaic or the stage
            if abs(x) > 0 or abs(y) > 0:
                #If the left bumper is pressed, the stage is moved. Also functions
                #as a dead-man switch.
                if self.button_states["lb"] == True:
                    interfaces.stageMover.moveRelative((-movement_speed_stage*x, -movement_speed_stage*y, 0), shouldBlock=False)
                #If the left bumper isn't pressed, the mosaic is moved.
                else:
                    self.mosaic.canvas.dragView([movement_speed_mosaic*x, movement_speed_mosaic*y])

            #Pressing the right bumper centers the window on the current position
            if self.button_states["rb"] == True:
                self.mosaic.centerCanvas()

            #Pressing the start button starts and stops the mosaic
            if self.button_states["start"] == True:
                self.mosaic.displayMosaicMenu()
                time.sleep(0.5)

            #Pressing the back button takes an image
            if self.button_states["back"] == True:
                interfaces.imager.takeImage()
                self.mosaic.transferCameraImage()
                time.sleep(0.5)


            #Pressing up and down on the D-pad zoom in/out respectively
            if self.button_states['dpad_up'] == True:
                self.mosaic.canvas.multiplyZoom(multiplier)
            elif self.button_states['dpad_down'] == True:
                self.mosaic.canvas.multiplyZoom(1/multiplier)

            #Pressing left and right on the D-pad increases/decreases movement speed
            if self.button_states["lb"] == True:
                if self.button_states['dpad_left'] == True:
                    movement_speed_stage *= multiplier
                elif self.button_states['dpad_right'] == True:
                    movement_speed_stage /= multiplier
                #Checks implimented to make sure the stage doesn't move faster
                #than it's physically capable of or slower than the discrete teeth
                #of the gears will let it.
                if movement_speed_stage > max_speed_stage:
                    movement_speed_stage = max_speed_stage
                if movement_speed_stage < min_speed_stage:
                    movement_speed_stage = min_speed_stage
            else:
                if self.button_states['dpad_left'] == True:
                    movement_speed_mosaic *= multiplier
                elif self.button_states['dpad_right'] == True:
                    movement_speed_mosaic /= multiplier

            #Mark sites by clicking the left analogue stick
            if self.button_states['thumbl'] == True:
                self.mosaic.saveSite()
                time.sleep(1)

            #Toggle cameras
            i=0
            for camera in cameras:
                if self.button_states[button_names[i]] == True:
                    camera.toggleState()
                    time.sleep(0.5)
                i = i + 1

            time.sleep(0.05)
