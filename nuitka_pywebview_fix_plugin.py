# User plugin override for Nuitka's bundled PywebViewPlugin.
#
# nuitka/plugins/standard/PywebViewPlugin.py hardcodes the set of
# webview.platforms.* submodules it allows on Windows: winforms,
# edgechromium, edgehtml, mshtml, cef. It predates pywebview adding
# webview/platforms/win32.py (a small DPI/screen-scale helper that
# winforms.py imports directly: `from webview.platforms import win32`),
# so it actively excludes that module — breaking window creation at
# runtime with a misleading "pythonnet cannot be loaded" error.
#
# A plain --include-module=webview.platforms.win32 conflicts with the
# built-in plugin's explicit exclusion decision and hard-aborts the build
# ("Conflict between user and plugin decision"). A YAML implicit-imports
# hint (--user-package-configuration-file) doesn't override it either —
# the plugin's onModuleEncounter veto is authoritative regardless of how
# Nuitka became aware the module might be needed.
#
# So build_nuitka.py disables the built-in plugin (--disable-plugins=
# pywebview) and loads this corrected copy instead (--user-plugin=...),
# adding exactly the one missing whitelist entry. Everything else is
# unchanged from the original.

from nuitka.options.Options import isStandaloneMode
from nuitka.plugins.PluginBase import NuitkaPluginBase
from nuitka.plugins.Plugins import getActiveQtPlugin
from nuitka.utils.Utils import getOS, isMacOS, isWin32Windows


class NuitkaPluginPywebviewWin32Fix(NuitkaPluginBase):
    plugin_name = "pywebview-win32-fix"
    plugin_desc = "Corrected 'webview' package support (adds webview.platforms.win32)."
    plugin_category = "package-support"

    @staticmethod
    def isAlwaysEnabled():
        return True

    @classmethod
    def isRelevant(cls):
        return isStandaloneMode()

    def onModuleEncounter(
        self, using_module_name, module_name, module_filename, module_kind
    ):
        if module_name.isBelowNamespace("webview.platforms"):
            if isWin32Windows():
                result = module_name in (
                    "webview.platforms.winforms",
                    "webview.platforms.edgechromium",
                    "webview.platforms.edgehtml",
                    "webview.platforms.mshtml",
                    "webview.platforms.cef",
                    "webview.platforms.win32",  # <-- the fix: added to the upstream whitelist
                )
                reason = "Platforms package of webview used on '%s'." % getOS()
            elif isMacOS():
                result = module_name == "webview.platforms.cocoa"
                reason = "Platforms package of webview used on '%s'." % getOS()
            elif getActiveQtPlugin() is not None:
                result = module_name = "webview.platforms.qt"
                reason = (
                    "Platforms package of webview used due to '%s' plugin being active."
                    % getActiveQtPlugin()
                )
            else:
                result = module_name = "webview.platforms.gtk"
                reason = (
                    "Platforms package of webview used on '%s' without Qt plugin enabled."
                    % getOS()
                )

            return result, reason
