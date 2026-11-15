# Rhino startup entrypoint. Configured in Rhino General Options > StartupCommands.
# Inventaur Rhino Standards 1.3.2 + RhinoAI MCP autostart.
import Rhino, traceback, os, codecs

_INV_INSTALLER_PATH = os.path.join(os.path.expanduser("~"), "Documents", "Inventaur", "Rhino Standards", "Inventaur_RhinoStandards_Install.py")
def _inv_ensure_directory(path):
    """Create a directory on both IronPython 2.7 and CPython 3."""
    if os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise


_INV_BOOTSTRAP_LOG_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Inventaur", "RhinoStandards", "logs", "Inventaur_RhinoBootstrap.log"
)
_inv_ensure_directory(os.path.dirname(_INV_BOOTSTRAP_LOG_PATH))

def _inv_bootstrap_log(message):
    try:
        with codecs.open(_INV_BOOTSTRAP_LOG_PATH, "a", "utf-8") as stream:
            stream.write(str(message) + "\n")
    except Exception:
        pass

# Install styles, hatches, layers and document event routing first.
try:
    with codecs.open(_INV_INSTALLER_PATH, "r", "utf-8") as stream:
        _inv_installer_source = stream.read()
    eval(compile(_inv_installer_source, _INV_INSTALLER_PATH, "exec"), globals(), globals())
    _inv_bootstrap_log("STANDARDS_BOOTSTRAP_OK version=1.3.2")
except Exception:
    _inv_bootstrap_log("STANDARDS_BOOTSTRAP_ERROR\n" + traceback.format_exc())

# Start the MCP explicitly on every Rhino launch. Keep this separate from the
# standards installer exception path so an installer/logging failure cannot
# prevent the MCP start command from running.
try:
    _inv_mcp_start_result = Rhino.RhinoApp.RunScript("_MCPStart", False)
    _inv_bootstrap_log("MCPSTART_RUNSCRIPT_RETURN=" + repr(_inv_mcp_start_result))
except Exception:
    _inv_bootstrap_log("MCPSTART_ERROR\n" + traceback.format_exc())
