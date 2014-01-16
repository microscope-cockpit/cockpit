import util.importer

## Call the initialize() method for each interface module.
def initialize():
    modules = util.importer.getModulesFrom('interfaces', ['__init__.py'])
    for module in modules:
        module.initialize()


## Let the modules make their initial publications.
def makeInitialPublications():
    modules = util.importer.getModulesFrom('interfaces', ['__init__.py'])
    for module in modules:
        module.makeInitialPublications()
