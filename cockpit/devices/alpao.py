#Cockpit Device file for Alpao AO device.
#Copyright Ian Dobbie, 2017
#released under the GPL 3+
#
#This file provides the cockpit end of the driver for the Alpao deformable
#mirror as currently mounted on DeepSIM in Oxford

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
import Tkinter as tk
from PIL import Image, ImageTk
import cockpit.util.userConfig as Config
import cockpit.handlers.executor

import numpy as np
import scipy.stats as stats

#the AO device subclasses Device to provide compatibility with microscope.
class Alpao(device.Device):
    def __init__(self, name, config={}):
        device.Device.__init__(self, name, config)
        self.proxy = None
        self.sendImage=False
        self.curCamera = None

        self.buttonName='Alpao'

        ## Connect to the remote program
    def initialize(self):
        self.proxy = Pyro4.Proxy(self.uri)
        self.proxy.set_trigger(cp_ttype="RISING_EDGE",cp_tmode="ONCE")
        self.no_actuators = self.proxy.get_n_actuators()
        self.actuator_slopes = np.zeros(self.no_actuators)
        self.actuator_intercepts = np.zeros(self.no_actuators)

        #Excercise the DM to remove residual static and then set to 0 position
        for ii in range(20):
            self.proxy.send((np.zeros(self.no_actuators)+(ii%2)))
        self.proxy.reset()

        #Create accurate look up table for certain Z positions
        ##LUT dict has key of Z positions
        try:
            LUT_array = np.loadtxt("C:\\cockpit\\nick\\cockpit\\remote_focus_LUT.txt")
            self.LUT = {}
            for ii in (LUT_array[:,0])[:]:
                self.LUT[ii] = LUT_array[np.where(LUT_array == ii)[0][0],1:]
        except:
            self.LUT = None

        ##slopes and intercepts are used for extrapolating values not
        ##found in the LUT dict
        if self.LUT is not None:
            self.actuator_slopes, self.actuator_intercepts = \
                self.remote_ac_fits(LUT_array, self.no_actuators)

        #Initiate a table for calibrating the look up table
        self.remote_focus_LUT = []

        #Load values from config
        try:
            self.parameters = Config.getValue('alpao_circleParams', isGlobal=True)
            self.proxy.set_roi(self.parameters[0], self.parameters[1],
                                     self.parameters[2])
        except:
            pass
        try:
            self.controlMatrix = Config.getValue('alpao_controlMatrix', isGlobal=True)
            self.proxy.set_controlMatrix(self.controlMatrix)
        except:
            pass

        # subscribe to enable camera event to get access the new image queue
        events.subscribe('camera enable',
                        lambda c, isOn: self.enablecamera(c, isOn))

    def takeImage(self):
        cockpit.interfaces.imager.takeImage()

    def enablecamera(self, camera, isOn):
        self.curCamera = camera
        # Subscribe to new image events only after canvas is prepared.

    def remote_ac_fits(self,LUT_array, no_actuators):
        #For Z positions which have not been calibrated, approximate with
        #a regression of known positions.

        actuator_slopes = np.zeros(no_actuators)
        actuator_intercepts = np.zeros(no_actuators)

        pos = np.sort(LUT_array[:,0])[:]
        ac_array = np.zeros((np.shape(LUT_array)[0],no_actuators))

        count = 0
        for jj in pos:
            ac_array[count,:] = LUT_array[np.where(LUT_array == jj)[0][0],1:]
            count += 1

        for kk in range(no_actuators):
            s, i, r, p, se = stats.linregress(pos, ac_array[:,kk])
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
            if reducedParams[0:length] == reducedParams[length:2*length]:
                sequenceLength = length
                break
        sequence = reducedParams[0:sequenceLength]

        #Calculate DM positions
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
                ## This is the type for remote focus calibration experiment
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
            np.savetxt('C:\\cockpit\\nick\\cockpit\\remote_focus_LUT.txt',
                       np.asanyarray(self.remote_focus_LUT))
            Config.setValue('alpao_remote_focus_LUT', self.remote_focus_LUT, isGlobal=True)

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

        selectCircleButton = cockpit.gui.toggleButton.ToggleButton(
            label='Select ROI',
        #Button to calibrate the DM
            activateAction=self.onSelectCircle,
            deactivateAction=self.deactivateSelectCircle,
            activeLabel='Selecting ROI',
            inactiveLabel='Select ROI',
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        self.elements['selectCircleButton'] = selectCircleButton

        calibrateButton = cockpit.gui.toggleButton.ToggleButton(
            label='Calibrate',
        #Button to calibrate the DM
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        calibrateButton.Bind(wx.EVT_LEFT_DOWN, lambda evt: self.onCalibrate())
        self.elements['calibrateButton'] = calibrateButton

        characteriseButton = cockpit.gui.toggleButton.ToggleButton(
            label='Characterise',
        #Button to calibrate the DM
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        characteriseButton.Bind(wx.EVT_LEFT_DOWN, lambda evt: self.onCharacterise())
        self.elements['characteriseButton'] = characteriseButton

        label_use = cockpit.gui.device.Label(
            parent=self.panel, label='AO use')
        self.elements['label_use'] = label_use

        # Reset the DM actuators
        resetButton = cockpit.cockpit.gui.toggleButton.ToggleButton(
            label='Reset DM',
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        resetButton.Bind(wx.EVT_LEFT_DOWN, lambda evt:self.proxy.reset())
        self.elements['resetButton'] = resetButton

        # Step the focal plane up one step
        applySysFlat = cockpit.gui.toggleButton.ToggleButton(
            label='System Flat',
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        applySysFlat.Bind(wx.EVT_LEFT_DOWN, lambda evt: self.onApplySysFlat())
        self.elements['applySysFlat'] = applySysFlat

        # Visualise current interferometric phase
        visPhaseButton = cockpit.gui.toggleButton.ToggleButton(
            label='Visualise Phase',
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        visPhaseButton.Bind(wx.EVT_LEFT_DOWN, lambda evt: self.onVisualisePhase())
        self.elements['visPhaseButton'] = visPhaseButton

        # Button to flatten the wavefront
        flattenButton = cockpit.gui.toggleButton.ToggleButton(
            label='Flatten',
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        flattenButton.Bind(wx.EVT_LEFT_DOWN, lambda evt: self.onFlatten())
        self.elements['flattenButton'] = flattenButton

        # Button to perform sensorless correction
        sensorlessAOButton = cockpit.gui.toggleButton.ToggleButton(
            label='Sensorless AO',
            parent=self.panel,
            size=cockpit.gui.device.DEFAULT_SIZE)
        sensorlessAOButton.Bind(wx.EVT_LEFT_DOWN, lambda evt: self.correctSensorlessSetup())
        self.elements['Sensorless AO'] = sensorlessAOButton

        for e in self.elements.values():
            rowSizer.Add(e)
        sizer.Add(rowSizer)
        self.panel.SetSizerAndFit(sizer)
        self.hasUI = True
        return self.panel

    def getPiezoPos(self):
        return(cockpit.interfaces.stageMover.getAllPositions()[1][2])

    def movePiezoRelative(self, distance):
        current=self.getPiezoPos()
        currentpos=self.movePiezoAbsolute(current+distance)
        return currentpos

    def movePiezoAbsolute(self, position):
#        originalHandlerIndex= cockpit.interfaces.stageMover.mover.curHandlerIndex
#        interfaces.cockpit.stageMover.mover.curHandlerIndex=1
        handler=cockpit.interfaces.stageMover.mover.axisToHandlers[2][1]
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

    def onSelectCircle(self):
        image_raw = self.proxy.acquire_raw()
        if np.max(image_raw) > 10:
            temp = self.bin_ndarray(image_raw, new_shape=(512, 512), operation='mean')
            self.createCanvas(temp)
        else:
            print("Detecting nothing but background noise")

    def createCanvas(self,temp):
        app = App(image_np=temp)
        app.master.title('Select a circle')
        app.mainloop()

    def deactivateSelectCircle(self):
        # Read in the parameters needed for the phase mask
        try:
            self.parameters = np.asarray(Config.getValue('alpao_circleParams', isGlobal = True))
        except IOError:
            print("Error: Masking parameters do not exist. Please select circle.")
            return
        self.proxy.set_roi(self.parameters[0], self.parameters[1],
                                         self.parameters[2])

    def onCalibrate(self):
        try:
            self.proxy.get_roi()
        except Exception as e:
            try:
                self.parameters = Config.getValue('alpao_circleParams', isGlobal=True)
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

        controlMatrix, sys_flat = self.proxy.calibrate(numPokeSteps = 5)
        Config.setValue('alpao_controlMatrix', np.ndarray.tolist(controlMatrix), isGlobal=True)
        Config.setValue('alpao_sys_flat', np.ndarray.tolist(sys_flat), isGlobal=True)

    def onCharacterise(self):
        try:
            self.proxy.get_roi()
        except Exception as e:
            try:
                self.parameters = Config.getValue('alpao_circleParams', isGlobal=True)
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
                self.controlMatrix = Config.getValue('alpao_controlMatrix', isGlobal=True)
                self.proxy.set_controlMatrix(self.controlMatrix)
            except:
                raise e
        assay = self.proxy.assess_character()
        np.save('C:\\cockpit\\nick\\cockpit\\characterisation_assay', assay)
        app = View(image_np=assay)
        app.master.title('Characterisation')
        app.mainloop()

    def onVisualisePhase(self):
        try:
            self.proxy.get_roi()
        except Exception as e:
            try:
                param = np.asarray(Config.getValue('alpao_circleParams', isGlobal=True))
                self.proxy.set_roi(y0 = param[0], x0 = param[1],
                                             radius = param[2])
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
        np.save('C:\\cockpit\\nick\\cockpit\\interferogram', interferogram)
        interferogram_ft = np.fft.fftshift(np.fft.fft2(interferogram))
        np.save('C:\\cockpit\\nick\\cockpit\\interferogram_ft', interferogram_ft)
        np.save('C:\\cockpit\\nick\\cockpit\\unwrapped_phase', unwrapped_phase)
        original_dim = int(np.shape(unwrapped_phase)[0])
        resize_dim = original_dim/2
        while original_dim % resize_dim is not 0:
            resize_dim -= 1
        unwrapped_phase_resize = self.bin_ndarray(unwrapped_phase, new_shape=
                                    (resize_dim, resize_dim), operation='mean')
        cycle_diff = abs(np.max(unwrapped_phase) - np.min(unwrapped_phase))/(2.0*np.pi)
        rms_phase = np.sqrt(np.mean(unwrapped_phase**2))
        app = View(image_np=unwrapped_phase_resize)
        app.master.title('Unwrapped interferogram. '
                         'Cycle difference = %f, RMS phase = %f'
                         %(cycle_diff, rms_phase))
        app.mainloop()

    def onFlatten(self):
        try:
            self.proxy.get_roi()
        except Exception as e:
            try:
                self.parameters = Config.getValue('alpao_circleParams', isGlobal=True)
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
                self.controlMatrix = Config.getValue('alpao_controlMatrix', isGlobal=True)
                self.proxy.set_controlMatrix(self.controlMatrix)
            except:
                raise e
        flat_values = self.proxy.flatten_phase(iterations=10)
        Config.setValue('alpao_flat_values', np.ndarray.tolist(flat_values), isGlobal=True)

    def onApplySysFlat(self):
        sys_flat_values = np.asarray(Config.getValue('alpao_sys_flat', isGlobal=True))
        self.proxy.send(sys_flat_values)

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
        alpaoOutputWindow(self, parent=wx.GetApp().GetTopWindow()).Show()

    ### Sensorless AO functions ###

    def correctSensorlessSetup(self,nollZernike = None):
        print("Performing sensorless AO setup")
        # Note: Default is to correct Primary and Secondary Spherical aberration and both
        # orientations of coma, astigmatism and trefoil
        try:
            self.proxy.get_controlMatrix()
        except Exception as e:
            try:
                self.controlMatrix = Config.getValue('alpao_controlMatrix', isGlobal=True)
                self.proxy.set_controlMatrix(self.controlMatrix)
            except:
                raise e

        if np.any(nollZernike) == None:
            self.nollZernike = np.array([5, 6, 7, 8, 9, 10, 11, 22])
        else:
            self.nollZernike = nollZernike

        #Subscribe to camera events
        events.subscribe("new image %s" % self.curCamera.name, self.correctSensorlessImage)

        #Initialise Fourier ring mask
        self.objectives = cockpit.depot.getHandlersOfType(cockpit.depot.OBJECTIVE)[0]
        self.pixelSize = self.objectives.getPixelSize()
        self.proxy.set_sensorless_ring_mask(size = self.curCamera.getImageSize(), pixel_size = self.pixelSize * 10 ** -6)

        #Initialise the Zernike modes to apply
        z_steps = np.linspace(-1.25,1.25,6)
        self.zernike_applied = np.zeros((z_steps.shape[0]*self.nollZernike.shape[0],self.no_actuators))
        for noll_ind in self.nollZernike:
            ind = np.where(self.nollZernike == noll_ind)[0][0]
            self.zernike_applied[ind * z_steps.shape[0]:(ind + 1) * z_steps.shape[0], noll_ind - 1] = z_steps

        #Initialise stack to store correction iumages
        self.correction_stack = []

        # Apply the first Zernike mode
        self.proxy.set_phase(self.zernike_applied[len(self.correction_stack), :])

        # Take image. This will trigger the iterative sensorless AO correction
        wx.CallAfter(self.takeImage)

    def correctSensorlessImage(self, image, timestamp):
        if len(self.correction_stack) < self.zernike_applied.shape[0]:
            print("Correction image %i/%i" %(len(self.correction_stack)+1,self.zernike_applied.shape[0]))
            #Store image for current applied phase
            self.correction_stack.append(np.ndarray.tolist(image))
            wx.CallAfter(self.correctSensorlessProcessing)
        else:
            print("Error in unsubscribing to camera events. Trying again")
            events.unsubscribe("new image %s" % self.curCamera.name, self.correctSensorlessImage)


    def correctSensorlessProcessing(self):
        print("Processing sensorless image")
        if len(self.correction_stack) < self.zernike_applied.shape[0]:
            #Advance counter by 1 and apply next phase
            self.proxy.set_phase(self.zernike_applied[len(self.correction_stack), :])

            #Take image, but ensure it's called after the phase is applied
            wx.CallAfter(self.takeImage)
        else:
            #Once all images have been obtained, unsubscribe
            events.unsubscribe("new image %s" % self.curCamera.name, self.correctSensorlessImage)

            #Save full stack of images used
            self.correction_stack = np.asarray(self.correction_stack)
            np.save("C:\\cockpit\\nick\\cockpit\\sensorless_AO_correction_stack", self.correction_stack)
            np.save("C:\\cockpit\\nick\\cockpit\\sensorless_AO_zernike_applied", self.zernike_applied)
            np.save("C:\\cockpit\\nick\\cockpit\\sensorless_AO_nollZernike", self.nollZernike)

            #Find aberration amplitudes and correct
            sensorless_correct_coef, ac_pos_sensorless = self.proxy.correct_sensorless_all_modes(self.correction_stack,
                                                                              self.zernike_applied, self.nollZernike)
            print("Aberrations measured: ", sensorless_correct_coef)
            print("Actuator positions applied: ", ac_pos_sensorless)
            np.save("C:\\cockpit\\nick\\cockpit\\sensorless_correct_coef", sensorless_correct_coef)
            np.save("C:\\cockpit\\nick\\cockpit\\ac_pos_sensorless", ac_pos_sensorless)

## This debugging window lets each digital lineout of the DSP be manipulated
# individually.
class alpaoOutputWindow(wx.Frame):
    def __init__(self, AoDevice, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## alpao Device instance.
        self.alpao = AoDevice
        self.SetTitle("Alpao AO device control")
        # Contains all widgets.
        self.panel = wx.Panel(self)
        font=wx.Font(12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        allPositions = cockpit.interfaces.stageMover.getAllPositions()
        self.piezoPos = allPositions[1][2]
        textSizer=wx.BoxSizer(wx.VERTICAL)
        self.piezoText=wx.StaticText(self.panel,-1,str(self.piezoPos),
                style=wx.ALIGN_CENTER)
        self.piezoText.SetFont(font)
        textSizer.Add(self.piezoText, 0, wx.EXPAND|wx.ALL,border=5)
        mainSizer.Add(textSizer, 0,  wx.EXPAND|wx.ALL,border=5)
        self.panel.SetSizerAndFit(mainSizer)
        events.subscribe('stage position', self.onMove)


    def onMove(self, axis, *args):
        if axis != 2:
            # We only care about the Z axis.
            return
        self.piezoText.SetLabel(
            str(cockpit.interfaces.stageMover.getAllPositions()[1][2]))

##This is a window for selecting the ROI for interferometry
#!/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2017 Mick Phillips (mick.phillips@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Display a window that allows the user to select a circular area."""

class App(tk.Frame):
    def __init__(self, image_np, master=None):
        tk.Frame.__init__(self, master)
        self.pack()
        self.ratio = 1
        self.offset = [45, 50]
        self.image_np = image_np
        self.create_widgets()

    def create_widgets(self):
        self.canvas = Canvas(self, width=600, height=600)
        self.array = np.asarray(self.image_np)
        self.convert = Image.fromarray(self.array)
        self.image = ImageTk.PhotoImage(image = self.convert)
        self.canvas.create_image(self.offset[0], self.offset[1], anchor = tk.NW, image = self.image)
        self.canvas.pack()

class Canvas(tk.Canvas):
    def __init__(self, *args, **kwargs):
        tk.Canvas.__init__(self, *args, **kwargs)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Button-3>", self.on_click)
        self.bind("<B1-Motion>", self.circle_resize)
        self.bind("<B3-Motion>", self.circle_drag)
        self.bind("<ButtonRelease>", self.on_release)
        self.circle = None
        self.p_click = None
        self.bbox_click = None
        self.centre = [0,0]
        self.radius = 0
        self.ratio = 4
        self.offset = [45, 50]

    def on_release(self, event):
        self.p_click = None
        self.bbox_click = None

    def on_click(self, event):
        if self.circle == None:
            self.circle = self.create_oval((event.x-1, event.y-1, event.x+1, event.y+1))
            self.centre[0] = (event.x - self.offset[0]) * self.ratio
            self.centre[1] = (event.y - self.offset[1]) * self.ratio
            self.radius = ((event.x+1 - event.x+1 + 1) * self.ratio)/2
            Config.setValue('alpao_circleParams', (self.centre[1], self.centre[0], self.radius), isGlobal=True)

    def circle_resize(self, event):
        if self.circle is None:
            return
        if self.p_click is None:
            self.p_click = (event.x, event.y)
            self.bbox_click = self.bbox(self.circle)
            return
        bbox = self.bbox(self.circle)
        unscaledCentre = ((bbox[2] + bbox[0])/2, (bbox[3] + bbox[1])/2)
        r0 = ((self.p_click[0] - unscaledCentre[0])**2 + (self.p_click[1] - unscaledCentre[1])**2)**0.5
        r1 = ((event.x - unscaledCentre[0])**2 + (event.y - unscaledCentre[1])**2)**0.5
        scale = r1 / r0
        self.scale(self.circle, unscaledCentre[0], unscaledCentre[1], scale, scale)
        self.p_click= (event.x, event.y)
        self.radius = ((self.bbox(self.circle)[2] - self.bbox(self.circle)[0]) * self.ratio)/2
        Config.setValue('alpao_circleParams', (self.centre[1], self.centre[0], self.radius), isGlobal=True)

    def circle_drag(self, event):
        if self.circle is None:
            return
        if self.p_click is None:
            self.p_click = (event.x, event.y)
            return
        self.move(self.circle,
                  event.x - self.p_click[0],
                  event.y - self.p_click[1])
        self.p_click = (event.x, event.y)
        bbox = self.bbox(self.circle)
        unscaledCentre = ((bbox[2] + bbox[0]) / 2, (bbox[3] + bbox[1]) / 2)
        self.centre[0] = (unscaledCentre[0] - self.offset[0]) * self.ratio
        self.centre[1] = (unscaledCentre[1] - self.offset[1]) * self.ratio
        Config.setValue('alpao_circleParams', (self.centre[1], self.centre[0], self.radius), isGlobal=True)
        self.update()

class View(tk.Frame):
    def __init__(self, image_np, master=None):
        tk.Frame.__init__(self, master)
        self.pack()
        self.ratio = 1
        self.offset = [25, 25]
        self.image_np = image_np
        self.create_widgets()

    def create_widgets(self):
        self.canvas = tk.Canvas(self, width=700, height=700)
        self.array = np.asarray(self.image_np)
        self.array_norm = (self.image_np/np.max(self.image_np))*255.0
        self.convert = Image.fromarray(self.array)
        self.convert_flip = self.convert.transpose(Image.FLIP_TOP_BOTTOM)
        self.image = ImageTk.PhotoImage(image = self.convert_flip)
        self.canvas.create_image(self.offset[0], self.offset[1], anchor = tk.NW, image = self.image)
        self.canvas.pack()
