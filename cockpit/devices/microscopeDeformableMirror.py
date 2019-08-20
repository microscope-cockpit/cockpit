# Cockpit Device file for Deformable Mirror AO device.
# Copyright Ian Dobbie, 2017
# Copyright Nick Hall, 2018
# released under the GPL 3+
#
# This file provides the cockpit end of the driver for a deformable
# mirror as currently mounted on DeepSIM in Oxford

import os
from collections import OrderedDict
import cockpit.devices
from cockpit.devices import device
from cockpit import events
import wx
import cockpit.interfaces.stageMover
import cockpit.util
import cockpit.interfaces.imager
from itertools import groupby
import cockpit.gui.device
import cockpit.gui.toggleButton
import Pyro4
import cockpit.util.userConfig as Config
import cockpit.handlers.executor
from cockpit.devices.microscopeDevice import MicroscopeBase
from cockpit import depot
import time
import cockpit.util.selectCircROI as selectCircle
import cockpit.util.phaseViewer as phaseViewer
import cockpit.util.charAssayViewer as charAssayViewer
import numpy as np
import scipy.stats as stats


# the AO device subclasses Device to provide compatibility with microscope.
class MicroscopeDeformableMirror(MicroscopeBase, device.Device):
    def __init__(self, name, dm_config={}):
        super(self.__class__, self).__init__(name, dm_config)
        self.proxy = None
        self.sendImage = False
        self.curCamera = None

        self.buttonName = 'Deformable Mirror'

        ## Connect to the remote program

    def initialize(self):
        self.proxy = Pyro4.Proxy(self.uri)
        self.proxy.set_trigger(cp_ttype="RISING_EDGE", cp_tmode="ONCE")
        self.no_actuators = self.proxy.get_n_actuators()
        self.actuator_slopes = np.zeros(self.no_actuators)
        self.actuator_intercepts = np.zeros(self.no_actuators)

        # Excercise the DM to remove residual static and then set to 0 position
        for ii in range(50):
            self.proxy.send(np.random.rand(self.no_actuators))
            time.sleep(0.01)
        self.proxy.reset()

        # Create accurate look up table for certain Z positions
        # LUT dict has key of Z positions
        try:
            file_path = os.path.join(os.path.expandvars('%LocalAppData%'), 'cockpit', 'remote_focus_LUT.txt')
            LUT_array = np.loadtxt(file_path)
            self.LUT = {}
            for ii in (LUT_array[:, 0])[:]:
                self.LUT[ii] = LUT_array[np.where(LUT_array == ii)[0][0], 1:]
        except:
            self.LUT = None

        # Slopes and intercepts are used for extrapolating values not
        # found in the LUT dict
        if self.LUT is not None:
            self.actuator_slopes, self.actuator_intercepts = \
                self.remote_ac_fits(LUT_array, self.no_actuators)

        # Initiate a table for calibrating the look up table
        self.remote_focus_LUT = []

        # Load values from config
        try:
            self.parameters = Config.getValue('dm_circleParams')
            self.proxy.set_roi(self.parameters[0], self.parameters[1],
                               self.parameters[2])
        except:
            pass

        try:
            self.controlMatrix = Config.getValue('dm_controlMatrix')
            self.proxy.set_controlMatrix(self.controlMatrix)
        except:
            pass

        # subscribe to enable camera event to get access the new image queue
        events.subscribe('camera enable',
                         lambda c, isOn: self.enablecamera(c, isOn))

    def finalizeInitialization(self):
        # A mapping of context-menu entries to functions.
        # Define in tuples - easier to read and reorder.
        menuTuples = (('Fourier metric', 'fourier'),
                      ('Contrast metric', 'contrast'),)
        # Store as ordered dict for easy item->func lookup.
        self.menuItems = OrderedDict(menuTuples)

    ### Context menu and handlers ###
    def menuCallback(self, index, item):
        return self.proxy.set_metric(self.menuItems[item])

    def onRightMouse(self, event):
        menu = cockpit.gui.device.Menu(self.menuItems.keys(), self.menuCallback)
        menu.show(event)

    def takeImage(self):
        cockpit.interfaces.imager.takeImage()

    def enablecamera(self, camera, isOn):
        self.curCamera = camera
        # Subscribe to new image events only after canvas is prepared.

    def remote_ac_fits(self, LUT_array, no_actuators):
        # For Z positions which have not been calibrated, approximate with
        # a regression of known positions.

        actuator_slopes = np.zeros(no_actuators)
        actuator_intercepts = np.zeros(no_actuators)

        pos = np.sort(LUT_array[:, 0])[:]
        ac_array = np.zeros((np.shape(LUT_array)[0], no_actuators))

        count = 0
        for jj in pos:
            ac_array[count, :] = LUT_array[np.where(LUT_array == jj)[0][0], 1:]
            count += 1

        for kk in range(no_actuators):
            s, i, r, p, se = stats.linregress(pos, ac_array[:, kk])
            actuator_slopes[kk] = s
            actuator_intercepts[kk] = i
        return actuator_slopes, actuator_intercepts

    ### Experiment functions ###

    def examineActions(self, table):
        # Extract pattern parameters from the table.
        # patternParms is a list of tuples (angle, phase, wavelength)
        patternParams = [row[2] for row in table if row[1] is self.handler]
        if not patternParams:
            # DM is not used in this experiment.
            return

        # Remove consecutive duplicates and position resets.
        reducedParams = [p[0] for p in groupby(patternParams)
                         if type(p[0]) is float]
        # Find the repeating unit in the sequence.
        sequenceLength = len(reducedParams)
        for length in range(2, len(reducedParams) // 2):
            if reducedParams[0:length] == reducedParams[length:2 * length]:
                sequenceLength = length
                break
        sequence = reducedParams[0:sequenceLength]

        # Calculate DM positions
        ac_positions = np.outer(reducedParams, self.actuator_slopes.T) \
                       + self.actuator_intercepts
        ## Queue patterns on DM.
        if np.all(ac_positions.shape) != 0:
            self.proxy.queue_patterns(ac_positions)
        else:
            # No actuator values to queue, so pass
            pass

        # Track sequence index set by last set of triggers.
        lastIndex = 0
        for i, (t, handler, action) in enumerate(table.actions):
            if handler is not self.handler:
                # Nothing to do
                continue
            elif action in [True, False]:
                # Trigger action generated on earlier pass through.
                continue
            # Action specifies a target frame in the sequence.
            # Remove original event.
            if type(action) is tuple:
                # Don't remove event for tuple.
                # This is the type for remote focus calibration experiment
                pass
            else:
                table[i] = None
            # How many triggers?
            if type(action) is float and action != sequence[lastIndex]:
                # Next pattern does not match last, so step one pattern.
                numTriggers = 1
            elif type(action) is int:
                if action >= lastIndex:
                    numTriggers = action - lastIndex
                else:
                    numTriggers = sequenceLength - lastIndex - action
            else:
                numTriggers = 0
            """
            Used to calculate time to execute triggers and settle here, 
            then push back all later events, but that leads to very long
            delays before the experiment starts. For now, comment out
            this code, and rely on a fixed time passed back to the action
            table generator (i.e. experiment class).
            # How long will the triggers take?
            # Time between triggers must be > table.toggleTime.
            dt = self.settlingTime + 2 * numTriggers * table.toggleTime
            ## Shift later table entries to allow for triggers and settling.
            table.shiftActionsBack(time, dt)
            for trig in range(numTriggers):
            t = table.addToggle(t, triggerHandler)
            t += table.toggleTime
            """
            for trig in range(numTriggers):
                t = table.addToggle(t, self.handler)
                t += table.toggleTime

            lastIndex += numTriggers
            if lastIndex >= sequenceLength:
                if sequenceLength == 0:
                    pass
                else:
                    lastIndex = lastIndex % sequenceLength
        table.clearBadEntries()
        # Store the parameters used to generate the sequence.
        self.lastParms = ac_positions
        # should add a bunch of spurious triggers on the end to clear the buffer for AO
        for trig in range(12):
            t = table.addToggle(t, self.handler)
            t += table.toggleTime

    def getHandlers(self):
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        dt = self.config.get('settlingtime', 10)
        result = []
        self.handler = cockpit.handlers.executor.DelegateTrigger(
            "dm", "dm group", True,
            {'examineActions': self.examineActions,
             'getMovementTime': lambda *args: dt,
             'executeTable': self.executeTable})
        self.handler.delegateTo(trigsource, trigline, 0, dt)
        result.append(self.handler)
        return result

    ## Run a portion of a table describing the actions to perform in a given
    # experiment.
    # \param table An ActionTable instance.
    # \param startIndex Index of the first entry in the table to run.
    # \param stopIndex Index of the entry before which we stop (i.e. it is
    #        not performed).
    # \param numReps Number of times to iterate the execution.
    # \param repDuration Amount of time to wait between reps, or None for no
    #        wait time.
    def executeTable(self, table, startIndex, stopIndex, numReps, repDuration):
        # The actions between startIndex and stopIndex may include actions for
        # this handler, or for this handler's clients. All actions are
        # ultimately carried out by this handler, so we need to parse the
        # table to replace client actions, resulting in a table of
        # (time, self).

        for t, h, args in table[startIndex:stopIndex]:
            if h is self.handler:
                if type(args) == float:
                    # This should have been replaced by a trigger and the entry cleared
                    # Theoretically, this check should always be False
                    pass
                elif type(args) == np.ndarray:
                    self.proxy.send(args)
                elif type(args) == str:
                    if args[1] == "clean":
                        # Clean any pre-exisitng values from the LUT
                        self.remote_focus_LUT = []
                    else:
                        raise Exception("Argument Error: Argument type %s not understood." % str(type(args)))
                elif type(args) == tuple:
                    if args[1] == "flatten":
                        LUT_values = np.zeros(self.no_actuators + 1)
                        LUT_values[0] = args[0]
                        LUT_values[1:] = \
                            self.proxy.flatten_phase(iterations=5)
                        self.proxy.reset()
                        self.proxy.send(LUT_values[1:])
                        self.remote_focus_LUT.append(np.ndarray.tolist(LUT_values))
                    else:
                        raise Exception("Argument Error: Argument type %s not understood." % str(type(args)))
                else:
                    raise Exception("Argument Error: Argument type %s not understood." % str(type(args)))

        if len(self.remote_focus_LUT) != 0:
            file_path = os.path.join(os.path.expandvars('%LocalAppData%'), 'cockpit', 'remote_focus_LUT.txt')
            np.savetxt(file_path, np.asanyarray(self.remote_focus_LUT))
            Config.setValue('dm_remote_focus_LUT', self.remote_focus_LUT)

    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        self.panel.SetDoubleBuffered(True)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label_setup = cockpit.gui.device.Label(
            parent=self.panel, label='AO set-up')
        sizer.Add(label_setup)
        rowSizer = wx.BoxSizer(wx.VERTICAL)
        self.elements = OrderedDict()

        # Button to calibrate the DM
        selectCircleButton = wx.Button(self.panel, label='Select ROI')
        selectCircleButton.Bind(wx.EVT_BUTTON, self.onSelectCircle)
        self.elements['selectCircleButton'] = selectCircleButton

        # Button to calibrate the DM
        calibrateButton = wx.Button(self.panel, label='Calibrate')
        calibrateButton.Bind(wx.EVT_BUTTON, lambda evt: self.onCalibrate())
        self.elements['calibrateButton'] = calibrateButton

        characteriseButton = wx.Button(self.panel, label='Characterise')
        characteriseButton.Bind(wx.EVT_BUTTON, lambda evt: self.onCharacterise())
        self.elements['characteriseButton'] = characteriseButton

        label_use = cockpit.gui.device.Label(
            parent=self.panel, label='AO use')
        self.elements['label_use'] = label_use

        # Reset the DM actuators
        resetButton = wx.Button(self.panel, label='Reset DM')
        resetButton.Bind(wx.EVT_BUTTON, lambda evt: self.proxy.reset())
        self.elements['resetButton'] = resetButton

        # Apply the actuator values correcting the system aberrations
        applySysFlat = wx.Button(self.panel, label='System Flat')
        applySysFlat.Bind(wx.EVT_BUTTON, lambda evt: self.onApplySysFlat())
        self.elements['applySysFlat'] = applySysFlat

        # Visualise current interferometric phase
        visPhaseButton = wx.Button(self.panel, label='Visualise Phase')
        visPhaseButton.Bind(wx.EVT_BUTTON, lambda evt: self.onVisualisePhase())
        self.elements['visPhaseButton'] = visPhaseButton

        # Apply last actuator values
        applyLastPatternButton = wx.Button(self.panel, label='Apply last pattern')
        applyLastPatternButton.Bind(wx.EVT_BUTTON, lambda evt: self.onApplyLastPattern())
        self.elements['applyLastPatternButton'] = applyLastPatternButton

        # Button to perform sensorless correction
        sensorlessAOButton = wx.Button(self.panel, label='Sensorless AO')
        sensorlessAOButton.Bind(wx.EVT_BUTTON, lambda evt: self.displaySensorlessAOMenu())
        self.elements['Sensorless AO'] = sensorlessAOButton

        self.panel.Bind(wx.EVT_CONTEXT_MENU, self.onRightMouse)

        for e in self.elements.values():
            rowSizer.Add(e, 0, wx.EXPAND)
        sizer.Add(rowSizer, 0, wx.EXPAND)
        self.panel.SetSizerAndFit(sizer)
        self.hasUI = True
        return self.panel

    def getPiezoPos(self):
        return (cockpit.interfaces.stageMover.getAllPositions()[1][2])

    def movePiezoRelative(self, distance):
        current = self.getPiezoPos()
        currentpos = self.movePiezoAbsolute(current + distance)
        return currentpos

    def movePiezoAbsolute(self, position):
        #        originalHandlerIndex= cockpit.interfaces.stageMover.mover.curHandlerIndex
        #        interfaces.cockpit.stageMover.mover.curHandlerIndex=1
        handler = cockpit.interfaces.stageMover.mover.axisToHandlers[2][1]
        handler.moveAbsolute(position)
        #        cockpit.interfaces.stageMover.mover.curHandlerIndex=originalHandlerIndex
        return (self.getPiezoPos())

    def bin_ndarray(self, ndarray, new_shape, operation='sum'):
        """
        Function acquired from Stack Overflow: https://stackoverflow.com/a/29042041. Stack Overflow or other Stack Exchange
        sites is cc-wiki (aka cc-by-sa) licensed and requires attribution.
        Bins an ndarray in all axes based on the target shape, by summing or
            averaging.
        Number of output dimensions must match number of input dimensions and
            new axes must divide old ones.
        Example
        -------
        m = np.arange(0,100,1).reshape((10,10))
        n = bin_ndarray(m, new_shape=(5,5), operation='sum')
        print(n)
        [[ 22  30  38  46  54]
         [102 110 118 126 134]
         [182 190 198 206 214]
         [262 270 278 286 294]
         [342 350 358 366 374]]
        """
        operation = operation.lower()
        if not operation in ['sum', 'mean']:
            raise ValueError("Operation not supported.")
        if ndarray.ndim != len(new_shape):
            raise ValueError("Shape mismatch: {} -> {}".format(ndarray.shape,
                                                               new_shape))
        compression_pairs = [(d, c // d) for d, c in zip(new_shape,
                                                         ndarray.shape)]
        flattened = [l for p in compression_pairs for l in p]
        ndarray = ndarray.reshape(flattened)
        for i in range(len(new_shape)):
            op = getattr(ndarray, operation)
            ndarray = op(-1 * (i + 1))
        return ndarray

    def onSelectCircle(self, event):
        image_raw = self.proxy.acquire_raw()
        if np.max(image_raw) > 10:
            original_dim = int(np.shape(image_raw)[0])
            resize_dim = 512

            while original_dim % resize_dim is not 0:
                resize_dim -= 1

            if resize_dim < original_dim / resize_dim:
                resize_dim = int(np.round(original_dim / resize_dim))

            scale_factor = original_dim / resize_dim
            temp = self.bin_ndarray(image_raw, new_shape=(resize_dim, resize_dim), operation='mean')
            self.createCanvas(temp, scale_factor)
        else:
            print("Detecting nothing but background noise")

    def createCanvas(self, temp, scale_factor):
        app = wx.App()
        temp = np.require(temp, requirements='C')
        frame = selectCircle.ROISelect(input_image=temp, scale_factor=scale_factor)
        app.MainLoop()

    def onCalibrate(self):
        self.parameters = Config.getValue('dm_circleParams')
        self.proxy.set_roi(self.parameters[0], self.parameters[1],
                           self.parameters[2])

        try:
            self.proxy.get_roi()
        except Exception as e:
            try:
                self.parameters = Config.getValue('dm_circleParams')
                self.proxy.set_roi(self.parameters[0], self.parameters[1],
                                   self.parameters[2])
            except:
                raise e

        try:
            self.proxy.get_fourierfilter()
        except Exception as e:
            try:
                test_image = self.proxy.acquire()
                self.proxy.set_fourierfilter(test_image=test_image)
            except:
                raise e

        controlMatrix, sys_flat = self.proxy.calibrate(numPokeSteps=5)
        Config.setValue('dm_controlMatrix', np.ndarray.tolist(controlMatrix))
        Config.setValue('dm_sys_flat', np.ndarray.tolist(sys_flat))

    def onCharacterise(self):
        self.parameters = Config.getValue('dm_circleParams')
        self.proxy.set_roi(self.parameters[0], self.parameters[1],
                           self.parameters[2])

        try:
            self.proxy.get_roi()
        except Exception as e:
            try:
                self.parameters = Config.getValue('dm_circleParams')
                self.proxy.set_roi(self.parameters[0], self.parameters[1],
                                   self.parameters[2])
            except:
                raise e

        try:
            self.proxy.get_fourierfilter()
        except Exception as e:
            try:
                test_image = self.proxy.acquire()
                self.proxy.set_fourierfilter(test_image=test_image)
            except:
                raise e

        try:
            self.proxy.get_controlMatrix()
        except Exception as e:
            try:
                self.controlMatrix = Config.getValue('dm_controlMatrix')
                self.proxy.set_controlMatrix(self.controlMatrix)
            except:
                raise e
        assay = self.proxy.assess_character()
        file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                 'cockpit', 'characterisation_assay')
        np.save(file_path, assay)

        # Show characterisation assay, excluding piston
        app = wx.App()
        frame = charAssayViewer.viewCharAssay(assay[1:, 1:])
        app.MainLoop()

    def onVisualisePhase(self):
        self.parameters = Config.getValue('dm_circleParams')
        self.proxy.set_roi(self.parameters[0], self.parameters[1],
                           self.parameters[2])

        try:
            self.proxy.get_roi()
        except Exception as e:
            try:
                param = np.asarray(Config.getValue('dm_circleParams'))
                self.proxy.set_roi(y0=param[0], x0=param[1],
                                   radius=param[2])
            except:
                raise e

        try:
            self.proxy.get_fourierfilter()
        except:
            try:
                test_image = self.proxy.acquire()
                self.proxy.set_fourierfilter(test_image=test_image)
            except Exception as e:
                raise e

        interferogram, unwrapped_phase = self.proxy.acquire_unwrapped_phase()
        interferogram_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                               'cockpit', 'interferogram')
        np.save(interferogram_file_path, interferogram)

        interferogram_ft = np.fft.fftshift(np.fft.fft2(interferogram))
        interferogram_ft_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                                  'cockpit', 'interferogram_ft')
        np.save(interferogram_ft_file_path, interferogram_ft)

        unwrapped_phase_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                                 'cockpit', 'unwrapped_phase')
        np.save(unwrapped_phase_file_path, unwrapped_phase)

        unwrapped_phase = np.require(unwrapped_phase, requirements='C')
        power_spectrum = np.require(np.log(abs(interferogram_ft)), requirements='C')

        app = wx.App()
        frame = phaseViewer.viewPhase(unwrapped_phase, power_spectrum)
        app.MainLoop()

    def onApplySysFlat(self):
        self.sys_flat_values = np.asarray(Config.getValue('dm_sys_flat'))
        self.proxy.send(self.sys_flat_values)

    def onApplyLastPattern(self):
        last_ac = self.proxy.get_last_actuator_values()
        self.proxy.send(last_ac)

    def showDebugWindow(self):
        # Ensure only a single instance of the window.
        global _windowInstance
        window = globals().get('_windowInstance')
        if window:
            try:
                window.Raise()
                return None
            except:
                pass
        # If we get this far, we need to create a new window.
        global _deviceInstance
        dmOutputWindow(self, parent=wx.GetApp().GetTopWindow()).Show()

    ### Sensorless AO functions ###

    ## Display a menu to the user letting them choose which camera
    # to use to perform sensorless AO. Of course, if only one camera is
    # available, then we just perform sensorless AO.
    def displaySensorlessAOMenu(self):
        self.showCameraMenu("Perform sensorless AO with %s camera",
                            self.correctSensorlessSetup)

    ## Generate a menu where the user can select a camera to use to perform
    # some action.
    # \param text String template to use for entries in the menu.
    # \param action Function to call with the selected camera as a parameter.
    def showCameraMenu(self, text, action):
        cameras = depot.getActiveCameras()
        if len(cameras) == 1:
            action(cameras[0])
        else:
            menu = wx.Menu()
            for i, camera in enumerate(cameras):
                menu.Append(i + 1, text % camera.descriptiveName)
                self.panel.Bind(wx.EVT_MENU,
                                lambda event, camera=camera: action(camera),
                                id=i + 1)
            cockpit.gui.guiUtils.placeMenuAtMouse(self.panel, menu)

    def correctSensorlessSetup(self, camera, nollZernike=np.array([11, 22, 5, 6, 7, 8, 9, 10])):
        print("Performing sensorless AO setup")
        # Note: Default is to correct Primary and Secondary Spherical aberration and both
        # orientations of coma, astigmatism and trefoil
        print("Checking for control matrix")
        try:
            self.proxy.get_controlMatrix()
        except Exception as e:
            try:
                self.controlMatrix = Config.getValue('dm_controlMatrix')
                self.proxy.set_controlMatrix(self.controlMatrix)
            except:
                raise e

        print("Setting Zernike modes")
        self.nollZernike = nollZernike

        self.actuator_offset = None

        self.sensorless_correct_coef = np.zeros(self.no_actuators)

        print("Subscribing to camera events")
        # Subscribe to camera events
        self.camera = camera
        events.subscribe("new image %s" % self.camera.name, self.correctSensorlessImage)

        # Get pixel size
        self.objectives = cockpit.depot.getHandlersOfType(cockpit.depot.OBJECTIVE)[0]
        self.pixelSize = self.objectives.getPixelSize()

        # Initialise the Zernike modes to apply
        print("Initialising the Zernike modes to apply")
        self.numMes = 9
        num_it = 2
        self.z_steps = np.linspace(-1.5, 1.5, self.numMes)

        for ii in range(num_it):
            it_zernike_applied = np.zeros((self.numMes * self.nollZernike.shape[0], self.no_actuators))
            for noll_ind in self.nollZernike:
                ind = np.where(self.nollZernike == noll_ind)[0][0]
                it_zernike_applied[ind * self.numMes:(ind + 1) * self.numMes,
                noll_ind - 1] = self.z_steps
            if ii == 0:
                self.zernike_applied = it_zernike_applied
            else:
                self.zernike_applied = np.concatenate((self.zernike_applied, it_zernike_applied))

        # Initialise stack to store correction iumages
        print("Initialising stack to store correction images")
        self.correction_stack = []

        print("Applying the first Zernike mode")
        # Apply the first Zernike mode
        print(self.zernike_applied[len(self.correction_stack), :])
        self.proxy.set_phase(self.zernike_applied[len(self.correction_stack), :], offset=self.actuator_offset)

        # Take image. This will trigger the iterative sensorless AO correction
        wx.CallAfter(self.takeImage)

    def correctSensorlessImage(self, image, timestamp):
        if len(self.correction_stack) < self.zernike_applied.shape[0]:
            print("Correction image %i/%i" % (len(self.correction_stack) + 1, self.zernike_applied.shape[0]))
            # Store image for current applied phase
            self.correction_stack.append(np.ndarray.tolist(image))
            wx.CallAfter(self.correctSensorlessProcessing)
        else:
            print("Error in unsubscribing to camera events. Trying again")
            events.unsubscribe("new image %s" % self.camera.name, self.correctSensorlessImage)

    def correctSensorlessProcessing(self):
        print("Processing sensorless image")
        if len(self.correction_stack) < self.zernike_applied.shape[0]:
            if len(self.correction_stack) % self.numMes == 0:
                # Find aberration amplitudes and correct
                ind = int(len(self.correction_stack) / self.numMes)
                nollInd = np.where(self.zernike_applied[len(self.correction_stack) - 1, :] != 0)[0][0] + 1
                print("Current Noll index being corrected: %i" % nollInd)
                current_stack = np.asarray(self.correction_stack)[(ind - 1) * self.numMes:ind * self.numMes, :, :]
                amp_to_correct, ac_pos_correcting = self.proxy.correct_sensorless_single_mode(image_stack=current_stack,
                                                                                              zernike_applied=self.z_steps,
                                                                                              nollIndex=nollInd,
                                                                                              offset=self.actuator_offset)
                self.actuator_offset = ac_pos_correcting
                self.sensorless_correct_coef[nollInd - 1] += amp_to_correct
                print("Aberrations measured: ", self.sensorless_correct_coef)
                print("Actuator positions applied: ", self.actuator_offset)

                # Advance counter by 1 and apply next phase
                self.proxy.set_phase(self.zernike_applied[len(self.correction_stack), :], offset=self.actuator_offset)

                # Take image, but ensure it's called after the phase is applied
                wx.CallAfter(self.takeImage)
            else:
                # Advance counter by 1 and apply next phase
                self.proxy.set_phase(self.zernike_applied[len(self.correction_stack), :], offset=self.actuator_offset)

                # Take image, but ensure it's called after the phase is applied
                time.sleep(0.1)
                wx.CallAfter(self.takeImage)
        else:
            # Once all images have been obtained, unsubscribe
            print("Unsubscribing to camera %s events" % self.camera.name)
            events.unsubscribe("new image %s" % self.camera.name, self.correctSensorlessImage)

            # Save full stack of images used
            self.correction_stack = np.asarray(self.correction_stack)
            correction_stack_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                                      'cockpit',
                                                      'sensorless_AO_correction_stack_%i%i%i_%i%i'
                                                      % (time.gmtime()[2], time.gmtime()[1], time.gmtime()[0],
                                                         time.gmtime()[3], time.gmtime()[4]))
            np.save(correction_stack_file_path, self.correction_stack)
            zernike_applied_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                                     'cockpit',
                                                     'sensorless_AO_zernike_applied_%i%i%i_%i%i'
                                                     % (time.gmtime()[2], time.gmtime()[1], time.gmtime()[0],
                                                        time.gmtime()[3], time.gmtime()[4]))
            np.save(zernike_applied_file_path, self.zernike_applied)
            nollZernike_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                                 'cockpit',
                                                 'sensorless_AO_nollZernike_%i%i%i_%i%i'
                                                 % (time.gmtime()[2], time.gmtime()[1], time.gmtime()[0],
                                                    time.gmtime()[3], time.gmtime()[4]))
            np.save(nollZernike_file_path, self.nollZernike)

            # Find aberration amplitudes and correct
            ind = int(len(self.correction_stack) / self.numMes)
            nollInd = np.where(self.zernike_applied[len(self.correction_stack) - 1, :] != 0)[0][0] + 1
            print("Current Noll index being corrected: %i" % nollInd)
            current_stack = np.asarray(self.correction_stack)[(ind - 1) * self.numMes:ind * self.numMes, :, :]
            amp_to_correct, ac_pos_correcting = self.proxy.correct_sensorless_single_mode(image_stack=current_stack,
                                                                                          zernike_applied=self.z_steps,
                                                                                          nollIndex=nollInd,
                                                                                          offset=self.actuator_offset)
            self.actuator_offset = ac_pos_correcting
            self.sensorless_correct_coef[nollInd - 1] += amp_to_correct
            print("Aberrations measured: ", self.sensorless_correct_coef)
            print("Actuator positions applied: ", self.actuator_offset)
            sensorless_correct_coef_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                                             'cockpit',
                                                             'sensorless_correct_coef_%i%i%i_%i%i'
                                                             % (time.gmtime()[2], time.gmtime()[1], time.gmtime()[0],
                                                                time.gmtime()[3], time.gmtime()[4]))
            np.save(sensorless_correct_coef_file_path, self.sensorless_correct_coef)
            ac_pos_sensorless_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                                       'cockpit',
                                                       'ac_pos_sensorless_%i%i%i_%i%i'
                                                       % (time.gmtime()[2], time.gmtime()[1], time.gmtime()[0],
                                                          time.gmtime()[3], time.gmtime()[4]))
            np.save(ac_pos_sensorless_file_path, self.actuator_offset)

            log_file_path = os.path.join(os.path.expandvars('%LocalAppData%'),
                                         'cockpit',
                                         'sensorless_AO_logger.txt')
            log_file = open(log_file_path, "a+")
            log_file.write("Time stamp: %i:%i:%i %i/%i/%i\n" % (
            time.gmtime()[3], time.gmtime()[4], time.gmtime()[5], time.gmtime()[2], time.gmtime()[1], time.gmtime()[0]))
            log_file.write("Aberrations measured: ")
            log_file.write(str(self.sensorless_correct_coef))
            log_file.write("\n")
            log_file.write("Actuator positions applied: ")
            log_file.write(str(self.actuator_offset))
            log_file.write("\n")
            log_file.close()

            print("Actuator positions applied: ", self.actuator_offset)
            self.proxy.send(self.actuator_offset)
            wx.CallAfter(self.takeImage)


# This debugging window lets each digital lineout of the DSP be manipulated
# individually.
class dmOutputWindow(wx.Frame):
    def __init__(self, AoDevice, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## dm Device instance.
        self.dm = AoDevice
        self.SetTitle("Deformable Mirror AO device control")
        # Contains all widgets.
        self.panel = wx.Panel(self)
        font = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        allPositions = cockpit.interfaces.stageMover.getAllPositions()
        self.piezoPos = allPositions[1][2]
        textSizer = wx.BoxSizer(wx.VERTICAL)
        self.piezoText = wx.StaticText(self.panel, -1, str(self.piezoPos),
                                       style=wx.ALIGN_CENTER)
        self.piezoText.SetFont(font)
        textSizer.Add(self.piezoText, 0, wx.EXPAND | wx.ALL, border=5)
        mainSizer.Add(textSizer, 0, wx.EXPAND | wx.ALL, border=5)
        self.panel.SetSizerAndFit(mainSizer)
        events.subscribe('stage position', self.onMove)

    def onMove(self, axis, *args):
        if axis != 2:
            # We only care about the Z axis.
            return
        self.piezoText.SetLabel(
            str(cockpit.interfaces.stageMover.getAllPositions()[1][2]))