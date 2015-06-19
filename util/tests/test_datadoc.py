import unittest
import mock
import util.datadoc

class TestDataDoc(unittest.TestCase):

    def setUp(self):
        with mock.patch('util.datadoc.DataDoc'):
            self.datadoc = util.datadoc.DataDoc()

    def test___init__(self):
        # data_doc = DataDoc(filename)
        assert False # TODO: implement your test here

    def test_alignAndCrop(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.alignAndCrop(wavelengths, timepoints, savePath))
        assert False # TODO: implement your test here

    def test_convertFromMicrons(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.convertFromMicrons(offsets))
        assert False # TODO: implement your test here

    def test_convertToMicrons(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.convertToMicrons(offsets))
        assert False # TODO: implement your test here

    def test_getAlignParams(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.getAlignParams(wavelength))
        assert False # TODO: implement your test here

    def test_getImageArray(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.getImageArray())
        assert False # TODO: implement your test here

    def test_getSliceCoords(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.getSliceCoords(axes))
        assert False # TODO: implement your test here

    def test_getSliceSize(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.getSliceSize(axis1, axis2))
        assert False # TODO: implement your test here

    def test_getTransformationMatrices(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.getTransformationMatrices())
        assert False # TODO: implement your test here

    def test_getValuesAt(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.getValuesAt(coord))
        assert False # TODO: implement your test here

    def test_hasTransformation(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.hasTransformation())
        assert False # TODO: implement your test here

    def test_hasZMotion(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.hasZMotion())
        assert False # TODO: implement your test here

    def test_mapCoords(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.mapCoords(data, targetCoords, targetShape, axes, order))
        assert False # TODO: implement your test here

    def test_moveCropbox(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.moveCropbox(offset, isMin))
        assert False # TODO: implement your test here

    def test_moveSliceLines(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.moveSliceLines(offset))
        assert False # TODO: implement your test here

    def test_registerAlignmentCallback(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.registerAlignmentCallback(callback))
        assert False # TODO: implement your test here

    def test_saveTo(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.saveTo(savePath))
        assert False # TODO: implement your test here

    def test_setAlignParams(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.setAlignParams(wavelength, params))
        assert False # TODO: implement your test here

    def test_takeDefaultSlice(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.takeDefaultSlice(perpendicularAxes, shouldTransform))
        assert False # TODO: implement your test here

    def test_takeProjectedSlice(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.takeProjectedSlice(axes, projectionAxis, shouldTransform, order))
        assert False # TODO: implement your test here

    def test_takeSlice(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.takeSlice(axes, shouldTransform, order))
        assert False # TODO: implement your test here

    def test_takeSliceFromData(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.takeSliceFromData(data, axes, shouldTransform, order))
        assert False # TODO: implement your test here

    def test_transformArray(self):
        # data_doc = DataDoc(filename)
        # self.assertEqual(expected, data_doc.transformArray(data, dx, dy, dz, angle, zoom, order))
        assert False # TODO: implement your test here

class TestMakeHeaderFor(unittest.TestCase):
    def test_make_header_for(self):
        # self.assertEqual(expected, makeHeaderFor(data, shouldSetMinMax, **kwargs))
        assert False # TODO: implement your test here

class TestMakeHeaderForShape(unittest.TestCase):
    def test_make_header_for_shape(self):
        # self.assertEqual(expected, makeHeaderForShape(shape, dtype, XYSize, ZSize, wavelengths))
        assert False # TODO: implement your test here

class TestWriteMrcHeader(unittest.TestCase):
    def test_write_mrc_header(self):
        # self.assertEqual(expected, writeMrcHeader(header, filehandle))
        assert False # TODO: implement your test here

class TestWriteDataAsMrc(unittest.TestCase):
    def test_write_data_as_mrc(self):
        # self.assertEqual(expected, writeDataAsMrc(data, filename, XYSize, ZSize, wavelengths))
        assert False # TODO: implement your test here

class TestGetExtendedHeader(unittest.TestCase):
    def test_get_extended_header(self):
        # self.assertEqual(expected, getExtendedHeader(data, header))
        assert False # TODO: implement your test here

class TestLoadHeader(unittest.TestCase):
    def test_load_header(self):
        # self.assertEqual(expected, loadHeader(path))
        assert False # TODO: implement your test here

class TestReorderArray(unittest.TestCase):
    def test_reorder_array(self):
        # self.assertEqual(expected, reorderArray(data, size, sequence))
        assert False # TODO: implement your test here

if __name__ == '__main__':
    unittest.main()
