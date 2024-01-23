import sublime
import sublime_plugin

# helper event listener:
class PluginHelperEventListener(sublime_plugin.EventListener):
    file_name = None
    callback = None

    def on_load(self, view):
        if not PluginHelperEventListener.file_name:
            return
        if view.file_name() == PluginHelperEventListener.file_name:
            PluginHelperEventListener.callback(view)
            PluginHelperEventListener.file_name = None
            PluginHelperEventListener.callback = None

class PluginHelperInsertStringInActiveView(sublime_plugin.TextCommand):
    def run(self, edit, point, string):
        sublime.active_window().active_view().insert(edit, point, string)