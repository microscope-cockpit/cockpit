import mock
import sys
from contextlib import contextmanager

@contextmanager
def replace_with_mock(namespace, funcname):
    '''Replaces a name in the given namespace with a magic mock object.

    with replace_with_mock(namespace, funcname):
        *do whatever with the mock*

    and the namespace is restored here!
    '''
    func_backup = vars(namespace)[funcname]
    vars(namespace)[funcname] = mock.MagicMock()
    yield vars(namespace)[funcname]
    # and restore afterwards
    vars(namespace)[funcname] = func_backup


@contextmanager
def mock_import(modnames):
    '''adds/replaces a module before it is imported. Useful if the import would
    have side effects or would error. Restores the real module (or lack of)
    afterwards.

    USAGE:
    with mock_import('numpy') as mocknp:
        mocknp.pi = 4
        # code that imports and uses numpy

    Works as when import is called, the module is first looked up in sys.modules
    to avoid reimporting, and so we can slip in ahead of the real import logic.

    if other imports occour that depend upon the mocked objects, they will also
    be affected. import them before the with statment manually to avoid this
    (don't mock builtins)
    '''
    if type(modnames) == str:
        modnames = [modnames]

    module_backup_refs = {}
    mocks = {}
    for modname in modnames:
        if modname in sys.modules:
            module_backup_refs[modname] = sys.modules[modname]
        else:
            module_backup_refs[modname] = None
        sys.modules[modname] = mock.MagicMock()
        mocks[modname] = sys.modules[modname]

    yield mocks

    for modname in modnames:
        if module_backup_refs[modname]:
            sys.modules[modname] = module_backup_refs[modname]
        else:
            del sys.modules[modname]
