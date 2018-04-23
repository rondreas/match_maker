import os

import pymel.core as pm
import maya.api.OpenMaya as om

from maya import OpenMayaUI as omui

try:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    from PySide2 import __version__
    from shiboken2 import wrapInstance
except ImportError:
    from PySide.QtCore import *
    from PySide.QtGui import *
    from PySide import __version__
    from shiboken import wrapInstance


# Get the Maya window so we can parent our widget to it.
mayaMainWindowPtr = omui.MQtUtil.mainWindow()
mayaMainWindow = wrapInstance(long(mayaMainWindowPtr), QWidget)


def get_transforms(hierarchy=False):
    """ Return a list of all transforms with a child mesh for selected items. """

    result = list()

    for selection in pm.selected():

        if selection.listRelatives(children=True, type='mesh'):
            result += [selection]

        if hierarchy:

            # Get all meshes in hierarchy,
            child_meshes = pm.listRelatives(
                selection,
                allDescendents=True,
                type='mesh'
            )

            # Get the transform for each mesh,
            result += [mesh.getTransform() for mesh in child_meshes]

    # Cast to a set to remove any item occurring more than once in the final list,
    # before casting back to a list.
    return list(set(result))


def find_closest(dictionary, target):
    """
        Search a dictionary for values most close to target to a float precision of 3.
    """

    # Get the lowest value in dictionary,
    min_diff = min(abs(value - target) for value in dictionary.values())

    # Find all keys which are same as the minimum value, rounded to a float precision of 3.
    keys = [k for k, v in dictionary.items() if round(float(abs(v - target)), 3) == round(float(min_diff), 3)]
    
    return keys
    
       
def closest_center(needle, haystack):
    """ Iterate over each straw in haystack and find closest matching bounding box center. """
    
    # Get a point for center of needle bounding box, cast to a vector,
    target_center_point = pm.dt.Vector(needle.getBoundingBox(space='world').center())
    
    center_points = dict()
    
    # For each straw, get the distance between target and current straw
    for straw in haystack:
        center_points[straw] = target_center_point.distanceTo(
            pm.dt.Vector(straw.getBoundingBox(space='world').center())
        )

    # Find the straw most similar to needle center point.
    return find_closest(center_points, 0.0)


def closest_area(needle, haystack):
    """ Iterate over each straw in the haystack and see if similar to needle, """

    # Get the surface area of needle,
    needle_area = needle.area()
    
    straw_areas = dict()

    # Surface area for each straw,
    for straw in haystack:        
        straw_areas[straw] = straw.area()
        
    # Find all straws which are most close to area size of needle,
    return find_closest(straw_areas, needle_area)


def get_softselection():
    """ Get a list of all paths to transforms affected by current soft selection, """
    
    items = list()
    
    # Get the active 'rich selecttion' ie soft select
    softSelection = om.MGlobal.getRichSelection()
    sel = softSelection.getSelection()
    
    # Create and iterator and run through the selection list,
    iter = om.MItSelectionList(sel)
    while not iter.isDone():
        
        # Get dag path for current item and it's lowest transform,
        dagPath = iter.getDagPath()        
        transform = dagPath.transform()
        
        # append the minimum unique string representation for the path to transform
        # to result list,
        items.append(
            om.MDagPath().getAPathTo(transform).partialPathName()
        )
        
        iter.next()
        
    # Return all items which were affected by soft select.
    return items
    
            
def select_in_sphere(item, radius=1.0):
    """ Using soft select, get all items which are inside soft select radius. """
    
    # If any current selection, save for later,
    selected = pm.selected()
    
    # Select specified item,
    pm.select(item)
    
    # Activate soft select, global falloff with a distance equal to given radius 
    pm.softSelect(
        softSelectEnabled=True,
        softSelectFalloff=2,
        softSelectDistance=radius,
    )
    
    # Call OpenMaya function to get the items affected by current soft select, 
    items = get_softselection()
    
    # Disable and reset soft select
    pm.softSelect(
        softSelectEnabled=False,
        softSelectReset=True,
    )
    
    # Return to previous selection if there was any,
    if selected:
        pm.select(selected)
    else:
        pm.select(clear=True)

    # Return the list of pymel objects for items
    return pm.ls(items)
    

def set_exclusion(a, b):
    """ Given two lists, return a list where all items from a are removed from b. """
    return list(set(b).difference(set(a)))


def find_best_match(needle, haystack):
    """ Find the most likely match by comparing center of bounding box and surface area.

    returns item most likely matching needle.

    """

    # Match center point of bounding boxes,
    center_matches = closest_center(needle, haystack)

    # If only one candidate left, we will return the result,
    if len(center_matches) == 1:
        return center_matches[0]

    # Run the second comparision for which bounding box center is most similar to needle, return list of candidates
    # hopefully it should only be one, unless there is a bunch of items sharing same surface area and position.
    area_matches = closest_area(needle, center_matches)

    # Only return first best match,
    return area_matches[0]


def match(source):
    """ Iterate over a list of mesh objects, and pair them to their closest match.

    returns a list of tuple pairs for matching items,

    """

    matches = list()

    for node in source:

        # Skip any node which doesn't have any immediate children of type 'mesh'
        if node.listRelatives(children=True, type='mesh'):

            # To avoid checking absolutely every item in scene, let's limit our search to any item
            # close to the current item in source list,
            limited_search = select_in_sphere(node)

            # create a list of items we want to compare to
            haystack = set_exclusion(source, limited_search)

            # Append a tuple pair of most likely match to current node,
            matches.append((node, find_best_match(node, haystack)))

    return matches


class Window(QWidget):
    """ UI class for matching low-poly objects to best matching high-poly, or vice-versa."""

    def __init__(self, parent=mayaMainWindow):
        super(Window, self).__init__(parent=parent)

        self.low_poly_items = list()
        self.high_poly_items = list()

        if os.name is 'posix':
            self.setWindowFlags(Qt.Tool)
        else:
            self.setWindowFlags(Qt.Window)

        self.setWindowTitle("Match Maker")

        self.setLayout(QGridLayout())

        self.loadOptions = QButtonGroup()
        self.loadOptions.setExclusive(True)

        self.loadOptions.addButton(QRadioButton('Selected'), 0)
        self.loadOptions.addButton(QRadioButton('Hierarchy'), 1)

        # Set 'Selected' as default
        self.loadOptions.button(0).setChecked(True)

        self.lowPolyBtn = QPushButton('Load Low')
        self.lowPolyBtn.setCheckable(True)
        self.lowPolyBtn.clicked.connect(self.set_low_poly_items)

        self.highPolyBtn = QPushButton('Load High')
        self.highPolyBtn.setCheckable(True)
        self.highPolyBtn.clicked.connect(self.set_high_poly_items)

        self.search = QLineEdit('_lp')
        self.replace = QLineEdit('_hp')

        self.matchBtn = QPushButton('Match')
        self.matchBtn.clicked.connect(self.match)
        self.matchBtn.setEnabled(False)

        self.layout().addWidget(self.loadOptions.button(0), 0, 0)
        self.layout().addWidget(self.loadOptions.button(1), 0, 1)

        self.layout().addWidget(self.lowPolyBtn, 1, 0)
        self.layout().addWidget(self.highPolyBtn, 1, 1)

        self.layout().addWidget(self.search, 2, 0)
        self.layout().addWidget(self.replace, 2, 1)

        # TODO Align center,
        self.layout().addWidget(self.matchBtn, 3, 0, 1, 2)

    def set_low_poly_items(self):
        """ """
        hierarchy = self.loadOptions.checkedButton().text() == 'Hierarchy'

        if self.lowPolyBtn.isChecked():
            self.matchBtn.setEnabled(True)
            self.low_poly_items = get_transforms(hierarchy)

        else:
            self.matchBtn.setEnabled(False)
            self.low_poly_items = list()

    def set_high_poly_items(self):
        """ """
        hierarchy = self.loadOptions.checkedButton().text() == 'Hierarchy'

        if self.highPolyBtn.isChecked():
            self.high_poly_items = get_transforms(hierarchy)

        else:
            self.high_poly_items = list()

    def match(self):
        """ Attempt matching each low-poly to most likely high-poly. """

        for item in self.low_poly_items:

            # TODO Allow user to define search radius,
            # Get all items within a sphere diameter of 1 unit,
            items_near = select_in_sphere(item, radius=0.5)

            # Exclude low-poly
            items = set_exclusion(self.low_poly_items, items_near)

            # If high poly items selected, only look for items which are both near and in the list
            # of high poly items.
            if self.high_poly_items:
                items = list(set(self.high_poly_items) & set(items))

            # If there are any items withing search range, and not excluded by other means,
            # rename the matching item according to users search and replace.
            if items:
                name = item.nodeName().replace(self.search.text(), self.replace.text())
                pm.rename(find_best_match(item, items), name)

            # self.matches.append((item, find_best_match(item, items)))


def ui():
    window = Window()
    window.show()
    return window
