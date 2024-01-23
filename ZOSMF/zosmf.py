# -*- coding: utf-8 -*-

# standard modules:
import os
import base64
import sys
import json
import ftplib
import re
import logging

import jinja2 # Jinja2 template engine

# sublime modules:
import sublime
import sublime_plugin

# add the current directory to the module path if it's not there yet:
module_path = os.path.dirname(__file__)
if module_path not in sys.path:
    sys.path.append(module_path)

import zosmf_api

class ZOSMFPlugin:
    def __init__(self):
        plugin_path = os.path.dirname(__file__)

        self.settings_path = os.path.join(plugin_path, 'zosmf.json') # load plugin settings
        self.datasets_path = os.path.join(plugin_path, 'data_sets')
        self.spool_path = os.path.join(plugin_path, 'spool')

        settings = json.loads(open(self.settings_path).read()) # parse JSON
        self.settings = settings

        password = settings['password'] if 'password' in settings else None
        self.zosmf = zosmf_api.ZOSMF(url=settings['url'], username=settings['username'], password=password)

    def save_settings(self):
        open(self.settings_path, 'w').write(json.dumps(self.settings, indent=4, sort_keys=True)) # update settings file

    def status_message(self, *args):
        sublime.status_message(*args)
        print('z/OSMF:', *args)

    def ensure_password(self, on_ready):
        if self.zosmf.password:
            on_ready()
        else:
            self._on_ready = on_ready
            sublime.active_window().show_input_panel("Password:", '', self._on_password_input, None, None)

    def _on_password_input(self, password):
        self.zosmf.password = password
        self._on_ready()

plugin = ZOSMFPlugin()

class ZosmfSubmitJobCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Submitting job')
        sublime.set_timeout_async(self.submit_job, 0)

    def submit_job(self):
        try:
            jcl = open(self.view.file_name(), 'r').read()

            if not re.match(r'//\S+ +JOB', jcl):
                raise Exception('Not a valid JCL job')
            
            job = plugin.zosmf.submit_job(jcl)

        except Exception as error:
            sublime.error_message(str(error))
            raise
        
        plugin.status_message("{} submitted".format(job['jobid']))

class ZosmfSubmitTemplatedJobCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Submitting job')
        sublime.set_timeout_async(self.submit_job, 0)

    def submit_job(self):
        try:
            file_content = open(self.view.file_name(), 'r').read()

            loader = jinja2.FileSystemLoader(os.path.dirname(self.view.file_name()))
            template = jinja2.Environment(loader=loader, lstrip_blocks=True, trim_blocks=True).from_string(file_content)
            jcl = template.render({})

            if not re.match(r'//\S+ +JOB', jcl):
                raise Exception('Not a valid JCL job')
            
            job = plugin.zosmf.submit_job(jcl)

        except Exception as error:
            sublime.error_message(str(error))
            raise
        
        plugin.status_message("{} submitted".format(job['jobid']))

class ZosmfPreviewTemplatedJobCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        try:
            file_content = open(self.view.file_name(), 'r').read()
            loader = jinja2.FileSystemLoader(os.path.dirname(self.view.file_name()))
            template = jinja2.Environment(loader=loader, lstrip_blocks=True, trim_blocks=True).from_string(file_content)
            jcl = template.render({})
            window = sublime.active_window()
            window.new_file()
            window.run_command('plugin_helper_insert_string_in_active_view', {'point': 0, 'string': jcl})

        except Exception as error:
            sublime.error_message(str(error))
            raise

class ZosmfDownloadDatasetCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        dataset_name = ''
        if 'dataset_name' in plugin.settings:
            dataset_name = plugin.settings['dataset_name']

        sublime.active_window().show_input_panel("Data set name:", dataset_name, self.on_dataset_name_input, None, None)

    def on_dataset_name_input(self, dataset_name):
        plugin.settings['dataset_name'] = dataset_name
        plugin.save_settings()

        self.dataset_name = dataset_name
        plugin.status_message('Downloading data set ' + dataset_name)
        sublime.set_timeout_async(self.download_dataset, 0)

    def download_dataset(self):
        try:
            dataset_content = plugin.zosmf.download_dataset(self.dataset_name)
        except Exception as error:
            sublime.error_message(str(error))
            raise

        dataset_name = self.dataset_name
        match = re.match(r'(.*?)\((.*?)\)', dataset_name)
        if match:
            is_pds = True
            dataset_name = match.group(1)
            member_name  = match.group(2)
        else:
            is_pds = False

        dataset_name_parts = dataset_name.split('.')
        if is_pds:
            file_name = '%s.%s' % (member_name, dataset_name_parts[-1])
        else:
            file_name = dataset_name_parts.pop()

        file_path = os.path.join(plugin.datasets_path, *dataset_name_parts)
        os.makedirs(file_path, exist_ok=True) # create data set folders

        file_path = os.path.join(file_path, file_name)
        open(file_path, 'w', errors='ignore').write(dataset_content) # write data set content

        sublime.active_window().open_file(file_path) # open the data set

class ZosmfUploadDatasetCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Uploading data set')
        sublime.set_timeout_async(self.upload_dataset, 0)

    def upload_dataset(self):
        file_name = self.view.file_name()
        if not file_name.startswith(plugin.datasets_path):
            sublime.error_message('The file is not a data set')
            return

        file_path = file_name[len(plugin.datasets_path) + 1:]
        file_path_parts = file_path.split('\\')
        file_name = file_path_parts[-1]

        if '.' in file_name:
            is_pds = True
            member_name = file_name.split('.')[0]
            file_path_parts.pop()
        else:
            is_pds = False
        
        dataset_name = '.'.join(file_path_parts)

        if is_pds:
            dataset_name = '%s(%s)' % (dataset_name, member_name)

        try:
            plugin.zosmf.upload_dataset(dataset_name, open(self.view.file_name(), 'r').read())
        except Exception as error:
            raise
            sublime.error_message(str(error))
            return

        plugin.status_message('Upload done successfully')

class ZosmfPrintJobSpoolCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        window = sublime.active_window()
        window.show_input_panel("Job spool target:", '<job id>[.<DD name>]', self.on_spool_target, None, None)

    def on_spool_target(self, spool_target):
        self.spool_target = spool_target
        plugin.status_message("Retrieving '%s' job spool" % spool_target)
        sublime.set_timeout_async(self.print_spool, 0)

    def print_spool(self):
        try:
            match = re.match(r'([^.]+)(?:\.(.*))?', self.spool_target)
            job_id = match.group(1)
            dd_name = match.group(2)
            job_spool = plugin.zosmf.retrieve_job_spool(job_id, dd_name=dd_name)
        except Exception as error:
            sublime.error_message(str(error))
            raise
        
        os.makedirs(plugin.spool_path, exist_ok=True)
        file_path = os.path.join(plugin.spool_path, self.spool_target + '.txt')
        open(file_path, 'w', errors='ignore').write(job_spool)

        sublime.active_window().open_file(file_path)
