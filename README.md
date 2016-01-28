cockpit
=======


Installation
============
* You will need python with a matching FTGL binary, Pyro4, numpy and wx.
* For Windows, WinPython-64 has been seen to work well.
* wxPython 3.0.2 breaks wx/lib/plot.py. To fix, apply this patch to (pythonpath)/Lib/site-packages/wx-3.0-msw/wx/lib/plot.py:
 * http://trac.wxwidgets.org/raw-attachment/ticket/16767/wxPython-3.0.2.0-plot.patch



More detail instructions on Windows install Jan 2016
-------------------------------------------------

1. Install winpython version 2.7 (current version is
WinPython-64bit-2.7.10.3). I installed it into c:\

2.  Edit the path to include the python directory and the python/scripts
dir. right click on my computer, select propeties:Advanced and click
on the Enviroment variables as the bottom right hand corener. Select
new, PATH and set it to
%PATH%;C:\WinPython-64bit-2.7.10.3\python-2.7.10.amd64;C:\WinPython-64bit-2.7.10.3\python-2.7.10.amd64\Scripts
Assuming the directories defined above.


3. Grab pyFTGL from micronadmin:/cockpitdependencies
copy the libaries in the build directory into
C:\WinPython-64bit-2.7.10.3\python-2.7.10.amd64\Lib


4. Install wx python (current version wxPython3.0-win64-3.0.2.0-py27)
compiling etc fails for me as it seesm to think python chould be in
c:\python27\python (although this my be a reminant for installing
vannila python27 on thsi machine perviously)

5. Install Pryo4 with
> pip install Pryo4.

6. Install gitbash so you have git and a useful command line  enviroment.

7. Patch the wx-3 plot bug. Patch in
> micronadmin:\cockpitdepencies\wxPython-3.0.2.0-plot.patch
Wx got installed in a bit of a strnage place so I had to do in a gitbash shell: 

> cd /c/WinPython-64bit-2.7.10.3/python-2.7.10.amd64/Lib/site-packages/wx-3.0-msw
> patch -p2 < /c/Users/bioc0882/Desktop/wxPython-3.0.2.0-plot.patch

8. Then install cockpit itself from github
open gitbash
> cd /c
> git clone https://github.com/MicronOxford/cockpit.git

9. finally run cockpit

> cd /c/cockpit
> python cockpit.pyw
