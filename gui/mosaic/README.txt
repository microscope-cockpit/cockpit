The Mosaic provides a UI to map out the user's sample in detail. It consists
of a large OpenGL canvas and some associated buttons.

canvas.py: Sets up the OpenGL canvas that image data is drawn to. Has a basic
  level-of-detail system so that the computer doesn't bog down horribly when
  trying to draw thousands of tiles at the same time. 
tile.py: Handles display of a single tile in the canvas. A tile is either a 
  single image from one camera, or a larger array of low-resolution images
  from that camera; the latter is used when zoomed out, as a performance 
  measure.
window.py: Creates the canvas, and sets up the UI for interacting with it, 
  including and especially all of the buttons in the sidebar.
