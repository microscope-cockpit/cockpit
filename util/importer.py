import imp
import importlib
import os

## Scan through the specified root and import all modules in it that do not
# contain a substring from the list forbiddenModules.
def getModulesFrom(root, forbiddenModules = []):
    fileHandle, path, description = imp.find_module(root)
    result = []
    for moduleName in os.listdir(path):
        # \todo Should we allow other file extensions?
        if moduleName.endswith('py'):
            canUse = True
            # Check it's not one of the "standard" modules that doesn't
            # actually represent a device. 
            for forbidden in forbiddenModules:
                if forbidden in moduleName:
                    canUse = False
                    break
            if not canUse:
                continue

            # Import the module, create a class from it, and add that 
            # class instance to our list.
            importPath = '.'.join([root, os.path.splitext(moduleName)[0]])
            module = importlib.import_module(importPath)
            result.append(module)
    return result

