import imageSequenceViewer
import util.datadoc



## This viewer loads a file and shows the images in it. 
class FileViewer(imageSequenceViewer.ImageSequenceViewer):
    def __init__(self, filename, *args, **kwargs):
        doc = util.datadoc.DataDoc(filename)
        images = doc.imageArray

        imageSequenceViewer.ImageSequenceViewer.__init__(self,
                images, "Viewer for %s" % filename, *args, **kwargs)

