cockpit
=======

OMX Cockpit - private repo

Installation
============
* You will need python with a matching FTGL binary, Pyro4, numpy and wx.
* For Windows, WinPython-64 has been seen to work well.
* wxPython 3.0.2 breaks wx/lib/plot.py. To fix, apply this patch to (pythonpath)/Lib/site-packages/wx-3.0-msw/wx/lib/plot.py:
  **http://trac.wxwidgets.org/raw-attachment/ticket/16767/wxPython-3.0.2.0-plot.patch
