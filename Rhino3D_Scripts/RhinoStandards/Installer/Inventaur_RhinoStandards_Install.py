# -*- coding: utf-8 -*-
"""Inventaur Rhino 9 drafting standards installer.
Adds Rhino's full default hatch library, practical McNeel PAT patterns,
formal non-reference annotation styles, drafting layers and persistent
Text/Annotation/Hatch object routing.
"""
import os, sys, traceback, codecs
from datetime import datetime
import Rhino
import scriptcontext as sc
import System
from System.Drawing import Color
from Rhino.DocObjects import ObjectType, DimensionStyle, HatchPattern, Font
from Rhino.Geometry import TextEntity, TextDot

VERSION = '1.3.2'
STICKY_KEY = 'INVENTAUR_RHINO_STANDARDS_V1'
BASE_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'Inventaur', 'Rhino Standards')
TEMPLATE_PATH = os.path.join(BASE_DIR, 'Inventaur_Architecture_MM.3dm')
PAT_PATH = os.path.join(BASE_DIR, 'McNeel_Rhino_Hatch_Library.pat')
LOG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'Inventaur', 'RhinoStandards', 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'Inventaur_RhinoStandards.log')


def _ensure_directory(path):
    """Create a directory without Python 3-only exist_ok support."""
    if os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise

LAYER_DEFS = [
 ('00_GUIDES', (125,135,145)),
 ('01_SITE::BOUNDARY', (75,155,220)), ('01_SITE::TOPOGRAPHY', (125,160,160)), ('01_SITE::LANDSCAPE', (105,165,95)),
 ('02_EXISTING', (150,150,150)), ('03_DEMOLITION', (215,75,75)),
 ('04_ARCHITECTURE::GENERAL', (230,230,230)), ('04_ARCHITECTURE::WALLS', (245,245,245)),
 ('04_ARCHITECTURE::DOORS', (205,165,90)), ('04_ARCHITECTURE::WINDOWS', (75,175,195)),
 ('04_ARCHITECTURE::FLOORS', (195,180,155)), ('04_ARCHITECTURE::CEILINGS', (190,190,190)),
 ('04_ARCHITECTURE::STAIRS', (185,135,95)), ('04_ARCHITECTURE::ROOFS', (145,125,145)),
 ('05_STRUCTURE::FOUNDATIONS', (205,160,65)), ('05_STRUCTURE::COLUMNS', (220,180,65)),
 ('05_STRUCTURE::BEAMS', (195,145,55)), ('05_STRUCTURE::SLABS', (180,155,105)),
 ('05_STRUCTURE::BRACING', (180,135,60)), ('05_STRUCTURE::CONNECTIONS', (220,190,105)),
 ('06_INTERIORS::PARTITIONS', (175,155,195)), ('06_INTERIORS::JOINERY', (180,135,95)), ('06_INTERIORS::FINISHES', (160,175,185)),
 ('07_FURNITURE::GENERAL', (190,135,75)), ('07_FURNITURE::FIXED', (175,120,65)),
 ('07_FURNITURE::LOOSE', (205,155,95)), ('07_FURNITURE::CUSTOM', (210,170,110)),
 ('08_SERVICES::HVAC', (80,165,190)), ('08_SERVICES::ELECTRICAL', (225,190,65)),
 ('08_SERVICES::PLUMBING', (75,145,210)), ('08_SERVICES::FIRE', (210,75,65)),
 ('TEXT', (235,245,235)), ('ANNOTATIONS', (57,190,105)), ('HATCH', (145,175,145)),
 ('DETAILS', (200,190,140)), ('REFERENCES', (125,145,155)), ('PRESENTATION', (180,165,200))
]


def log(msg):
    try:
        _ensure_directory(LOG_DIR)
        with codecs.open(LOG_FILE, 'a', 'utf-8') as f:
            f.write('[{0}] [Inventaur Standards {1}] {2}\n'.format(datetime.now().strftime('%Y-%m-%dT%H:%M:%S'), VERSION, msg))
    except Exception:
        pass


def color(rgb):
    return Color.FromArgb(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def find_layer(doc, path):
    try:
        return int(doc.Layers.FindByFullPath(path, False))
    except Exception:
        return -1


def ensure_layer(doc, path, rgb):
    idx = find_layer(doc, path)
    if idx >= 0:
        return idx
    idx = int(doc.Layers.AddPath(path, color(rgb)))
    if idx < 0:
        idx = find_layer(doc, path)
    if idx < 0:
        raise RuntimeError('Layer create failed: ' + path)
    return idx


def ensure_layers(doc):
    result = {}
    for path, rgb in LAYER_DEFS:
        result[path] = ensure_layer(doc, path, rgb)
    return result


def hatch_names(doc):
    try:
        return set([str(h.Name) for h in doc.HatchPatterns])
    except Exception:
        return set()


def ensure_hatches(doc):
    before = doc.HatchPatterns.Count
    added_default = 0
    added_pat = 0
    names = hatch_names(doc)
    defaults = HatchPattern.GetDefaultHatchPatterns()
    if defaults is None:
        raise RuntimeError('Rhino default hatch library returned null')
    for pattern in defaults:
        name = str(pattern.Name)
        if name in names:
            continue
        idx = int(doc.HatchPatterns.Add(pattern))
        if idx >= 0:
            names.add(name)
            added_default += 1
    # Use RhinoScriptSyntax's native PAT importer. This is the document-level
    # import path used by Rhino's hatch-pattern tooling and is more reliable
    # here than manually adding ReadFromFile results to the document table.
    try:
        import rhinoscriptsyntax as rs
        imported_names = rs.AddHatchPatterns(PAT_PATH, True) or []
        for imported_name in imported_names:
            name = str(imported_name)
            if name in names:
                continue
            names.add(name)
            added_pat += 1
    except Exception:
        log('PAT_IMPORT_ERROR\n' + traceback.format_exc())
    after = doc.HatchPatterns.Count
    expected_custom = ['Concrete', 'Concrete Reinforced', 'Earth', 'Granite', 'Herringbone', 'Sand']
    log('HATCHES default_available={0} added_default={1} added_pat={2} before={3} after={4} standard_pat_present={5}'.format(len(defaults), added_default, added_pat, before, after, len([n for n in expected_custom if n in names])))
    missing_custom = [name for name in expected_custom if name not in names]
    if missing_custom:
        raise RuntimeError('Custom PAT import incomplete; missing: ' + ', '.join(missing_custom))
    if after < len(defaults):
        missing = [str(p.Name) for p in defaults if str(p.Name) not in names]
        raise RuntimeError('Hatch import incomplete; missing: ' + ', '.join(missing[:25]))
    return {'defaults_available': len(defaults), 'added_default': added_default, 'added_pat': added_pat, 'total': after}


def unit_scale(unit):
    if unit == Rhino.UnitSystem.Millimeters: return 1.0
    if unit == Rhino.UnitSystem.Meters: return 0.001
    if unit == Rhino.UnitSystem.Inches: return 1.0 / 25.4
    if unit == Rhino.UnitSystem.Feet: return 1.0 / 304.8
    return 1.0


def style_exists(doc, name):
    try:
        return doc.DimStyles.FindName(name)
    except Exception:
        return None


def make_style(doc, name, source_token, unit, display, precision, suffix='', alternate=False,
               alt_display=DimensionStyle.LengthDisplay.ModelUnits, alt_factor=1.0, alt_precision=2, alt_suffix=''):
    existing = style_exists(doc, name)
    if existing is not None:
        # Prior setup used Add(style, True), which made reference styles that did not persist.
        # Do not reuse a reference/document-controlled style as the standard.
        if not existing.IsReference and existing.IsValid:
            return int(existing.Index)
        log('SKIP_REFERENCE_STYLE name={0} index={1}; creating persistent replacement'.format(name, existing.Index))
        # Keep the legacy entry intact; use a uniquely named persistent replacement.
        name = name + '_LOCAL'
        existing = style_exists(doc, name)
        if existing is not None and not existing.IsReference and existing.IsValid:
            return int(existing.Index)
    source = None
    for candidate in doc.DimStyles.BuiltInStyles:
        if source_token in str(candidate.Name):
            source = candidate
            break
    if source is None:
        raise RuntimeError('Built-in dimension template not found: ' + source_token)
    st = source.Duplicate()
    st.ClearId()
    st.ClearIndex()
    st.Name = name
    st.UnitSystem = unit
    st.DimensionLengthDisplay = display
    scale = unit_scale(unit)
    st.TextHeight = 2.5 * scale
    st.ArrowLength = 2.5 * scale
    st.ExtensionLineOffset = 0.8 * scale
    st.ExtensionLineExtension = 1.25 * scale
    st.DimensionLineExtension = 1.25 * scale
    st.TextGap = 0.625 * scale
    st.BaselineSpacing = 7.5 * scale
    st.Font = Font('Arial')
    st.LengthResolution = int(precision)
    st.Roundoff = 0.0
    st.Suffix = suffix
    st.ZeroSuppress = DimensionStyle.ZeroSuppression.SuppressTrailing
    st.ArrowType1 = DimensionStyle.ArrowType.SolidTriangle
    st.ArrowType2 = DimensionStyle.ArrowType.SolidTriangle
    st.LeaderArrowType = DimensionStyle.ArrowType.OpenArrow
    st.LeaderArrowLength = 2.5 * scale
    st.LeaderLandingLength = 3.0 * scale
    st.LeaderHasLanding = True
    st.UseKerning = True
    st.AlternateUnitsDisplay = bool(alternate)
    st.AlternateDimensionLengthDisplay = alt_display
    st.AlternateLengthFactor = float(alt_factor)
    st.AlternateLengthResolution = int(alt_precision)
    st.AlternateSuffix = alt_suffix
    st.AlternateZeroSuppress = DimensionStyle.ZeroSuppression.SuppressTrailing
    st.AlternateBelowLine = True
    # IMPORTANT: False creates a normal document style; True creates a reference style.
    idx = int(doc.DimStyles.Add(st, False))
    if idx < 0:
        raise RuntimeError('Persistent dimension style add failed: ' + name)
    stored = doc.DimStyles.FindName(name)
    if stored is None or stored.IsReference:
        raise RuntimeError('Dimension style did not persist as a document style: ' + name)
    return idx


def make_text_style(doc, name, height):
    idx = make_style(doc, name, 'Template Millimeter Large', Rhino.UnitSystem.Millimeters,
                     DimensionStyle.LengthDisplay.Millmeters, 0, '')
    st = doc.DimStyles[idx].Duplicate()
    st.TextHeight = float(height)
    st.ArrowLength = 0.0
    st.LeaderArrowLength = 0.0
    st.TextGap = 0.0
    st.Suffix = ''
    if not doc.DimStyles.Modify(st, idx, True):
        raise RuntimeError('Text style modification failed: ' + name)
    return idx


def ensure_styles(doc, set_current=True):
    mm = make_style(doc, 'INV_STD_MM', 'Template Millimeter Small', Rhino.UnitSystem.Millimeters,
                    DimensionStyle.LengthDisplay.Millmeters, 0)
    make_style(doc, 'INV_STD_M', 'Template Millimeter Small', Rhino.UnitSystem.Meters,
               DimensionStyle.LengthDisplay.Meters, 3, ' m')
    make_style(doc, 'INV_STD_IN_DEC', 'Template Inch Decimal', Rhino.UnitSystem.Inches,
               DimensionStyle.LengthDisplay.InchesDecimal, 2, ' in')
    make_style(doc, 'INV_STD_IN_FRAC', 'Template Inch Fractional', Rhino.UnitSystem.Inches,
               DimensionStyle.LengthDisplay.InchesFractional, 3)
    make_style(doc, 'INV_STD_FT_IN', 'Template Foot-Inch Architectural', Rhino.UnitSystem.Inches,
               DimensionStyle.LengthDisplay.FeetAndInches, 3)
    make_style(doc, 'INV_STD_MM_M', 'Template Millimeter Small', Rhino.UnitSystem.Millimeters,
               DimensionStyle.LengthDisplay.Millmeters, 0, '', True,
               DimensionStyle.LengthDisplay.Meters, 0.001, 3, ' m')
    make_style(doc, 'INV_STD_MM_IN', 'Template Millimeter Small', Rhino.UnitSystem.Millimeters,
               DimensionStyle.LengthDisplay.Millmeters, 0, '', True,
               DimensionStyle.LengthDisplay.InchesDecimal, 1.0/25.4, 2, ' in')
    make_style(doc, 'INV_STD_MM_FT_IN', 'Template Millimeter Small', Rhino.UnitSystem.Millimeters,
               DimensionStyle.LengthDisplay.Millmeters, 0, '', True,
               DimensionStyle.LengthDisplay.FeetAndInches, 1.0/304.8, 3, '')
    make_style(doc, 'INV_STD_M_MM', 'Template Millimeter Small', Rhino.UnitSystem.Meters,
               DimensionStyle.LengthDisplay.Meters, 3, ' m', True,
               DimensionStyle.LengthDisplay.Millmeters, 1000.0, 0, ' mm')
    make_style(doc, 'INV_STD_LEADER_MM', 'Template Millimeter Small', Rhino.UnitSystem.Millimeters,
               DimensionStyle.LengthDisplay.Millmeters, 0)
    make_text_style(doc, 'INV_STD_TEXT_2_5MM', 2.5)
    make_text_style(doc, 'INV_STD_TEXT_3_5MM', 3.5)
    make_text_style(doc, 'INV_STD_TEXT_5_0MM', 5.0)
    make_text_style(doc, 'INV_STD_TEXT_7_0MM', 7.0)
    if set_current:
        unit = doc.ModelUnitSystem
        current_name = 'INV_STD_MM'
        if unit == Rhino.UnitSystem.Meters:
            current_name = 'INV_STD_M'
        elif unit == Rhino.UnitSystem.Inches:
            current_name = 'INV_STD_IN_DEC'
        elif unit == Rhino.UnitSystem.Feet:
            current_name = 'INV_STD_FT_IN'
        chosen = doc.DimStyles.FindName(current_name)
        if chosen is None or not doc.DimStyles.SetCurrent(int(chosen.Index), False):
            raise RuntimeError('Could not set current dimension style to ' + current_name)
    current = str(doc.DimStyles.Current.Name)
    names = [str(s.Name) for s in doc.DimStyles if str(s.Name).startswith('INV_STD_')]
    log('DIMSTYLES count={0} current={1} persistent={2}'.format(len(names), current, len(names)))
    return {'count': len(names), 'current': current, 'names': names}


def route_target(rhino_object):
    g = rhino_object.Geometry
    typ = g.GetType().Name
    if isinstance(g, (TextEntity, TextDot)) or typ in ('TextEntity', 'TextDot'):
        return 'TEXT'
    if typ == 'Hatch' or (rhino_object.ObjectType & ObjectType.Hatch) == ObjectType.Hatch:
        return 'HATCH'
    if (rhino_object.ObjectType & ObjectType.Annotation) == ObjectType.Annotation:
        return 'ANNOTATIONS'
    return None


_busy = set()

def route_object(doc, rhino_object, layer_map=None):
    target = route_target(rhino_object)
    if not target:
        return False
    if layer_map is None:
        layer_map = ensure_layers(doc)
    idx = layer_map[target]
    if int(rhino_object.Attributes.LayerIndex) == int(idx):
        return False
    attrs = rhino_object.Attributes.Duplicate()
    attrs.LayerIndex = int(idx)
    return bool(doc.Objects.ModifyAttributes(rhino_object.Id, attrs, True))


def route_existing(doc, layer_map):
    serial = int(doc.RuntimeSerialNumber)
    if serial in _busy:
        return 0
    _busy.add(serial)
    moved = 0
    try:
        for obj in list(doc.Objects):
            try:
                if route_object(doc, obj, layer_map): moved += 1
            except Exception:
                log('ROUTE_EXISTING_ERROR ' + traceback.format_exc())
    finally:
        _busy.discard(serial)
    return moved


def apply_document(doc, build_template=False):
    if doc is None:
        raise RuntimeError('No Rhino document supplied')
    # Only the standards template builder may set model/page units or tolerances.
    # Opening an existing user model must never silently rescale its geometry.
    if build_template:
        doc.AdjustModelUnitSystem(Rhino.UnitSystem.Millimeters, True)
        doc.AdjustPageUnitSystem(Rhino.UnitSystem.Millimeters, True)
        doc.ModelAbsoluteTolerance = 0.01
        doc.ModelAngleToleranceRadians = 0.017453292519943295
    layers = ensure_layers(doc)
    hatches = ensure_hatches(doc)
    current_is_default = int(doc.DimStyles.CurrentIndex) == 0
    styles = ensure_styles(doc, bool(build_template or current_is_default))
    routed = route_existing(doc, layers)
    if build_template or int(doc.Objects.Count) == 0:
        try:
            doc.Layers.SetCurrentLayerIndex(layers['04_ARCHITECTURE::GENERAL'], True)
        except Exception:
            pass
    result = {'name': str(doc.Name), 'objects': int(doc.Objects.Count), 'layers': int(doc.Layers.Count),
              'styles': styles['count'], 'current_style': styles['current'],
              'hatches': hatches['total'], 'routed_existing': routed}
    log('APPLIED ' + repr(result))
    return result


def on_object_added(sender, event_args):
    try:
        obj = event_args.TheObject
        if obj is None: return
        doc = obj.Document
        if doc is None: return
        target = route_target(obj)
        if target is None: return
        serial = int(doc.RuntimeSerialNumber)
        if serial in _busy: return
        _busy.add(serial)
        try:
            layers = ensure_layers(doc)
            route_object(doc, obj, layers)
        finally:
            _busy.discard(serial)
    except Exception:
        log('ADD_OBJECT_EVENT_ERROR ' + traceback.format_exc())


def on_document_ready(sender, event_args):
    try:
        doc = getattr(event_args, 'Document', None)
        if doc is None and hasattr(sender, 'DimStyles'):
            doc = sender
        if doc is None:
            doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None:
            apply_document(doc, False)
    except Exception:
        log('DOCUMENT_EVENT_ERROR ' + traceback.format_exc())


def install_events():
    old = sc.sticky.get(STICKY_KEY)
    if old:
        for event_name, key in [('AddRhinoObject','add'), ('NewDocument','new'), ('EndOpenDocument','open')]:
            try: getattr(Rhino.RhinoDoc, event_name).__isub__(old[key])
            except Exception: pass
    Rhino.RhinoDoc.AddRhinoObject += on_object_added
    Rhino.RhinoDoc.NewDocument += on_document_ready
    Rhino.RhinoDoc.EndOpenDocument += on_document_ready
    sc.sticky[STICKY_KEY] = {'version': VERSION, 'add': on_object_added, 'new': on_document_ready, 'open': on_document_ready}
    log('EVENT_HANDLERS_INSTALLED version=' + VERSION)


def build_template():
    _ensure_directory(BASE_DIR)
    tmp = TEMPLATE_PATH + '.tmp.3dm'
    if os.path.isfile(tmp): os.remove(tmp)
    tdoc = Rhino.RhinoDoc.CreateHeadless(None)
    if tdoc is None: raise RuntimeError('Could not create headless Rhino document for template')
    try:
        result = apply_document(tdoc, True)
        ok = bool(tdoc.SaveAsTemplate(tmp))
        if not ok: raise RuntimeError('SaveAsTemplate returned False')
    finally:
        tdoc.Dispose()
    if os.path.isfile(TEMPLATE_PATH):
        backup = TEMPLATE_PATH + '.previous'
        if os.path.isfile(backup): os.remove(backup)
        os.rename(TEMPLATE_PATH, backup)
    os.rename(tmp, TEMPLATE_PATH)
    # Independently reopen the written .3dm and verify that definitions persisted.
    check = Rhino.FileIO.File3dm.Read(TEMPLATE_PATH)
    if check is None:
        raise RuntimeError('Template readback failed')
    persisted_styles = [str(x.Name) for x in check.DimStyles if str(x.Name).startswith('INV_STD_')]
    persisted_hatches = int(check.HatchPatterns.Count)
    persisted_layers = int(check.Layers.Count)
    if len(persisted_styles) < 14:
        raise RuntimeError('Template lost annotation styles on save: ' + str(len(persisted_styles)))
    if persisted_hatches < 59:
        raise RuntimeError('Template lost default hatch patterns on save: ' + str(persisted_hatches))
    # Set Rhino's new-document default to this verified template.
    Rhino.ApplicationSettings.FileSettings.TemplateFolder = BASE_DIR
    Rhino.ApplicationSettings.FileSettings.TemplateFile = TEMPLATE_PATH
    log('TEMPLATE_READBACK_OK styles={0} hatches={1} layers={2} objects={3}'.format(len(persisted_styles), persisted_hatches, persisted_layers, check.Objects.Count))
    log('TEMPLATE_SAVED ' + TEMPLATE_PATH + ' ' + repr(result))
    return result


def verify_template_file():
    if not os.path.isfile(TEMPLATE_PATH):
        return None
    check = Rhino.FileIO.File3dm.Read(TEMPLATE_PATH)
    if check is None:
        raise RuntimeError('Existing metric template cannot be read; refusing automatic overwrite')
    styles = [str(x.Name) for x in check.DimStyles if str(x.Name).startswith('INV_STD_')]
    hatch_count = int(check.HatchPatterns.Count)
    layer_count = int(check.Layers.Count)
    if check.Settings.ModelUnitSystem != Rhino.UnitSystem.Millimeters or len(styles) < 14 or hatch_count < 59 or layer_count < 44:
        raise RuntimeError('Existing metric template failed validation; run an explicit template rebuild after reviewing the backup')
    return {'layers': layer_count, 'styles': len(styles), 'hatches': hatch_count, 'objects': int(check.Objects.Count)}


def main():
    _ensure_directory(BASE_DIR)
    install_events()
    doc = Rhino.RhinoDoc.ActiveDoc
    result = apply_document(doc, False)
    template_state = verify_template_file()
    if template_state is None:
        template_state = build_template()
    else:
        Rhino.ApplicationSettings.FileSettings.TemplateFolder = BASE_DIR
        Rhino.ApplicationSettings.FileSettings.TemplateFile = TEMPLATE_PATH
        log('TEMPLATE_REUSED_READBACK_OK ' + repr(template_state))
    print('INVENTAUR RHINO STANDARDS {0} APPLIED'.format(VERSION))
    print('LIVE: ' + repr(result))
    print('TEMPLATE: ' + repr(template_state) + ' | ' + TEMPLATE_PATH)
    print('AUTO ROUTING: TEXT -> TEXT | DIMENSIONS/LEADERS -> ANNOTATIONS | HATCHES -> HATCH')
    print('EXISTING MODEL UNITS AND TOLERANCES PRESERVED; template rebuild is explicit and non-destructive')
    return result

main()
