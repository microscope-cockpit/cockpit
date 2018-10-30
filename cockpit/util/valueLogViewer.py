#!/usr/bin/env python
import csv
import matplotlib
import numpy as np
import os
#import re
import sys
import wx

import matplotlib.dates
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure
matplotlib.use('WXAgg')

DEBUG = False


class DataFile:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        #self.label = re.sub(r"_?([0-9]{4}|[0-9]{2})[-_]?[0-9]+[_-}-?[0-9]+(\.log)?",
        #                    "", os.path.basename(path))
        self.label = os.path.basename(path).rstrip(".log")
        self._xdata = None
        self._ydata = None
        self._fh = None # Open file handled; opened by read_data.
        # Dialect determination fails on Windows if we read past EOF, so set a limit.
        f_len = os.path.getsize(path)
        with open(path) as fh:
            head = fh.read(min(4096, f_len))
            self._dialect = csv.Sniffer().sniff(head)()
            self._has_header = csv.Sniffer().has_header(head)
            fh.seek(0)
            reader = csv.reader(fh, self._dialect)
            row = reader.__next__()
            if self._has_header:
                self.headers = row
            else:
                self.headers = ['col'+str(i) for i in range(len(row)-1)]


    def __del__(self):
        if self._fh is not None and not self._fh.closed:
            self._fh.close()


    def close(self):
        self._fh.close()
        self._xdata = None
        self._ydata = None


    @property
    def name(self):
        return os.path.basename(self.path)


    @property
    def xdata(self):
        if self._xdata is None:
            self.read_data()
        return self._xdata


    @property
    def ydata(self):
        if self._ydata is None:
            self.read_data()
        return self._ydata


    def read_data(self):
        if self._fh is not None and not self._fh.closed:
            self._fh.close()
        skiprows = [0,1][self._has_header]
        delimiter = self._dialect.delimiter
        cols = range(1,len(self.headers))
        self._xdata = np.loadtxt(self.path, dtype='datetime64', usecols=0,
                                delimiter=delimiter, skiprows=skiprows).T
        self._ydata = np.loadtxt(self.path, usecols=cols,
                                delimiter=delimiter, skiprows=skiprows).T
        if self._xdata.size and self._ydata.size:
            self._fh = open(self.path)
            self._fh.seek(0, os.SEEK_END)


    def fetch_new_data(self):
        if self._fh is None:
            # file not opened yet
            return 0
        rows_added = 0
        while True:
            row = self._fh.readline().strip()
            if not row:
                break
            row = row.split(';')
            t = np.datetime64(row[0])
            vals = np.array([row[1:]], dtype='float')
            self._xdata = np.append(self._xdata, t)
            self._ydata = np.append(self._ydata, vals.T, axis=1)
            rows_added += 1
        return rows_added


class ValueLogViewer(wx.Frame):
    def __init__(self, *args, **kwargs):
        kwargs['title'] = "value log viewer"
        super(ValueLogViewer, self).__init__(*args, **kwargs)
        self.sources = []
        self.item_to_trace = {}
        self.trace_to_item = {}
        self.trace_to_data = {}
        self._makeUI()
        self._watch_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_data, self._watch_timer)
        self._watch_timer.Start(1000)


    def _makeUI(self):
        splitter = wx.SplitterWindow(self, -1, style=wx.SP_LIVE_UPDATE)
        splitter.SetMinimumPaneSize(96)
        splitter.SetSashGravity(0.0)
        
        figure = Figure()
        self.axis = figure.add_axes((0.1,0.1,.8,.8))
        self.axis.xaxis_date()
        self.axis.xaxis.set_major_formatter(
                matplotlib.dates.DateFormatter('%H:%M'))
        self.axis.xaxis.set_major_locator(
                matplotlib.ticker.LinearLocator() )
        self.canvas = FigureCanvas(splitter, -1, figure)
        wx.BoxSizer(wx.HORIZONTAL).Add(self.canvas, flag=wx.EXPAND, proportion=True)
        
        self.tree = wx.TreeCtrl(splitter, -1, wx.DefaultPosition, wx.Size(160,100),
                                style=wx.TR_MULTIPLE | wx.TR_HAS_BUTTONS | wx.EXPAND |
                                      wx.TR_LINES_AT_ROOT | wx.TR_HIDE_ROOT)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_tree_sel_changed)
        wx.BoxSizer(wx.HORIZONTAL).Add(self.tree, flag=wx.EXPAND, proportion=True)

        splitter.SplitVertically(self.tree, self.canvas)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, flag=wx.EXPAND, proportion=True)
        self.Sizer = sizer
        self.Fit()


    def update_data(self, evt):
        current_sources = set([d[0] for d in self.trace_to_data.values()])

        for s in current_sources:
            new_lines = s.fetch_new_data()
            if new_lines == 0:
                continue
            for t, (src, col_num) in self.trace_to_data.items():
                if s != src:
                    continue
                t.set_data(src.xdata, src.ydata[col_num])
        self.redraw()


    def on_tree_sel_changed(self, evt):
        # Select any children of selected items
        for it in self.tree.GetSelections():
            if self.tree.ItemHasChildren(it):
                ch = self.tree.GetFirstChild(it)[0]
                while wx.TreeItemId.IsOk(ch):
                    self.tree.SelectItem(ch)
                    ch = self.tree.GetNextSibling(ch)
        # Update the plot - must iterate over updated selection.
        selected = self.tree.GetSelections()
        # Remove de-selected traces.
        for (it, tr) in self.item_to_trace.items():
            if tr is not None and it not in selected:
                tr.remove()
                self.item_to_trace[it] = None
                self.trace_to_data.pop(tr, None)
        # Add new traces.
        for it in self.tree.GetSelections():
            if self.tree.ItemHasChildren(it):
                # Skip anything that isn't a channel of data.
                continue
            trace = self.item_to_trace.get(it)
            if trace is not None:
                # Skip traces that have already been plotted.
                continue
            src, col_num = self.tree.GetItemData(it)
            if src.xdata.size and src.ydata.size:
                label = src.label + ": " + src.headers[col_num+1]
                trace = self.axis.plot(src.xdata, src.ydata[col_num],
                                       label=label)[0]
            self.item_to_trace[it] = trace
            self.trace_to_item[trace] = it
            self.trace_to_data[trace] = (src, col_num)
        # Rescale axes and update the canvas.
        self.redraw()


    def redraw(self):
        if any(self.item_to_trace.values()):
            # Don't try to rescale if no data - will cause datetime formatter error.
            self.axis.relim()
            self.axis.autoscale_view()
            self.axis.legend()
        self.canvas.draw()


    def set_data_sources(self, filenames):
        wpaths = set()
        self.sources = []
        for fn in filenames:
            try:
                self.sources.append(DataFile(fn))
            except Exception as e:
                sys.stderr.write("Could not open %s.\n%s" % (fn, e))
        # Add all files and their channels to the tree
        root = self.tree.AddRoot('Files')
        for src in self.sources:
            node = self.tree.AppendItem(root, src.name, data=None)
            # First col contains x-axis data, so skip
            for colnum, ch in enumerate(src.headers[1:]):
                self.tree.AppendItem(node, ch, data=(src, colnum))


if __name__ == "__main__":
    import sys
    import glob
    if len(sys.argv) <= 1:
        filenames = glob.glob("*.log")
    else:
        filenames = []
        for arg in sys.argv[1:]:
            if os.path.isdir(arg):
                filenames.extend(glob.glob(os.path.join(arg, "*.log")))
            else:
                filenames.append(arg)
    [print(f) for f in filenames]

    from wx.lib.inspection import InspectionTool

    app = wx.App(False)
    window = ValueLogViewer(None)
    window.set_data_sources(filenames)
    window.Show()
    if DEBUG:
        it = InspectionTool()
        it.Show()
    app.MainLoop()