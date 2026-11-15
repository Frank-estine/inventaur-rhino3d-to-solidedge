#! python 3
# Inventaur Inc. — Rhino 9 automatic annotation layer router
# Version: 1.0.0
#
# Purpose:
#   Automatically route Rhino text objects to the TEXT layer and all other
#   annotation objects (dimensions, leaders, angular/radial annotations, etc.)
#   to the ANNOTATIONS layer.
#
# Scope:
#   - Applies to all open Rhino documents and documents opened/created later.
#   - Does not modify geometry, materials, object names, colours, or non-annotation
#     layer assignments.
#   - Uses object-attribute duplication and changes only LayerIndex.
#
# Install:
#   Add this command to Rhino Options > General >
#   "Run these commands every time Rhino starts":
#   _-RunPythonScript "C:\Users\krish\Documents\Inventaur\Rhino Standards\Inventaur_RhinoAutoLayer.py"

import os
import traceback
from datetime import datetime

import Rhino
import scriptcontext as sc
import System
from System.Drawing import Color
from Rhino.DocObjects import ObjectType
from Rhino.Geometry import TextEntity, TextDot

VERSION = "1.0.0"
STICKY_KEY = "INVENTAUR_RHINO_AUTO_LAYER_ROUTER_V1"
TEXT_LAYER = "TEXT"
ANNOTATION_LAYER = "ANNOTATIONS"

_LOCAL = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
_LOG_DIR = os.path.join(_LOCAL, "Inventaur", "RhinoStandards", "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "Inventaur_RhinoAutoLayer.log")

# Layer colours are restrained drafting colours, independent of the Rhino
# application theme. They can be changed later without changing routing logic.
_LAYER_DEFS = (
    (TEXT_LAYER, Color.FromArgb(245, 245, 245)),
    (ANNOTATION_LAYER, Color.FromArgb(57, 190, 105)),
)

_busy_documents = set()


def _log(message):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as stream:
            stream.write("[{0}] [InventaurAutoLayer {1}] {2}\n".format(
                datetime.now().isoformat(timespec="seconds"), VERSION, message))
    except Exception:
        pass


def _find_root_layer_index(doc, layer_name):
    """Return the index of an exact top-level layer, or -1."""
    try:
        for layer in doc.Layers:
            if (layer.Name == layer_name and
                    layer.ParentLayerId == System.Guid.Empty):
                return int(layer.Index)
    except Exception:
        pass
    return -1


def _ensure_layer(doc, layer_name, colour):
    """Ensure a top-level routing layer exists; return its layer index."""
    idx = _find_root_layer_index(doc, layer_name)
    if idx >= 0:
        return idx

    idx = int(doc.Layers.Add(layer_name, colour))
    if idx < 0:
        # Re-check in case another handler created it concurrently.
        idx = _find_root_layer_index(doc, layer_name)
    if idx < 0:
        raise RuntimeError("Could not create required layer: " + layer_name)
    return idx


def _ensure_routing_layers(doc):
    """Create TEXT and ANNOTATIONS without touching any existing layers."""
    return {
        TEXT_LAYER: _ensure_layer(doc, TEXT_LAYER, _LAYER_DEFS[0][1]),
        ANNOTATION_LAYER: _ensure_layer(doc, ANNOTATION_LAYER, _LAYER_DEFS[1][1]),
    }


def _target_layer_for_object(rhino_object):
    """Classify only Text/TextDot and Rhino annotation geometry."""
    geometry = rhino_object.Geometry

    if isinstance(geometry, (TextEntity, TextDot)):
        return TEXT_LAYER

    # Remaining annotation entities include linear/angular/radial dimensions,
    # leaders and related drafting annotations.
    try:
        if (rhino_object.ObjectType & ObjectType.Annotation) == ObjectType.Annotation:
            return ANNOTATION_LAYER
    except Exception:
        pass

    return None


def _route_one(doc, rhino_object, layer_indices):
    """Change only the object's LayerIndex when it belongs in a routing layer."""
    target_name = _target_layer_for_object(rhino_object)
    if target_name is None:
        return False

    target_index = layer_indices[target_name]
    try:
        current_index = int(rhino_object.Attributes.LayerIndex)
    except Exception:
        current_index = -1

    if current_index == target_index:
        return False

    attributes = rhino_object.Attributes.Duplicate()
    attributes.LayerIndex = target_index

    ok = bool(doc.Objects.ModifyAttributes(rhino_object.Id, attributes, True))
    if ok:
        _log("ROUTED {0} object {1} -> {2}".format(
            rhino_object.Geometry.GetType().Name,
            str(rhino_object.Id),
            target_name))
    else:
        _log("WARN unable to route object {0} -> {1}".format(
            str(rhino_object.Id), target_name))
    return ok


def _route_existing_objects(doc, layer_indices):
    """Move existing Text/Annotation objects only; leave all other objects as-is."""
    try:
        objects = list(doc.Objects)
    except Exception:
        objects = []

    changed = 0
    key = int(doc.RuntimeSerialNumber)
    if key in _busy_documents:
        return 0

    _busy_documents.add(key)
    try:
        for rhino_object in objects:
            try:
                if _route_one(doc, rhino_object, layer_indices):
                    changed += 1
            except Exception:
                _log("ERROR route existing object:\n" + traceback.format_exc())
    finally:
        _busy_documents.discard(key)

    return changed


def _on_object_added(sender, event_args):
    """Global RhinoDoc.AddRhinoObject handler."""
    rhino_object = None
    try:
        rhino_object = event_args.TheObject
        if rhino_object is None:
            return

        doc = rhino_object.Document
        if doc is None:
            return

        target_name = _target_layer_for_object(rhino_object)
        if target_name is None:
            return

        key = int(doc.RuntimeSerialNumber)
        if key in _busy_documents:
            return

        layer_indices = _ensure_routing_layers(doc)
        _busy_documents.add(key)
        try:
            _route_one(doc, rhino_object, layer_indices)
        finally:
            _busy_documents.discard(key)
    except Exception:
        _log("ERROR AddRhinoObject handler:\n" + traceback.format_exc())


def _on_document_ready(sender, event_args):
    """Install the routing layers and classify existing objects in a document."""
    try:
        doc = getattr(event_args, "Document", None)
        if doc is None:
            return
        layer_indices = _ensure_routing_layers(doc)
        moved = _route_existing_objects(doc, layer_indices)
        _log("DOCUMENT READY {0} | layers TEXT={1}, ANNOTATIONS={2} | routed={3}".format(
            doc.Name, layer_indices[TEXT_LAYER], layer_indices[ANNOTATION_LAYER], moved))
    except Exception:
        _log("ERROR document-ready handler:\n" + traceback.format_exc())


def install():
    """Register global handlers and initialise all documents already open."""
    previous = sc.sticky.get(STICKY_KEY)
    if previous:
        try:
            Rhino.RhinoDoc.AddRhinoObject -= previous.get("on_add")
        except Exception:
            pass
        try:
            Rhino.RhinoDoc.NewDocument -= previous.get("on_new")
        except Exception:
            pass
        try:
            Rhino.RhinoDoc.EndOpenDocument -= previous.get("on_open")
        except Exception:
            pass

    Rhino.RhinoDoc.AddRhinoObject += _on_object_added
    Rhino.RhinoDoc.NewDocument += _on_document_ready
    Rhino.RhinoDoc.EndOpenDocument += _on_document_ready

    # Keep handler references alive in the Python runtime.
    sc.sticky[STICKY_KEY] = {
        "version": VERSION,
        "on_add": _on_object_added,
        "on_new": _on_document_ready,
        "on_open": _on_document_ready,
        "log_file": _LOG_FILE,
    }

    docs = []
    try:
        docs = list(Rhino.RhinoDoc.OpenDocuments())
    except Exception:
        pass

    active = Rhino.RhinoDoc.ActiveDoc
    if active is not None and all(
            int(d.RuntimeSerialNumber) != int(active.RuntimeSerialNumber) for d in docs):
        docs.append(active)

    for doc in docs:
        try:
            indices = _ensure_routing_layers(doc)
            moved = _route_existing_objects(doc, indices)
            _log("INITIALISED {0} | routed existing={1}".format(doc.Name, moved))
        except Exception:
            _log("ERROR initialising document:\n" + traceback.format_exc())

    _log("INSTALLED | documents={0} | event handlers active".format(len(docs)))
    print("Inventaur AutoLayer {0}: active. Text -> TEXT; dimensions/leaders -> ANNOTATIONS.".format(VERSION))
    print("Log: " + _LOG_FILE)


install()
