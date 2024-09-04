import json
import logging
import os
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
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""This module imports an Uberon JSON ontology as a new terminology context.""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Csaba Pinter, EBATINCA, and was funded by TODO:.
""")


#
# UberonTerminologyImporterParameterNode
#
# @parameterNodeWrapper  #TODO: The wrapper cannot process the base class
class UberonTerminologyImporterParameterNode(slicer.vtkMRMLScriptedModuleNode):
    """
    The parameters needed by module.

    inputFilePath - The JSON file to import
    """
    # inputFilePath: str  #TODO: ctkPathLineEdit is not supported by guiConnectors


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
        self.ui.uberonJsonPathLineEdit.validInputChanged.connect(self.updateParameterNodeFromGUI)
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
            # self._parameterNode.disconnectGui(self._parameterNodeGuiTag)  #TODO: The wrapper cannot process the base class
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            # self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)  #TODO: The wrapper cannot process the base class
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def _checkCanApply(self, caller=None, event=None) -> None:
        inputFilePath = self._parameterNode.GetParameter(self.logic.parameterName_uberonJsonPath)
        if self._parameterNode and inputFilePath:
            self.ui.importTerminologyButton.toolTip = _("Import selected file as new terminology context")
            self.ui.importTerminologyButton.enabled = True
        else:
            self.ui.importTerminologyButton.toolTip = _("Select input file")
            self.ui.importTerminologyButton.enabled = False

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
        self.ui.uberonJsonPathLineEdit.currentPath = self._parameterNode.GetParameter(self.logic.parameterName_uberonJsonPath)

        self._checkCanApply()

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch
        self._parameterNode.SetParameter(self.logic.parameterName_uberonJsonPath, self.ui.uberonJsonPathLineEdit.currentPath)
        self._parameterNode.EndModify(wasModified)

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
        self.parameterName_uberonJsonPath = 'UberonJsonPath'

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
        inputFilePath = parameterNode.GetParameter(self.parameterName_uberonJsonPath)
        if not os.path.exists(inputFilePath):
            raise ValueError(f"Selected input file {inputFilePath} does not exist")

        with open(inputFilePath, 'r') as fh:
            self.loadedJson = json.loads(fh.read())
            self.loadedJsonFlatList = list(self.flatListFromDict(self.loadedJson))

        # Find "subdivision of skeleton"
        rootNodeFlatList = None
        rootElementLabel = 'subdivision of skeletal system'
        for elem in self.loadedJsonFlatList:
            if elem[-1] == rootElementLabel:
                rootNodeFlatList = elem  # Should be: # ['graphs', [0], 'nodes', [50], 'lbl', 'subdivision of skeletal system']
                logging.info(f'Found element {rootElementLabel}, node index {rootNodeFlatList[4]}')
                break
        if rootNodeFlatList is None:
            raise RuntimeError(f'Failed to find node with label {rootElementLabel} in the ontology')
        rootNodeJsonElement = self.getJsonElementFromFlatElement(rootNodeFlatList, 4)
        rootNodeID = rootNodeJsonElement['id']
        logging.error(f'ZZZ rootNodeID: {rootNodeID}')

        # # Collect direct children (sub-categories) that are not leaves
        # for elem in self.loadedJsonFlatList:
        #     if elem[2] == 'edges' and elem[4] == 'obj':

        # For each subcategory
        #   Add terminology category with the nodes inside as types in the category
        # Collect all nodes that are not added yet
        # Add terminology category "Other" with these nodes as types

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

    def getChildrenForNode(self, uberonNodeID):
        """
        Get children of the specified uberon node in the loaded uberon dictionary.
        :param string uberonNodeID: Uberon node ID, e.g. "http://purl.obolibrary.org/obo/UBERON_0001739"
        """
        pass  #TODO:


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
