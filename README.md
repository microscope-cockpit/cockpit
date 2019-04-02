cockpit
=======


Installation
============
* You will need python with a matching FTGL binary, Pyro4, numpy and wx.
* For Windows, WinPython-64 has been seen to work well.


More detail instructions on Windows install Jan 2016
-------------------------------------------------

<<<<<<< HEAD
1. Install python.
=======
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
C:\WinPython-64bit-2.7.10.3\python-2.7.10.amd64\Lib (Note: For Windows10
copy the libaries in the build directory into
C:\WinPython-64bit-2.7.10.3\python-2.7.10.amd64)
>>>>>>> Added Windows10 FTGL documentation fix


2. Ensure the python and python/scripts folders are on the system path. 
https://docs.python.org/3/using/windows.html#excursus-setting-environment-variables


3. Download the FTGL library and put it somewhere on the system path.
https://sourceforge.net/projects/ftgl/


4. Obtain the cockpit source:
```git clone git@github.com:MicronOxford/cockpit.git```


5. From the source folder, run ```python setup.py install```.


Installation instructions to get stuff working on the Mac -Jan 2016
==

1. Install ftgl

```brew install ftgl

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
```
2. May need to install some dependencies that setuptools doesn't pick up.

```brew install homebrew/x11/freeglut
pip install pyopengl
pip install pyopengl_accelerate
pip install pyserial
```

3. Obtain the cockpit source:
```git clone git@github.com:MicronOxford/cockpit.git```


4. From the source folder, run ```python setup.py install```.



Installation instructions for the Raspberry Pi
==

1. Preparation
```
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
```

2. Obtain the cockpit source: ```git clone git@github.com:MicronOxford/cockpit.git```

3. From the source folder, run ```python setup.py install```.
