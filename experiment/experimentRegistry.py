## This module lists the available experiments. Depending on the scope,
# some experiment types may not be appropriate (due to requiring
# hardware that is not available).

import offsetGainCorrection
import optoScriptExample
import responseMap
import structuredIllumination
import stutteredZStack
import sweptShutter
import zStack

## List of registered modules.
registeredModules = [zStack, sweptShutter,
            offsetGainCorrection, responseMap, stutteredZStack,
            optoScriptExample, structuredIllumination]


## Add another experiment to the registered set.
def registerModule(module, index = -1):
    global registeredModules
    # HACK: convert -1 to end-of-list.
    if index == -1:
        index = len(registeredModules)
    registeredModules.insert(index, module)
    

## Retrieve all registered experiments.
def getExperimentModules():
    global registeredModules
    return registeredModules
