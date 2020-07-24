#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
##
## Latest version available at
##     https://github.com/mickp/csv_plotter
##     git@github.com:mickp/csv_plotter.git
##
## This file implements a CSV data plotter using wxPython.
##
## This file is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This file is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this file.  If not, see <http://www.gnu.org/licenses/>.

import csv
import glob
import matplotlib
import numpy as np
import os
import wx

matplotlib.use('WXAgg')
import matplotlib.dates
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavigationToolbar
from matplotlib import colors
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

DEBUG = False

# We use images of size BMP_SIZE in the tree to act as a legend.
BMP_SIZE = (16, 16)
# A mapping of matplotlib colour to a base image index.
C_TO_I = {}
for i, hex in enumerate(plt.rcParams["axes.prop_cycle"].by_key()["color"]):
    C_TO_I[hex.lower()] = i+1

def make_bitmap(hex, text=None):
    """Return a square bitmap for use in TreeCtrl imagelist."""
    rgb = [int(flt*255) for flt in colors.to_rgb(hex)]
    bmp = wx.Bitmap.FromRGBA(*BMP_SIZE, red=rgb[0], green=rgb[1], blue=rgb[2],
                             alpha=wx.ALPHA_OPAQUE)
    if text is not None:
        dc = wx.MemoryDC()
        dc.SelectObject(bmp)
        w, h = dc.GetTextExtent(text)
        dc.DrawText(text, (BMP_SIZE[0] - w) / 2,  (BMP_SIZE[1] - h) / 2)
        dc.SelectObject(wx.NullBitmap)
    return bmp


class DataSource:
    def __init__(self, path, node):
        """A wrapper around CSV-formatted data in a file."""
        self.path = os.path.abspath(path)
        self.label = os.path.basename(path).rstrip(".log")
        self._xdata = None
        self._ydata = None
        self._fh = None
        self._dialect = None
        self._headers = None
        self.has_headers = None
        self.trace = None
        self.node = node


    def set_trace(self, trace):
        self.trace = trace


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
                    self._headers = [h.strip() for h in row]
                    self.has_headers = True
                else:
                    self._headers = ['col' + str(i) for i in range(len(row) - 1)]
                    self.has_headers = False
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
        """Read complete data from source file.

        Returns number of rows read."""
        if self._fh is not None and not self._fh.closed:
            self._fh.close()
        headers = self.get_headers()
        skiprows = [0,1][self.has_headers]
        delimiter = self._dialect.delimiter
        cols = range(1,len(self._headers))
        converters = {col: lambda val: float(val.strip() or 'nan') for col in cols}
        try:
            self._xdata = np.loadtxt(self.path, dtype='datetime64', usecols=0,
                                     delimiter=delimiter, skiprows=skiprows, unpack=True)
            self._ydata = np.loadtxt(self.path, usecols=cols, converters=converters,
                                     delimiter=delimiter, skiprows=skiprows, unpack=True)
        except:
            self._xdata = None
            self._ydata = None
            return 0
        if self._ydata.ndim == 1:
            self._ydata = self._ydata.reshape((1, -1))
        if self._xdata.size and self._ydata.size:
            self._fh = open(self.path)
            self._fh.seek(0, os.SEEK_END)
        return len(self._ydata)


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


class CSVPlotter(wx.Frame):
    """This class implements CSVPlotter.

    The window displays a tree of source files and the columns available in those
    files, and a matplotlib plot with a single horizontal axis, and a pair of vertical axes.

    Items selected in the tree are displayed on the plot.
    Right-clicking on an item in the tree shows a context menu that allows a trace to be moved
    between the left and right vertical axes.
    The tree also serves as a plot legend, showing the colour of the trace for plotted data, and
    the letter 'L' or 'R' to indicate whether the trace is on the _L_eft or _R_ight axis.
    """
    def __init__(self, *args, **kwargs):
        """CSVPlotter instance"""
        kwargs['title'] = "value log viewer"
        super().__init__(*args, **kwargs)
        self.fn_to_src = {}
        self.item_to_trace = {}
        self.trace_to_item = {}
        self.trace_to_data = {}
        self.node_to_colour = {}
        self.node_to_axis = {}
        self.empty_root_nodes = []
        self._watch_timer = wx.Timer(self)

        self._makeUI()
        self.Bind(wx.EVT_TIMER, self.update_data, self._watch_timer)
        self._watch_timer.Start(1000)
        self.Bind(wx.EVT_CLOSE, self._on_close)


    def _on_close(self, evt):
        """On close, unbind an event to prevent access to deleted C/C++ objects."""
        style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        with wx.MessageDialog(self, "Exit?", style=style) as md:
            if md.ShowModal() == wx.ID_NO:
                return
        self.tree.Unbind(wx.EVT_TREE_SEL_CHANGED)
        evt.Skip()


    def _on_remove_all(self, evt):
        """Remove all items from the tree."""
        style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        with wx.MessageDialog(self, "Remove all data sources?", style=style) as md:
            if md.ShowModal() == wx.ID_NO:
                return
        for line in self.axis.lines + self.axis_r.lines:
            line.remove()
        self.fn_to_src.clear()
        self.trace_to_data.clear()
        self.trace_to_item.clear()
        self.item_to_trace.clear()
        self.tree.DeleteAllItems()


    def _on_select_file(self, evt):
        """Display a dialog to allow selection of a data source file."""
        style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE |wx.FD_CHANGE_DIR
        with wx.FileDialog(self, "Open files", style=style) as fd:
            if fd.ShowModal() == wx.ID_CANCEL:
                return
            self.add_data_sources(fd.Paths, defer_open=len(fd.Paths) > 2)


    def _on_select_folder(self, evt):
        """Display a dialog to allow selection of a folder of data sources."""
        style = wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR
        with wx.DirDialog(self, "Open folder", style=style) as fd:
            if fd.ShowModal() == wx.ID_CANCEL:
                return
            files = glob.glob(fd.Path + '/*')
            self.add_data_sources(files, defer_open=len(files) > 2)


    def _makeUI(self):
        """Make the window and all widgets"""
        min_plot_w = min_plot_h = 400
        min_tree_w = 160

        menubar = wx.MenuBar()
        menu = wx.Menu()
        self.SetMenuBar(menubar)
        self.Bind(wx.EVT_MENU, self._on_select_file,
                  menu.Append(wx.ID_FILE, 'Open &file(s)', 'Open a file'))
        self.Bind(wx.EVT_MENU, self._on_select_folder,
                  menu.Append(wx.ID_OPEN, 'Open fol&der', 'Open a folder'))
        menu.AppendSeparator()
        self.Bind(wx.EVT_MENU, lambda evt: self.Close(),
                  menu.Append(wx.ID_EXIT, '&Quit', 'Quit application'))
        menubar.Append(menu, '&File')


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
        iml = wx.ImageList(*BMP_SIZE, mask=False, initialCount=0)
        iml.Add(wx.Bitmap.FromRGBA(BMP_SIZE[0], BMP_SIZE[1], *self.tree.GetBackgroundColour() ))
        for hex in sorted(C_TO_I, key=C_TO_I.get):
            iml.Add(make_bitmap(hex, 'L'))
            iml.Add(make_bitmap(hex, 'R'))
        self.tree.AssignImageList(iml)

        self.Fit()


    def set_node_image(self, node):
        """Set the image for a node to act as legend for the plot.

         The imageshows the colour of the trace, and also indicates which Y-axis
         the trace is plotted against. either 'L'eft or 'R'ight.
        """
        trace = self.item_to_trace.get(node)
        if trace is None:
            index = 0
        else:
            # Image index: first term selects colour, second term selects L or R variant.
            index = 2 * C_TO_I[trace.get_c()] - (trace.axes == self.axis)
        self.tree.SetItemImage(node, index)


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

        for node in self.empty_root_nodes:
            # Check for new data for nodes which had insufficient data before.
            src = self.tree.GetItemData(node)
            if src.read_data() > 2:
                # There is new data. Update appearance of this and child nodes.
                self.empty_root_nodes.remove(node)
                self.tree.SetItemTextColour(node, wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOXTEXT))
                child = self.tree.GetFirstChild(node)[0]
                while wx.TreeItemId.IsOk(child):
                    self.tree.SetItemTextColour(child, wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOXTEXT))
                    child = self.tree.GetNextSibling(child)
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

        menu = wx.Menu()
        if self.tree.GetItemParent(node) == self.tree.RootItem:
            remove = menu.Append(wx.ID_REMOVE, 'remove')
            self.Bind(wx.EVT_MENU, lambda evt, node=node: self.del_data_source(node), remove)
        else:
            swap = menu.Append(wx.ID_ANY, 'swap y-axis')
            self.Bind(wx.EVT_MENU, lambda evt, node=node: self.swap_axis(node), swap)
            menu.AppendSeparator()
        remove_all = menu.Append(wx.ID_CLEAR, 'remove all')
        self.Bind(wx.EVT_MENU, self._on_remove_all, remove_all)
        self.PopupMenu(menu)


    def swap_axis(self, node):
        """Move a trace from one vertical axis to the other."""
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
        self.node_to_axis[node] = new_axis
        self.set_node_image(node)


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
                self.set_node_image(node)
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
            if xlen < 2:
                empty_nodes.update([node, self.tree.GetItemParent(node)])
                continue
            if src.ydata is None or all(np.isnan(src.ydata[col_num])):
                empty_nodes.update([node])
                continue
            try:
                label = src.label + ": " + headers[col_num+1]
                # Plot a trace, recalling the colour and axis used previously,
                # or storing defaults if this node has not been plotted before.
                axis = self.node_to_axis.get(node, self.axis)
                trace = axis.plot(src.xdata, src.ydata[col_num])[0]
                if node in self.node_to_colour:
                    trace.set_c(self.node_to_colour[node])
                else:
                    self.node_to_colour[node] = trace.get_c()
            except:
                error_nodes.update([node, self.tree.GetItemParent(node)])
                continue
            self.tree.SetItemTextColour(node, wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOXTEXT))
            self.item_to_trace[node] = trace
            self.trace_to_item[trace] = node
            self.trace_to_data[trace] = (src, col_num)
            self.set_node_image(node)

        for node in empty_nodes:
            self.tree.SetItemTextColour(node, 'grey')
            self.tree.SetItemImage(node, 0)
            self.tree.SelectItem(node, False)
            # Store empty top-level nodes to poll for new data.
            if f_top(node):
                self.empty_root_nodes.append(node)
        for node in error_nodes:
            self.tree.SetItemTextColour(node, 'red')
            self.tree.SetItemImage(node, 0)
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


    def del_data_source(self, node):
        """Delete a data source by its node id."""
        self.tree.SetEvtHandlerEnabled(False)
        parent = self.tree.GetItemParent(node)
        if  parent != self.tree.RootItem:
            node = parent

        src = self.tree.GetItemData(node)
        self.fn_to_src.pop(src.path, None)

        child = self.tree.GetFirstChild(node)[0]
        while wx.TreeItemId.IsOk(child):
            trace = self.item_to_trace.pop(child, None)
            if trace is not None:
                trace.remove()
                self.trace_to_data.pop(trace, None)
            self.tree.Delete(child)
            child = self.tree.GetFirstChild(node)[0]
        self.tree.Delete(node)
        del src
        self.tree.SetEvtHandlerEnabled(True)


    def add_data_sources(self, filenames, defer_open=False):
        """Set data sources and populate tree."""
        root = self.tree.GetRootItem() or self.tree.AddRoot('Files')
        for fn in filenames:
            if os.path.abspath(fn) not in self.fn_to_src:
                node = self.tree.AppendItem(root, 'empty')
                try:
                    src = DataSource(fn, node)
                except Exception as e:
                    sys.stderr.write("Could not open %s.\n%s" % (fn, e))
                    self.tree.Delete(node)
                    continue
                self.tree.SetItemText(src.node, src.label)
                self.tree.SetItemData(src.node, src)
                self.fn_to_src[src.path] = src
            else:
                src = self.fn_to_src[fn]
            if not defer_open:
                self.tree.SelectItem(src.node)


if __name__ == "__main__":
    import sys
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
    window = CSVPlotter(None)
    window.add_data_sources(filenames, defer_open=True)
    window.Show()
    if DEBUG:
        it = InspectionTool()
        it.Show()
    app.MainLoop()
