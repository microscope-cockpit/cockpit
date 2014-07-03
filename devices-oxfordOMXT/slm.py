from config import config
import Pyro4
import depot
import device
import events
import util.logger
from experiment.structuredIllumination import SIExperiment
from experiment.structuredIllumination import COLLECTION_ORDERS
from math import pi, sin, radians
from itertools import product

ANGLE_OFFSET = pi / 6.
PHASE_OFFSET = 0.
ANGLE_RANGE = 2. * pi
PHASE_RANGE = 2. * pi

DIFF_ANGLES = {
    'fallback': 8,
    '100xOil': 8.5,
}

CLASS_NAME = 'SpatialLightModulatorDevice'

def loop_in_order(arrayList, order=None):
    """Iterate over a list of lists in a specified order."""
    if order == None:
        order = range(len(arrayList))

    order.reverse()
    pList = product(*[arrayList[n] for n in order])

    reorder = [order.index(n) for n in range(len(order))]

    for p in pList:
        yield tuple(p[n] for n in reorder)


class SpatialLightModulatorDevice(device.Device):
    """Manage the spatial light modulator used to make SI patterns."""
    def __init__(self):
        device.Device.__init__(self)
        ## Telnet connection to the device.
        self.connection = None
        ## IP address of the device.
        self.ipAddress = config['slm'].get('ipAddress')
        self.port = config['slm'].get('port')
        ## Set of handlers we control.
        self.handlers = set()
        ## Our ExperimentExecutor handler.
        self.executor = None 
        events.subscribe('prepare for experiment', self.prepareForExperiment)
        events.subscribe('experiment complete', self.cleanupAfterExperiment)
        self.patternparms = []


    def initialize(self):
        """Connect to the device."""
        uri = 'PYRO:pyroSLM@%s:%d' % (self.ipAddress, self.port)
        print uri
        self.connection = Pyro4.Proxy(uri)
        self.connection._pyroTimeout = 10


    def prepareForExperiment(self, experiment):
        """ Get ready for an experiment.

        Generate patterns, load patterns, turn on the SLM and set it ready
        to receive triggers.
        """
        if experiment.__class__ == SIExperiment:
            ## Examine experiment, generate patterns, load patterns, 
            # and turn on the SLM.
            ## List of (angle, phase, z).
            ## At each position, there will be one or more exposures.
            # For now we will just use the longest wavelength from
            # the complete set of exposures, but see below.
            wavelength = None
            for cameras, lights in experiment.exposureSettings:
                if lights:
                    wavelength = max([wavelength] +
                        [light[0].wavelength * (light[1] > 0)
                        for light in lights]
                        )
            if wavelength <= 0:
                raise(Except("No wavelengths found for pattern generation."))


            ## The SIM pattern should have a line pitch that puts the
            # first-order spots at the edge of the objective's back
            # pupil.  This will depend on the pupil diameter and the 
            # optical setup.  One way to parameterise this is in terms of
            # the required diffraction angle for the first order beams.
            # The objective handler should be modified so it can tell
            # us what angle we need the diffraction orders at.
            # Until then, pull the parameter from a module variable.
            objectiveHandler = depot.getHandlerWithName('objective')
            diffractionAngle = DIFF_ANGLES.get(objectiveHandler.curObjective)
            diffractionAngle = diffractionAngle or DIFF_ANGLES.get('fallback')
            linepitch = (wavelength / 1000.) / sin(radians(diffractionAngle))

            ## We could just use experiment.genSIParameters, but this
            # will include duplicate patterns for each Z position
            # (either consecutively, or in repeats of basic series, 
            # depending on the collection order).  Loading patterns takes
            # time, so we try to avoid unnecessary pattern repetition.
            numAngles = experiment.numAngles
            numPhases = experiment.numPhases
            angles = [ANGLE_OFFSET +
                (ANGLE_RANGE / numAngles) * n for n in range(numAngles)]
            phases = [PHASE_OFFSET + 
                (PHASE_RANGE / numPhases) * n for n in range(numPhases)]

            order = list(COLLECTION_ORDERS.get(experiment.collectionOrder))
            order.remove(2) # We don't care about Z, only phase and angle.
            order.reverse()
            
            self.patternparms = [(linepitch, angle, phase, wavelength)
                for (angle, phase) in loop_in_order([angles, phases], order)]

            self.connection.generate_stripe_series(self.patternparms)
            self.connection.load_images()
            self.connection.run()

            ## Send these patternparms to the SLM.

            ## Ideally, we should determine the longest wavelength for each
            # exposure and use it to generate the SI pattern, but this
            # requires modifications to the expose method to send additional
            # triggers to the SLM on wavelength change.  Given those
            # changes, the code here would look something like:
            #
            #(for each position)...
            # wavelength = None
            # oldWavelength = None
            # for cameras, lights in experiment.exposureSettings:
            #     if lights:
            #         wavelength = max([
            #             light[0].wavelength * (light[1] > 0) 
            #             for light in lights
            #             ])
            #     else: wavelength = None
            #     if wavelength and wavelength != oldWavelength:
            #         ## We need a new image and expose needs to trigger
            #         # the SLM.



    ## Experiment finished: turn off the SLM.
    def cleanupAfterExperiment(self):
        self.connection.stop()
