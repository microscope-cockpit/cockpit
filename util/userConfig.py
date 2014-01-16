import logger
import files
import util.user

import os
# We could use pickle here instead, but I prefer config
# files that I can read myself.
import pprint
import sys
import traceback

## @package userConfig 
# This module handles loading and saving changes to user configuration, which
# is used to remember individual users' settings (and a few global settings)
# for dialogs and the like.

## Directory that contains config files.
CONFIG_ROOT_PATH = files.getConfigDir()
## Username for config settings that don't belong to a specific user.
GLOBAL_USERNAME = 'global'
## Suffix we append to each username to help avoid name conflicts
CONFIG_SUFFIX = "-MUI-config"

## In-memory version of the config; program singleton.
config = {}
## Indicates if the config has changed during a function call
didChange = False

## Printer for saving the config to file
printer = pprint.PrettyPrinter()

## Open the config file and unserialize its contents.
def loadConfig():
    global config
    sys.path.append(CONFIG_ROOT_PATH)
    # Ensure that the config directory exists. Normally the util.files
    # directory does this, but it depends on config...
    if not os.path.exists(CONFIG_ROOT_PATH):
        os.mkdir(CONFIG_ROOT_PATH)
    # Ensure config exists for all users.
    userList = util.user.getUsers() + [GLOBAL_USERNAME]
    for user in userList:
        pathToModule = getConfigPath(user)
        if not os.path.exists(pathToModule):
            # Create a default (blank) config file.
            outHandle = open(pathToModule, 'w')
            outHandle.write("config = {}\n")
            outHandle.close()

        try:
            modulename = user + CONFIG_SUFFIX
            module = __import__(modulename, globals(), locals(), ['config'])
            config[user] = module.config
        except Exception, e:
            logger.log.error("Failed to load configuration file %s: %s", modulename, e)            


## Serialize the current config state for the specified user
# to the appropriate config file.
def writeConfig(user):
    outFile = open(getConfigPath(user), 'w')
    # Do this one key-value pair at a time, to reduce the likelihood
    # that the printer will fail to print something really big.
    outFile.write("config = {\n")
    for key, value in config[user].iteritems():
        outFile.write(" %s: %s,\n" % (printer.pformat(key), printer.pformat(value)))
    outFile.write("}\n")
    outFile.close()


## Generate the path to the specified user's config file
def getConfigPath(user):
    return os.path.join(CONFIG_ROOT_PATH, user + CONFIG_SUFFIX + ".py")


## Retrieve the config value referenced by key. If isGlobal is true, look 
# under the global config entry; otherwise look under the entry for 
# the current user. If key is not found, default is inserted and returned.
# If the value changed as a result of the lookup (because we wrote the
# default value to config), then write config back to the file.
def getValue(key, isGlobal = False, default = None):
    global config, didChange
    didChange = False
    user = getUser(isGlobal)
    if user not in config:
        config[user] = {}
    result = getValueFromConfig(config[user], key, default)
    if didChange:
        writeConfig(user)
    return result


## Second-level, potentially-recursive config getter. Allows clients to
# muck around with deep dicts.
def getValueFromConfig(config, key, default):
    global didChange
    if key not in config:
        didChange = True
        config[key] = default
    if type(default) == type(dict()):
        # Ensure all values in default are in result.
        for name, value in default.iteritems():
            if name not in config[key]:
                didChange = True
                config[key][name] = value
            # Recurse for nested dicts
            if type(value) == type(dict()):
                getValueFromConfig(config[key], name, value)
    return config[key]


## Set the entry referenced by key to the given value. Users are set as
# in getValue.
def setValue(key, value, isGlobal = False):
    global config
    user = getUser(isGlobal)
    if user not in config:
        config[user] = {}
    config[user][key] = value
    writeConfig(user)


## Remove the given key from config
def removeValue(key, isGlobal = False):
    global config
    user = getUser(isGlobal)
    del config[user][key]
    writeConfig(user)


## Simple chooser to reduce code duplication.
def getUser(isGlobal):
    if isGlobal:
        return GLOBAL_USERNAME

    curName = util.user.getUsername()
    if curName is not None:
        return curName
    # Nobody logged in yet; have to use global controls
    logger.log.warn("Trying to use non-global config when no user is logged in")
    logger.log.warn("%s", traceback.format_list(traceback.extract_stack()))
    return GLOBAL_USERNAME


def initialize():
    loadConfig()
