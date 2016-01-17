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




Installation instructions to get stuff working on the Mac -Jan 2016
==

#mega pain in the neck to get ftgl §installed and compiled....

brew install ftgl

#get pyftgl
cd ~/src
wget https://pyftgl.googlecode.com/files/PyFTGL-0.5c.tar.bz2
tar -xjvf PyFTGL-0.5c.tar.bz2
cd pyftgl/

#link the needed headers and library why doesn't brew do this?
cd /usr/local/include/
ln -s ../Cellar/freetype/2.6_1/include/freetype2/ft2build.h ./ft2build.h
mkdir config
cd config/
ln -s ../../Cellar/freetype/2.6_1/include/freetype2/config/ftheader.h ./ftheader.h
cd ..
ln -s ../Cellar/freetype/2.6_1/include/freetype2/freetype.h ./freetype.h
cd config/
ln -s ../../Cellar/freetype/2.6_1/include/freetype2/config/ftconfig.h ./ftconfig.h
ln -s ../../Cellar/freetype/2.6_1/include/freetype2/config/ftoption.h ./ftoption.h
ln -s ../../Cellar/freetype/2.6_1/include/freetype2/config/ftstdlib.h ./ftstdlib.h
cd ..
ln -s ../Cellar/freetype/2.6_1/include/freetype2/fttypes.h ./fttypes.h
ln -s ../Cellar/freetype/2.6_1/include/freetype2/ftsystem.h ./ftsystem.h
ln -s ../Cellar/freetype/2.6_1/include/freetype2/ftimage.h ./ftimage.h
ln -s ../Cellar/freetype/2.6_1/include/freetype2/fterrors.h ./fterrors.h
ln -s ../Cellar/freetype/2.6_1/include/freetype2/ftmoderr.h ./ftmoderr.h
ln -s ../Cellar/freetype/2.6_1/include/freetype2/fterrdef.h ./fterrdef.h
ln -s ../Cellar/freetype/2.6_1/include/freetype2/ftoutln.h ./ftoutln.h
ln -s ../Cellar/freetype/2.6_1/include/freetype2/ftglyph.h ./ftglyph.h

cd /usr/local/lib/
ln -s /opt/X11/lib/libGLU.dylib libGLU.dylib

#back to pyftgl directory.
cd ~/src/pyftgl/
sudo python setup.py install


brew install wx
brew install scipy
brew install numpy
brew install homebrew/x11/freeglut


pip install pyopengl
pip install pyopengl_accelerate
pip install pyserial

#download and install Micks wxPython patch
#download from issue
wget http://trac.wxwidgets.org/raw-attachment/ticket/16767/wxPython-3.0.2.0-plot.patch
cd /usr/local/lib/python2.7/site-packages/wx-3.0-osx_cocoa/wx/lib/
patch < ~/Downloads/wxPython-3.0.2.0-plot.patch

Installation instructions for the Raspberry Pi
==

------------------------------
git clone https://github.com/iandobbie/cockpit.git
sudo aptitude install python-wxtools 
#raspbian pyro install is only version3 we need 4
#raspbian pip install is for python2.6 not 2.7 so we need to get
#pip explicity.
mkdir Downloads
cd Downloads/
wget https://raw.githubusercontent.com/pypa/pip/master/contrib/get-pip.py
#need root to install the python package in system dir
sudo python get-pip.py
sudo pip install Pyro4
sudo aptitude install python-opengl
sudo aptitude install ftgl-dev
#need libboost-python to build PyFTGL
sudo aptitude install libboost-python-dev
#no package for pyFTGL so need to grab source
wget https://pyftgl.googlecode.com/files/PyFTGL-0.5c.tar.bz2
#untar 
tar -xjvf PyFTGL-0.5c.tar.bz2
cd pyftgl/
python setup.py build
sudo python setup.py install

#now fix up a couple of issues.
cd ~/cockpit
# Some python difference we need the core file called cockpit.py
mv cockpit.pyw cockpit.py

#windows USB joystick has some explicit windows dependency.
#disable it completely.
cd devices
mv windowsUSBJoystick.py windowsUSBJoystick.py-disabled
cd ..

python cockpit.py
