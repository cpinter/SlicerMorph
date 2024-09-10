import json
import logging
import os
import pathlib
import time
from typing import Annotated, Optional

import vtk

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode


#
# UberonTerminologyImporter
#


class UberonTerminologyImporter(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Uberon Terminology Importer")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "SlicerMorph.SlicerMorph Utilities")]
        self.parent.dependencies = ['Terminologies']
        self.parent.contributors = ["Csaba Pinter (EBATINCA S.L.)"]
        self.parent.helpText = _("""This module imports an Uberon JSON ontology as a new terminology context.""")
        self.parent.acknowledgementText = _("""
This file was originally developed by Csaba Pinter, EBATINCA, and was funded by the MorphoCloud project.
""")


#
# UberonTerminologyImporterParameterNode
#
@parameterNodeWrapper
class UberonTerminologyImporterParameterNode():
    """
    The parameters needed by module.

    inputFilePath - The JSON file to import
    """
    inputFilePath: pathlib.Path


#
# UberonTerminologyImporterWidget
#
class UberonTerminologyImporterWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None
        self._updatingGUIFromParameterNode = False

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/UberonTerminologyImporter.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = UberonTerminologyImporterLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.importTerminologyButton.clicked.connect(self.onImportTerminologyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # # Select default input nodes if nothing is selected yet to save a few clicks for the user
        # if not self._parameterNode.inputVolume:
        #     firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
        #     if firstVolumeNode:
        #         self._parameterNode.inputVolume = firstVolumeNode

    def setParameterNode(self, inputParameterNode: Optional[UberonTerminologyImporterParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

        # Initial GUI update
        self._checkCanApply()

    def _checkCanApply(self, caller=None, event=None) -> None:
        if self._parameterNode and self._parameterNode.inputFilePath:
            self.ui.importTerminologyButton.toolTip = _("Import selected file as new terminology context")
            self.ui.importTerminologyButton.enabled = True
        else:
            self.ui.importTerminologyButton.toolTip = _("Select input file")
            self.ui.importTerminologyButton.enabled = False

    def onImportTerminologyButton(self) -> None:
        """Run processing when user clicks "Apply" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            # Compute output
            self.logic.process(self._parameterNode)


#
# UberonTerminologyImporterLogic
#
class UberonTerminologyImporterLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

        # Constants
        self.containmentPredicateIDs = ['is_a', 'http://purl.obolibrary.org/obo/BFO_0000050']  # IsA and PartOf predicates

        # Loaded ontology variables
        self.loadedJson = None
        self.loadedJsonFlatList = None

    def getParameterNode(self):
        return UberonTerminologyImporterParameterNode(super().getParameterNode())

    def process(self, parameterNode) -> None:
        """
        Load the selected JSON file as a terminology.
        :param inputFilePath: The JSON file to import as a terminology context
        """
        if not parameterNode:
            raise ValueError("Input is invalid")
        inputFilePath = parameterNode.inputFilePath
        if not os.path.exists(inputFilePath):
            raise ValueError(f"Selected input file {inputFilePath} does not exist")

        startTime = time.time()

        with open(inputFilePath, 'r') as fh:
            self.loadedJson = json.loads(fh.read())
            self.loadedJsonFlatList = list(self.flatListFromDict(self.loadedJson))

        # Find root node (parent the direct children of which will be added as categories)
        rootNodeLabel = 'subdivision of skeleton'  #TODO: If we want to give more options to the user we can expose this on the UI
        rootNodeListItem = self.findValueInFlatList(rootNodeLabel, 'lbl')
        rootNodeJsonElement = self.getJsonElementFromFlatElement(rootNodeListItem, 4)
        rootNodeID = rootNodeJsonElement['id']

        # Collect direct children (sub-categories) that are not leaves
        childNodeIDs = self.getChildrenForNode(rootNodeID)

        # Initialize terminology JSON dictionary to be filled with categories and types
        terminologyJson = {}
        terminologyJson["SegmentationCategoryTypeContextName"] = rootNodeLabel
        terminologyJson["@schema"] = "https://raw.githubusercontent.com/qiicr/dcmqi/master/doc/schemas/segment-context-schema.json#"
        segmentationCodes = {}
        terminologyJson["SegmentationCodes"] = segmentationCodes
        categories = []
        segmentationCodes["Category"] = categories

        # For each child, add terminology category for with the nodes inside as types in the category
        usedNodeIDs = set()
        for childNodeID in childNodeIDs:
            # Get child Uberon JSON element
            childListItem = self.findValueInFlatList(childNodeID, 'id')
            nodeJsonElement = self.getJsonElementFromFlatElement(childListItem, 4)
            childLabel = nodeJsonElement['lbl']

            # Get all children of the category node in Uberon
            typeNodeIDsInCategory = self.getChildrenForNode(childNodeID, True)
            logging.info(f'Adding category for child with label {childLabel}  (ID: {childNodeID}), children: {len(typeNodeIDsInCategory)}')
            if len(typeNodeIDsInCategory) == 0:
                continue  # If there are no children (category is a leaf), then leave it for later in "Other" category

            # Add new category
            newCategory = {}
            newCategory["CodeMeaning"] = childLabel
            newCategory["CodingSchemeDesignator"] = 'Uberon'  #TODO:
            newCategory["CodeValue"] = childNodeID
            newCategory["showAnatomy"] = 'false'
            newTypes = []
            newCategory["Type"] = newTypes
            categories.append(newCategory)

            for typeNodeID in typeNodeIDsInCategory:
                # Get type Uberon JSON element
                typeListItem = self.findValueInFlatList(typeNodeID, 'id')
                typeJsonElement = self.getJsonElementFromFlatElement(typeListItem, 4)
                typeLabel = typeJsonElement['lbl']
                # Add new type in current category
                newType = {}
                newType["CodeMeaning"] = typeLabel
                newType["CodingSchemeDesignator"] = 'Uberon'  #TODO:
                newType["CodeValue"] = typeNodeID
                newType["recommendedDisplayRGBValue"] = [128, 128, 128]  #TODO: Generate color
                newTypes.append(newType)
                usedNodeIDs.add(typeNodeID)

        # Collect all nodes that are not added yet
        #TODO:

        # Add terminology category "Other" with these nodes as types
        #TODO:

        # Write out JSON file
        with open('d:/test.json', 'w') as fh:  #TODO: To temporary folder and then import
            json.dump(terminologyJson, fh)

        logging.info(f'Importing ontology completed in {time.time()-startTime:.2f} seconds')

    @staticmethod
    def flatListFromDict(dictionary, previous=None):
        """
        Generate flat list from JSON dictionary to make it better searchable.
        Source: https://stackoverflow.com/questions/71266551/how-to-completely-traverse-a-complex-dictionary-of-unknown-depth-in-python
        """
        previous = previous[:] if previous else []
        if isinstance(dictionary, dict):
            for key, value in dictionary.items():
                if isinstance(value, dict):
                    for d in UberonTerminologyImporterLogic.flatListFromDict(value,  previous + [key]):
                        yield d
                elif isinstance(value, list) or isinstance(value, tuple):
                    for k,v in enumerate(value):
                        for d in UberonTerminologyImporterLogic.flatListFromDict(v, previous + [key] + [[k]]):
                            yield d
                else:
                    yield previous + [key, value]
        else:
            yield previous + [dictionary]

    def findValueInFlatList(self, value, tag=None):
        """
        Find item in flat list with the last value equal to the given value.
        :param str value: Value to look for. E.g. 'subdivision of skeletal system'
        :return list: Flat list item having the given value, e.g. ['graphs', [0], 'nodes', [50], 'lbl', 'subdivision of skeletal system']
        """
        foundNodeFlatListElem = None
        for elem in self.loadedJsonFlatList:
            if elem[-1] == value:
                if tag is None or elem[-2] == tag:
                    foundNodeFlatListElem = elem
                    # logging.info(f'Found element {value}, node index {foundNodeFlatListElem[4]}')
                    break
                else:
                    logging.error(f'ZZZ Found but discarded:\n{elem}')
        if foundNodeFlatListElem is None:
            raise RuntimeError(f'Failed to find item with last value {value} in the ontology')
        return foundNodeFlatListElem

    def getJsonElementFromFlatElement(self, flatElement, depth=99999):
        """
        Get sub-dictionary from loaded JSON ontology specified by the arguments.
        :param list flatElement: Element list from flattened JSON
        :param int depth: Depth to which the dictionary tree is considered. Default is to consider them all
        For example if flatElement is ['graphs', [0], 'nodes', [50], 'lbl', 'subdivision of skeletal system'], and
        depth is 3, then the JSON element is returned that corresponds to ['graphs', [0], 'nodes', [50]]
        """
        if self.loadedJson is None:
            logging.error(f'No JSON dictionary is loaded.')
            return None
        currentJson = self.loadedJson
        for currentDepth, elem in enumerate(flatElement):
            if isinstance(elem, list):
                elem = elem[0]  # List indices are wrapped in a list (not sure why)
            if currentDepth == depth:
                return currentJson
            currentJson = currentJson[elem]
        return currentJson

    def getChildrenForNode(self, uberonNodeID, recursive=False):
        """
        Get children of the specified uberon node in the loaded uberon dictionary.
        :param string uberonNodeID: Uberon node ID, e.g. "http://purl.obolibrary.org/obo/UBERON_0001739"
        """
        directChildNodeIDs = set()
        for elem in self.loadedJsonFlatList:
            if elem[2] == 'edges' and elem[4] == 'obj' and elem[5] == uberonNodeID:
                edge = self.getJsonElementFromFlatElement(elem, 4)
                if edge['pred'] in self.containmentPredicateIDs:
                    # logging.error(f'ZZZ Child with ID found: {edge["sub"]} (pred: {edge["pred"]})')
                    directChildNodeIDs.add(edge['sub'])
        if not recursive:
            return directChildNodeIDs
        # Handle request for recursive search
        # allChildNodeIDs = directChildNodeIDs.copy()
        allChildNodeIDs = set()
        for childNodeID in directChildNodeIDs:
            if childNodeID in allChildNodeIDs:
                continue  # Skip circular connections
            allChildNodeIDs = allChildNodeIDs.union(self.getChildrenForNode(childNodeID, True))
        allChildNodeIDs = allChildNodeIDs.union(directChildNodeIDs)
        return allChildNodeIDs


#
# UberonTerminologyImporterTest
#
class UberonTerminologyImporterTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_UberonTerminologyImporter1()

    def test_UberonTerminologyImporter1(self):
        """Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData

        registerSampleData()
        inputVolume = SampleData.downloadSample("UberonTerminologyImporter1")
        self.delayDisplay("Loaded test data set")

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = UberonTerminologyImporterLogic()

        # Test algorithm with non-inverted threshold
        logic.process(inputVolume, outputVolume, threshold, True)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.process(inputVolume, outputVolume, threshold, False)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay("Test passed")
