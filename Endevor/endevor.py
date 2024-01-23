# -*- coding: utf-8 -*-

# standard imports:
import os
import sys
import json
import re
import tempfile
import subprocess
import logging
import urllib.request

# sublime modules:
import sublime
import sublime_plugin

# add the current directory to the module path if it's not there yet:
module_path = os.path.dirname(__file__)
if module_path not in sys.path:
    sys.path.append(module_path)

import plugin_helpers # Sublime Text plugin helpers
import zftplib # z/OS FTP library
import endevor_api # Endevor API library

class EndevorPlugin:
    instance = None
    
    @staticmethod
    def get():
        # singleton:
        if not EndevorPlugin.instance:
            EndevorPlugin.instance = EndevorPlugin()

        return EndevorPlugin.instance

    def __init__(self):
        # set up logging:
        self.logger = logging.getLogger('endevor_plugin')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter("%(name)s[%(asctime)s]: %(message)s", "%H:%M:%S"))
            self.logger.addHandler(stream_handler)

        self.load_configuration()
        self.load_session()
        self.repository_path = os.path.join(os.path.dirname(__file__), 'repository')
        self.initialize(self.settings)

    def initialize(self, settings):
        # set up FTP connection:
        zftp = zftplib.ZFTP(settings['ftp']['hostname'], settings['username'], self.password, logging.INFO)
        
        # set up Endevor FTP interface:
        jcl_variables = {}
        jcl_variables['job_card'] = settings['ftp']['job_card']
        jcl_variables['load_library'] = settings['ftp']['load_library']
        jcl_variables['script_library'] = settings['ftp']['script_library']
        self.endevor_ftp = endevor_api.EndevorFTP(zftp, jcl_variables, logging.INFO)

        # set up Endevor HTTP interface:
        base_urls = settings['http']['urls']
        data_source = settings['http']['data_source']
        self.endevor_http = endevor_api.EndevorHTTP('rest', base_urls, data_source, settings['username'], self.password, logging.INFO)

    def load_configuration(self):
        # load and read plugin settings:
        settings_path = os.path.join(os.path.dirname(__file__), 'endevor.json')
        # parse JSON:
        settings = json.loads(open(settings_path).read())
        self.settings = settings
        self.password = settings['password'] if 'password' in settings else None
        self.initialize(self.settings)

    def load_session(self):
        # load and read plugin session:
        self.session_path = os.path.join(os.path.dirname(__file__), 'endevor_session.json')
        # parse JSON:
        if os.path.isfile(self.session_path):
            self.session = json.loads(open(self.session_path).read())
        else:
            self.session = {}

    def save_session(self):
        # write plugin session to the file:
        open(self.session_path, 'w').write(json.dumps(self.session, indent=4))

    def status_message(self, message):
        self.logger.info(message)
        sublime.status_message(message)

    def error_message(self, message):
        sublime.error_message(message)

    def ensure_password(handler):
        def wrapper(*args, **kwargs):
            self = EndevorPlugin.get()

            # ensure password was specified:
            if self.endevor_ftp._zftp.password:
                return handler(*args, **kwargs)
            else:
                self._on_password_ready = {'handler': handler, 'parameters': [args, kwargs]}
                sublime.active_window().show_input_panel("Password:", '', self._on_password_input, None, None)

        return wrapper

    def _on_password_input(self, password):
        self.endevor_ftp._zftp.password = password
        self.endevor_http.password = password
        parameters = self._on_password_ready['parameters']
        self._on_password_ready['handler'](*parameters[0], **parameters[1])

class EndevorReloadConfiguration(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin = EndevorPlugin.get()
        plugin.load_configuration()
        plugin.status_message('Endevor configuration has been reloaded')

class EndevorCheckConnection(sublime_plugin.TextCommand):
    def run(self, edit):
        sublime.set_timeout_async(self.check_connection, 0)

    def check_connection(self):
        plugin = EndevorPlugin.get()
        urls = plugin.settings['http']['urls']
        for url in urls:
            print('checking ' + url)
            request = urllib.request.Request(url + '/EndevorService')
            request.add_header('Accept-Encoding', 'gzip')
            try:
                response = urllib.request.urlopen(request)
            except Exception as error:
                print(str(error))
            print('OK')

class EndevorExecuteSclCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        plugin = EndevorPlugin.get()
        scl = plugin.session['scl'] if 'scl' in plugin.session else ''
        sublime.active_window().show_input_panel("SCL:", scl, self.on_scl_input, None, None)

    def on_scl_input(self, scl):
        plugin = EndevorPlugin.get()
        plugin.session['scl'] = scl
        plugin.save_session()
        self.scl = scl
        plugin.status_message('Executing SCL')
        sublime.set_timeout_async(self.execute_scl, 0)

    def execute_scl(self):
        plugin = EndevorPlugin.get()
        try:
            response = plugin.endevor_http.submit_scl(self.scl)

            output = ['{}:\n{}'.format(name, content) for name, content in response['attachments'].items()]
            
            window = sublime.active_window()
            window.new_file()
            window.run_command('plugin_helper_insert_string_in_active_view', {'point': 0, 'string': '\n'.join(output)})
        except Exception as error:
            plugin.error_message(str(error))
            raise

class EndevorRetrieveCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        plugin = EndevorPlugin.get()

        endevor_path = "<environment>/<system>/<subsystem>/<element>[/<type>[/<stage>]]" # path pattern

        file_name = sublime.active_window().active_view().file_name()
        if file_name and file_name.startswith(plugin.repository_path):
            file_name_parts = file_name.split('\\')

            element_name = file_name_parts[-1].split('.')[0]
            element_type = file_name_parts[-2]
            stage = file_name_parts[-3]
            subsystem = file_name_parts[-4]
            system = file_name_parts[-5]
            environment = file_name_parts[-6]

            endevor_path = [environment, system, subsystem, element_name, element_type]
            endevor_path = '/'.join(endevor_path)

        elif 'endevor_path' in plugin.session:
            endevor_path = plugin.session['endevor_path']

        sublime.active_window().show_input_panel("Endevor path:", endevor_path, self.on_endevor_path_input, None, None)

    def on_endevor_path_input(self, endevor_path):
        plugin = EndevorPlugin.get()
        plugin.session['endevor_path'] = endevor_path
        plugin.save_session() # update session file

        self.endevor_path = endevor_path
        sublime.status_message('Retrieving element ' + endevor_path)
        sublime.set_timeout_async(self.retrieve_element, 0)

    def retrieve_element(self):
        plugin = EndevorPlugin.get()
        endevor_path = self.endevor_path.split('/')
        try:
            endevor_response = plugin.endevor_http.retrieve_element(path=endevor_path)
        except Exception as error:
            plugin.error_message(str(error))
            raise

        if len(endevor_path) < 5:
            endevor_path.append(endevor_response['element_type'])
        if len(endevor_path) < 6:
            endevor_path.append(endevor_response['stage'])

        element_name = endevor_path[3]
        element_type = endevor_path[4]
        stage = endevor_path[5]

        endevor_path[4] = stage
        endevor_path[5] = element_type

        del endevor_path[3]

        file_path = os.path.join(plugin.repository_path, *endevor_path)
        os.makedirs(file_path, exist_ok=True) # create element folders

        file_path = os.path.join(file_path, '%s.%s' % (element_name, element_type))
        element_content = endevor_response['content']
        # remove sequence numbers:
        element_content = re.sub(r'^(.{72})\d{8}$', r'\1', element_content, flags=re.M)
        # remove trailing blanks:
        element_content = re.sub(r' +$', '', element_content, flags=re.M)
        open(file_path, 'w', encoding='iso-8859-1').write(element_content) # write element content

        sublime.active_window().open_file(file_path) # open the element

class EndevorUpdateCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        sublime.status_message('Updating element')
        sublime.set_timeout_async(self.update_element, 0)

    def update_element(self):
        plugin = EndevorPlugin.get()
        file_name = sublime.active_window().active_view().file_name()
        if not file_name.startswith(plugin.repository_path):
            plugin.error_message('The file is not an Endevor element')
            return

        file_name_parts = file_name.split('\\')

        element_name = file_name_parts[-1].split('.')[0]
        element_type = file_name_parts[-2]
        stage = file_name_parts[-3]
        subsystem = file_name_parts[-4]
        system = file_name_parts[-5]
        environment = file_name_parts[-6]

        try:
            path = [environment, system, subsystem, element_name, element_type, stage]
            endevor_response = plugin.endevor_http.update_element(path=path, element_content=open(file_name).read())
        except Exception as error:
            # "NO SOURCE CHANGES DETECTED" OR "SOURCE CHANGE LEVEL IS OUT-OF-SYNC"
            if not re.search(r'SMGR122W|SCHK112C', str(error)):
                plugin.error_message(str(error))
                raise

        endevor_path = '/'.join([environment, system, subsystem, element_name, element_type])
        plugin.status_message('Update of element {} done successfully'.format(endevor_path))

class EndevorPrintListingCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        EndevorPlugin.get().status_message('Retrieving element listing')
        sublime.set_timeout_async(self.print_listing, 0)

    def print_listing(self):
        plugin = EndevorPlugin.get()
        file_name = sublime.active_window().active_view().file_name()
        if not file_name.startswith(plugin.repository_path):
            plugin.error_message('The file is not an Endevor element')
            return

        file_name_parts = file_name.split('\\')

        element_name = file_name_parts[-1].split('.')[0]
        element_type = file_name_parts[-2]
        stage = file_name_parts[-3]
        subsystem = file_name_parts[-4]
        system = file_name_parts[-5]
        environment = file_name_parts[-6]

        if element_type == 'LISTLIB':
            element_type = 'ASMPGM'
        elif element_type == 'LNKINC':
            element_type = 'LNK'
        
        if element_type == 'LNKINC':
            folder = element_type
            extension = element_type
        else:
            folder = 'LISTLIB'
            extension = 'LISTLIB'

        try:
            path = [environment, system, subsystem, element_name, element_type, stage]
            endevor_response = plugin.endevor_http.print_element(path=path)
        except Exception as error:
            plugin.error_message(str(error))
            raise

        file_path = os.path.join(plugin.repository_path, environment, system, subsystem, stage, folder)
        os.makedirs(file_path, exist_ok=True) # create element folders

        file_path = os.path.join(file_path, '%s.%s' % (element_name, extension))
        open(file_path, 'w', errors='ignore').write(endevor_response['content']) # write element listing

        sublime.active_window().open_file(file_path) # open the listing

class EndevorRefreshListingCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        EndevorPlugin.get().status_message('Refreshing element listing')
        sublime.set_timeout_async(self.refresh_listing, 0)

    def refresh_listing(self):
        plugin = EndevorPlugin.get()
        file_name = sublime.active_window().active_view().file_name()
        if not file_name.startswith(plugin.repository_path):
            plugin.error_message('The file is not an Endevor listing')
            return

        file_name_parts = file_name.split('\\')

        element_name = file_name_parts[-1].split('.')[0]
        element_type = 'ASMPGM'
        stage = file_name_parts[-3]
        subsystem = file_name_parts[-4]
        system = file_name_parts[-5]
        environment = file_name_parts[-6]

        if element_type == 'LNKINC':
            element_type = 'LNK'
            folder = element_type
            extension = element_type
        else:
            folder = 'LISTLIB'
            extension = 'LISTLIB'

        try:
            path = [environment, system, subsystem, element_name, element_type, stage]
            endevor_response = plugin.endevor_http.print_element(path=path)
        except Exception as error:
            plugin.error_message(str(error))
            raise

        file_path = os.path.join(plugin.repository_path, environment, system, subsystem, stage, folder)
        os.makedirs(file_path, exist_ok=True) # create element folders

        file_path = os.path.join(file_path, '%s.%s' % (element_name, extension))
        open(file_path, 'w', errors='ignore').write(endevor_response['content']) # write element listing

        sublime.active_window().open_file(file_path) # open the listing

class EndevorValidateSandboxCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        plugin = EndevorPlugin.get()
        endevor_path = "<environment>/<system>/<subsystem>" # path pattern
        if 'sandbox_path' in plugin.session:
            endevor_path = plugin.session['sandbox_path']
        sublime.active_window().show_input_panel("Endevor path:", endevor_path, self.on_endevor_path_input, None, None)

    def on_endevor_path_input(self, endevor_path):
        plugin = EndevorPlugin.get()
        plugin.session['sandbox_path'] = endevor_path
        plugin.save_session() # update session file

        self.endevor_path = endevor_path
        plugin.status_message('Validating sandbox ' + endevor_path)
        sublime.set_timeout_async(self.validate_sandbox, 0)

    def validate_sandbox(self):
        plugin = EndevorPlugin.get()
        environment, system, subsystem = self.endevor_path.split('/')
        try:
            plugin.endevor_ftp.validate_sandbox(path=[environment, system, subsystem])
        except Exception as error:
            plugin.error_message(str(error))
            return

class EndevorSmartGenerateCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        plugin = EndevorPlugin.get()
        endevor_path = "<environment>/<system>/<subsystem>" # path pattern
        if 'sandbox_path' in plugin.session:
            endevor_path = plugin.session['sandbox_path']
        sublime.active_window().show_input_panel("Endevor path:", endevor_path, self.on_endevor_path_input, None, None)

    def on_endevor_path_input(self, endevor_path):
        plugin = EndevorPlugin.get()
        plugin.session['sandbox_path'] = endevor_path
        plugin.save_session() # update session file
        
        self.endevor_path = endevor_path
        plugin.status_message('Performing SMARTGEN for sandbox ' + endevor_path)
        sublime.set_timeout_async(self.smart_generate, 0)

    def smart_generate(self):
        plugin = EndevorPlugin.get()
        try:
            plugin.endevor_ftp.smart_generate(path=self.endevor_path)
        except Exception as error:
            plugin.error_message(str(error))
            raise

class EndevorCompareElementsCommand(sublime_plugin.TextCommand):
    @EndevorPlugin.ensure_password
    def run(self, edit):
        plugin = EndevorPlugin.get()
        if 'endevor_path' in plugin.session:
            right_endevor_path = plugin.session['endevor_path']
        else:
            right_endevor_path = "<environment>/<system>/<subsystem>/<element>/<type>/<stage>" # path pattern

        sublime.active_window().show_input_panel("Right endevor path:", right_endevor_path, self.on_right_endevor_path_input, None, None)

    def on_right_endevor_path_input(self, right_endevor_path):
        plugin = EndevorPlugin.get()
        plugin.session['endevor_path'] = right_endevor_path
        plugin.save_session() # update session file
        self.right_endevor_path = right_endevor_path

        environment, system, subsystem, element_name, element_type, stage = right_endevor_path.split('/')
        if environment == 'RWRK':
            environment = 'WRK'
        elif environment == 'WRK':
            environment = 'DEV'
        elif environment == 'DEV':
            environment = 'PRD'
            subsystem = 'GA'
            stage = '2'
        left_endevor_path = '/'.join([environment, system, subsystem, element_name, element_type, stage])

        sublime.active_window().show_input_panel("Left endevor path:", left_endevor_path, self.on_left_endevor_path_input, None, None)

    def on_left_endevor_path_input(self, left_endevor_path):
        self.left_endevor_path = left_endevor_path
        EndevorPlugin.get().status_message('Comparing elements')
        sublime.set_timeout_async(self.compare_elements, 0)

    def compare_elements(self):
        left_path = self.left_endevor_path.split('/')
        right_path = self.right_endevor_path.split('/')
        EndevorPlugin.get().endevor_http.compare_elements(left_path, right_path, 'WinMergeU')

class EndevorFindLoadModulesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        EndevorPlugin.get().status_message('Finding load modules')
        sublime.set_timeout_async(self.find_load_modules, 0)

    def find_load_modules(self):
        # find which load modules include the given object module:
        plugin = EndevorPlugin.get()
        file_name = sublime.active_window().active_view().file_name()
        element_name = file_name.split('\\')[-1].split('.')[0]
        load_modules_path = os.path.join(plugin.repository_path, plugin.settings['load_modules_path'])

        load_modules = []
        for load_module_file in os.listdir(load_modules_path):
            if element_name in open(os.path.join(load_modules_path, load_module_file), errors='ignore').read():
                load_modules.append(load_module_file.split('.')[0])

        window = sublime.active_window()
        window.new_file()
        load_modules = '\n'.join(load_modules)
        window.run_command('plugin_helper_insert_string_in_active_view', {'point': 0, 'string': load_modules})
