#!/usr/bin/env python
import csv
import matplotlib
import numpy as np
import os
#import re
import wx

matplotlib.use('WXAgg')
import matplotlib.dates
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib import colors
from matplotlib import pyplot as plt
from matplotlib.figure import Figure


DEBUG = True
BMP_SIZE = (16, 16)
C_TO_I = {}
for i, hex in enumerate(plt.rcParams["axes.prop_cycle"].by_key()["color"]):
    C_TO_I[hex.lower()] = i+1


def make_bitmap(hex):
    """Return a square bitmap for use in TreeCtrl imagelist."""
    rgb = [int(flt*255) for flt in colors.to_rgb(hex)]
    return wx.Bitmap.FromRGBA(*BMP_SIZE, red=rgb[0], green=rgb[1], blue=rgb[2],
                              alpha=wx.ALPHA_OPAQUE)


class DataFile:
    def __init__(self, path):
        """A wrapper around CSV-formatted data in a file."""
        self.path = os.path.abspath(path)
        #self.label = re.sub(r"_?([0-9]{4}|[0-9]{2})[-_]?[0-9]+[_-}-?[0-9]+(\.log)?",
        #                    "", os.path.basename(path))
        self.label = os.path.basename(path).rstrip(".log")
        self._xdata = None
        self._ydata = None
        self._fh = None
        self._dialect = None
        self._headers = None


    def get_headers(self):
        """Determine source file dialect and parse headers."""
        if self._headers is None:
            # Dialect determination fails on Windows if we read past EOF, so set a limit.
            f_len = os.path.getsize(self.path)
            with open(self.path) as fh:
                head = fh.read(min(4096, f_len))
                self._dialect = csv.Sniffer().sniff(head)()
                has_header = csv.Sniffer().has_header(head)
                fh.seek(0)
                reader = csv.reader(fh, self._dialect)
                row = reader.__next__()
                if has_header:
                    self._headers = row
                else:
                    self._headers = ['col' + str(i) for i in range(len(row) - 1)]
        return self._headers


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
        """Read complete data from source file."""
        if self._fh is not None and not self._fh.closed:
            self._fh.close()
        headers = self.get_headers()
        skiprows = [0,1][headers is not None]
        delimiter = self._dialect.delimiter
        cols = range(1,len(self._headers))
        self._xdata = np.loadtxt(self.path, dtype='datetime64', usecols=0,
                                delimiter=delimiter, skiprows=skiprows).T
        self._ydata = np.loadtxt(self.path, usecols=cols,
                                delimiter=delimiter, skiprows=skiprows).T
        if self._xdata.size and self._ydata.size:
            self._fh = open(self.path)
            self._fh.seek(0, os.SEEK_END)


    def fetch_new_data(self):
        """Fetch new data from an open file."""
        if self._fh is None:
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
        """ValueLogViewer instance"""
        kwargs['title'] = "value log viewer"
        super(ValueLogViewer, self).__init__(*args, **kwargs)
        self.sources = []
        self.item_to_trace = {}
        self.trace_to_item = {}
        self.trace_to_data = {}
        self._watch_timer = wx.Timer(self)

        self._makeUI()
        self.Bind(wx.EVT_TIMER, self.update_data, self._watch_timer)
        self._watch_timer.Start(1000)
        self.Bind(wx.EVT_CLOSE, self._on_close)


    def _on_close(self, evt):
        """On close, unbind an event to prevent access to deleted C/C++ objects."""
        self.tree.Unbind(wx.EVT_TREE_SEL_CHANGED)
        evt.Skip()


    def _makeUI(self):
        """Make the window and all widgets"""
        min_plot_w = min_plot_h = 400
        min_tree_w = 160

        self.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE,
                                     size=(min_plot_w+400, min_plot_h) )
        splitter.SetMinimumPaneSize(1)
        splitter.SetSashGravity(0.0)
        figure = Figure()
        self.axis = figure.add_axes((0.1,0.1,.8,.8))
        self.axis.xaxis_date()
        self.axis.xaxis.set_major_formatter(
                matplotlib.dates.DateFormatter('%H:%M'))
        self.axis.xaxis.set_major_locator(
                matplotlib.ticker.LinearLocator() )
        self.axis_r = self.axis.twinx()

        # Need to put navbar in same panel as the canvas - putting it
        # in an outer layer means it may not be drawn correctly or at all.
        fig_panel = wx.Panel(splitter, size=(min_plot_w, min_plot_h))
        fig_panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.canvas = FigureCanvas(fig_panel, -1, figure)
        nav_bar = NavigationToolbar(self.canvas)
        fig_panel.Sizer.Add(self.canvas, -1, wx.EXPAND)
        fig_panel.Sizer.Add(nav_bar, 0, wx.LEFT)

        self.tree = wx.TreeCtrl(splitter, -1, wx.DefaultPosition, size=(min_tree_w, -1),
                                style=wx.TR_MULTIPLE | wx.TR_HAS_BUTTONS |
                                      wx.TR_LINES_AT_ROOT | wx.TR_HIDE_ROOT)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_tree_sel_changed)
        self.tree.Bind(wx.EVT_CONTEXT_MENU, self.on_tree_right_click)

        splitter.SplitVertically(self.tree, fig_panel)
        splitter.SashPosition = min_tree_w

        self.Sizer.Add(splitter, 1, flag=wx.EXPAND)

        # Create am imagelist so the tree also acts as a legend.
        # The 0th element is a bitmap with the tree's background colour.
        iml = wx.ImageList(*BMP_SIZE, False, 0)
        iml.Add(wx.Bitmap.FromRGBA(*BMP_SIZE, *self.tree.GetBackgroundColour() ))
        for hex in sorted(C_TO_I, key=C_TO_I.get):
            iml.Add(make_bitmap(hex))
        self.tree.AssignImageList(iml)

        self.Fit()


    def update_data(self, evt):
        """Update a data source with new points"""
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


    def on_tree_right_click(self, evt):
        """On right click in tree, move node's trace to the other y-axis."""
        pos = self.ScreenToClient(evt.GetPosition())
        node, flags = self.tree.HitTest(pos)
        if not node.IsOk():
            return

        if not any([flags & test for test in [ wx.TREE_HITTEST_ONITEM,
                                               wx.TREE_HITTEST_ONITEMBUTTON,
                                               wx.TREE_HITTEST_ONITEMICON,
                                               wx.TREE_HITTEST_ONITEMLABEL] ]):
            return

        trace = self.item_to_trace.get(node)
        if trace is None:
            return

        src, col_num = self.trace_to_data[trace]
        colour = trace.properties().get('color')
        new_axis = [self.axis, self.axis_r][trace.axes == self.axis]
        new_trace = new_axis.plot(src.xdata, src.ydata[col_num],
                                  color=colour)[0]
        trace.remove()
        self.trace_to_item.pop(trace, None)
        self.trace_to_data.pop(trace, None)
        self.item_to_trace[node] = new_trace
        self.trace_to_item[new_trace] = node
        self.trace_to_data[new_trace] = (src, col_num)


    def on_tree_sel_changed(self, evt):
        """Read data for selected items and add to plot."""
        self.tree.SetEvtHandlerEnabled(False) # Prevent re-entrance.
        busy_cursor = wx.BusyCursor()

        # Filters for GetSelections.
        f_top = lambda o: self.tree.GetItemParent(o) == self.tree.RootItem
        f_not_top = lambda o : not(f_top(o))

        # Nodes to mark later
        error_nodes = set() # Nodes with data errors
        empty_nodes = set() # Nodes with insufficient data

        for node in filter(f_top, self.tree.GetSelections() ):
            # Add child nodes if this is first access.
            if not self.tree.ItemHasChildren(node):
                src = self.tree.GetItemData(node)
                try:
                    headers = src.get_headers()
                except:
                    error_nodes.add(node)
                    continue
                if len(headers) < 2:
                    empty_nodes.add(node)
                # First col contains x-axis data, so skip
                for colnum, ch in enumerate(headers[1:]):
                    self.tree.AppendItem(node, ch, data=(src, colnum))
            # Select any children of selected items
            child = self.tree.GetFirstChild(node)[0]
            while wx.TreeItemId.IsOk(child):
                self.tree.SelectItem(child)
                child = self.tree.GetNextSibling(child)
            self.tree.SetItemTextColour(node, wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOXTEXT))
            self.tree.Expand(node)

        selected = set( filter(f_not_top, self.tree.GetSelections() ))
        # Remove de-selected traces.
        for (node, tr) in self.item_to_trace.items():
            if tr is not None and node not in selected:
                tr.remove()
                self.item_to_trace[node] = None
                self.trace_to_data.pop(tr, None)
                self.tree.SetItemImage(node, 0)
        # Add new traces.
        for node in selected:
            trace = self.item_to_trace.get(node)
            if trace is not None: # Skip items already on the plot.
                continue
            src, col_num = self.tree.GetItemData(node)
            try:
                headers = src.get_headers()
                xlen = src.xdata.size
            except:
                error_nodes.update([node, self.tree.GetItemParent(node)])
                continue
            if xlen <= 2:
                empty_nodes.update([node, self.tree.GetItemParent(node)])
                continue
            try:
                label = src.label + ": " + headers[col_num+1]
                trace = self.axis.plot(src.xdata, src.ydata[col_num])[0]
            except:
                error_nodes.update([node, self.tree.GetItemParent(node)])
                continue
            self.tree.SetItemTextColour(node, wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOXTEXT))
            self.tree.SetItemImage(node, C_TO_I[trace.get_c()])
            self.item_to_trace[node] = trace
            self.trace_to_item[trace] = node
            self.trace_to_data[trace] = (src, col_num)

        for node in empty_nodes:
            self.tree.SetItemTextColour(node, 'grey')
            self.tree.SelectItem(node, False)
        for node in error_nodes:
            self.tree.SetItemTextColour(node, 'red')
            self.tree.SelectItem(node, False)

        del busy_cursor
        self.tree.SetEvtHandlerEnabled(True)
        self.redraw()


    def redraw(self):
        """Redraw the plot."""
        if any(self.item_to_trace.values()):
            # Don't try to rescale if no data - will cause datetime formatter error.
            for ax in [self.axis, self.axis_r]:
                ax.relim()
                ax.autoscale_view()
        self.canvas.draw()


    def set_data_sources(self, filenames):
        """Set data sources and populate tree."""
        self.sources = []
        for fn in filenames:
            try:
                self.sources.append(DataFile(fn))
            except Exception as e:
                sys.stderr.write("Could not open %s.\n%s" % (fn, e))
        root = self.tree.AddRoot('Files')
        for src in self.sources:
            node = self.tree.AppendItem(root, src.name, data=src)


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

    from wx.lib.inspection import InspectionTool

    app = wx.App(False)
    window = ValueLogViewer(None)
    window.set_data_sources(filenames)
    window.Show()
    if DEBUG:
        it = InspectionTool()
        it.Show()
    app.MainLoop()