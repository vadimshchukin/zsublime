import re

import sublime, sublime_plugin

class IspfShiftRightCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        selection = self.view.sel()
        for region in selection:
            region_text = self.view.substr(region)
            shifted_lines = []
            for line in region_text.split('\n'):
                shifted_lines.append(self.shift_text_right(line, 2))
            self.view.replace(edit, region, '\n'.join(shifted_lines))

    def shift_text_right(self, text, factor=1):
        for index in range(factor):
            match = re.search(r'\W+(\w).*?(  )', text)
            if match:
                text = text[:match.span(1)[0]] + ' ' + text[match.span(1)[0]:match.span(2)[0]] + text[match.span(2)[0] + 1:]
        return text

class IspfShiftLeftCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        selection = self.view.sel()
        for region in selection:
            region_text = self.view.substr(region)
            shifted_lines = []
            for line in region_text.split('\n'):
                shifted_lines.append(self.shift_text_left(line, 2))
            self.view.replace(edit, region, '\n'.join(shifted_lines))

    def shift_text_left(self, text, factor=1):
        for index in range(factor):
            match = re.search(r'\W+(\w).*?(  )', text)
            if match:
                text = text[:match.span(1)[0] - 1] + text[match.span(1)[0]:match.span(2)[0]] + ' ' + text[match.span(2)[0]:]
        return text

class IspfPadToWidth(sublime_plugin.TextCommand):
    def input(self, args):
        return sublime_plugin.TextInputHandler()

    def run(self, edit, text):
        selection = self.view.sel()
        for region in selection:
            region_text = self.view.substr(region)
            padded_lines = []
            for line in region_text.split('\n'):
                padded_lines.append(line.ljust(int(text)))
            self.view.replace(edit, region, '\n'.join(padded_lines))

