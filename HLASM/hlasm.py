#!/usr/bin/env python
# -*- coding: utf-8 -*-

# standard modules:
import os
import collections
import re
import json
import sys

# sublime modules:
import sublime
import sublime_plugin

# add the current directory to the module path if it's not there yet:
module_path = os.path.dirname(__file__)
if module_path not in sys.path:
    sys.path.append(module_path)
    
import plugin_helpers

class HLASMPlugin:
    def __init__(self):
        self.settings_path = os.path.join(os.path.dirname(__file__), 'hlasm.json') # load plugin settings
        settings = json.loads(open(self.settings_path).read()) # parse JSON
        self.settings = settings

plugin = HLASMPlugin()

class HlasmPrintSubroutines(sublime_plugin.TextCommand):
    def run(self, edit):
        source_file_name = sublime.active_window().active_view().file_name()
        module_name = os.path.splitext(os.path.basename(source_file_name))[0]
        routines = collections.OrderedDict()
        routine_name = module_name
        routines[routine_name] = {'calls': []}
        comments = []
        comment_group = None

        for line in open(source_file_name, errors='ignore'):
            if line.startswith('*'):
                comments.append(line[1:71])
                continue
            else:
                comment_group = '\n'.join(comments)
                comments = []

            match = re.match(plugin.settings['subroutine_start_pattern'], line)
            if match:
                routine_name = match.group('name').upper()
                routines[routine_name] = {'calls': []}
                if comment_group:
                    routines[routine_name]['comment'] = comment_group
            
            match = re.match(plugin.settings['subroutine_call_pattern'], line)
            if match:
                    routines[routine_name]['calls'].append(match.group('name').upper())
        
        text = []
        for routine in routines:
            if not routines[routine]['calls']:
                continue
            if text:
                text.append('')
            text.append(routine)
            for call in routines[routine]['calls']:
                text.append('  ' + call)

        window = sublime.active_window()
        window.new_file()
        window.run_command('plugin_helper_insert_string_in_active_view', {'point': 0, 'string': '\n'.join(text)})

class HlasmFindLineInListing(sublime_plugin.TextCommand):
    def run(self, edit):
        window = sublime.active_window()
        view = window.active_view()
        self.line = view.substr(view.line(view.sel()[0])).rstrip()

        file_name = view.file_name()
        listing_file_name = [os.path.dirname(file_name), '..', plugin.settings['listing_ext']]
        listing_file_name += [os.path.splitext(os.path.basename(file_name))[0] + '.' + plugin.settings['listing_ext']]
        listing_file_name = os.path.join(*listing_file_name)

        plugin_helpers.PluginHelperEventListener.file_name = os.path.abspath(listing_file_name)
        plugin_helpers.PluginHelperEventListener.callback = self.process_listing

        if not os.path.isfile(listing_file_name):
            view.run_command("endevor_get_listing")
            return

        view = window.find_open_file(listing_file_name)
        window.focus_view(view)
        if view:
            self.process_listing(view)
        else:
            window.open_file(listing_file_name)

    def process_listing(self, view):
        position = view.find(self.line, 0, sublime.LITERAL)
        view.sel().clear()
        view.sel().add(position)
        view.show_at_center(position)

class HlasmSetTag(sublime_plugin.TextCommand):
    def run(self, edit):
        window = sublime.active_window()
        tag = plugin.settings.get('tag', '')
        window.show_input_panel("Tag:", tag, self.on_tag, None, None)

    def on_tag(self, tag):
        plugin.settings['tag'] = tag
        open(plugin.settings_path, 'w').write(json.dumps(plugin.settings, indent=4, sort_keys=True))

class HlasmTagLines(sublime_plugin.TextCommand):
    def run(self, edit):
        tag = plugin.settings['tag']
        selection = self.view.sel()
        for region in selection:
            region_text = self.view.substr(region)
            region_lines = region_text.split('\n')
            tagged_lines = []
            if len(region_lines) == 1:
                line = region_lines[0]
                line = line.ljust(71)
                tagged_lines.append(line[:71 - len(tag)] + tag)
            else:
                tagged_lines.append('*' + 'vv{}'.format(tag).rjust(70))
                tagged_lines.extend(region_lines)
                tagged_lines.append('*' + '^^{}'.format(tag).rjust(70))
            self.view.replace(edit, region, '\n'.join(tagged_lines))

class HlasmListingFindLineInSource(sublime_plugin.TextCommand):
    def run(self, edit):
        window = sublime.active_window()
        view = window.active_view()
        self.line = view.substr(view.line(view.sel()[0]))[50:122]

        file_name = view.file_name()
        source_file_name = [os.path.dirname(file_name), '..', plugin.settings['source_ext']]
        source_file_name += [os.path.splitext(os.path.basename(file_name))[0] + '.' + plugin.settings['source_ext']]
        source_file_name = os.path.join(*source_file_name)

        plugin_helpers.PluginHelperEventListener.file_name = os.path.abspath(source_file_name)
        plugin_helpers.PluginHelperEventListener.callback = self.process_source

        view = window.find_open_file(source_file_name)
        window.focus_view(view)
        if view:
            self.process_source(view)
        else:
            window.open_file(source_file_name)

    def process_source(self, view):
        position = view.find(self.line, 0, sublime.LITERAL)
        view.sel().clear()
        view.sel().add(position)
        view.show_at_center(position)

class HlasmListingFindMacroOriginCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        (row, column) = self.view.rowcol(self.view.sel()[0].begin())
        while row > 0:
            text_point = self.view.text_point(row, 0)
            line = self.view.substr(self.view.line(text_point))
            if not line[123:].startswith(' ') and line[49:].startswith(' ') and line.startswith(' ' * 45):
                self.view.sel().clear()
                self.view.sel().add(sublime.Region(text_point))
                self.view.show_at_center(text_point)
                break
            row -= 1
