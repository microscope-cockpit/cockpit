import unittest
import mock
import imp
from mockManagers import mock_import

import util.importer

imports_to_fake = ['os', 'imp', 'importlib']

class testImporter(unittest.TestCase):

    def testImporterReturnsModules(self):
        with mock_import(imports_to_fake) as mocks:
            imp.reload(util.importer)

            fakeModule = mock.Mock(name='fakeModule')
            mocks['imp'].find_module.return_value = (None, '/path', None)
            mocks['os'].listdir.return_value = ['file1', 'file2.py']
            mocks['os'].path.splitext.return_value = 'moduleName'
            mocks['importlib'].import_module.return_value = fakeModule

            modules = util.importer.getModulesFrom('mydir')

            self.assertEqual(modules[0], fakeModule)


    def testImporterIgnoresForbidden(self):
        with mock_import(imports_to_fake) as mocks:
            imp.reload(util.importer)

            mocks['imp'].find_module.return_value = (None, '/path', None)
            mocks['os'].listdir.return_value = ['module.py']
            mocks['os'].path.splitext.return_value = 'moduleName'

            modules = util.importer.getModulesFrom('mydir',
                                                   forbiddenModules = ['module'])
            self.assertEqual(modules, [])
