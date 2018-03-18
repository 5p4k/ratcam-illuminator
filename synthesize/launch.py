import sys
import os

_this_folder = '/Users/spak/Development/ratcam-illuminator/synthesize'

sys.path.append(_this_folder)
sys.path.append(os.path.join(_this_folder, 'venv/lib/python2.7/site-packages'))

execfile(os.path.join(_this_folder, 'radial_illuminator.py'))
