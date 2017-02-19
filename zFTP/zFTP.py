# -*- coding: utf-8 -*-

# standard modules:
import os
import base64
import sys
import json
import ftplib
import re

# sublime modules:
import sublime
import sublime_plugin

sys.path.append(os.path.dirname(__file__))
import zftplib

class Plugin:
    def __init__(self):
        plugin_path        = os.path.dirname(__file__)

        self.settings_path = os.path.join(plugin_path, 'zFTP.json') # load plugin settings
        self.datasets_path = os.path.join(plugin_path, 'data_sets')
        self.spool_path    = os.path.join(plugin_path, 'spool')

        settings           = json.loads(open(self.settings_path).read()) # parse JSON
        self.settings      = settings

        password           = settings['password'] if 'password' in settings else None
        self.zftp          = zftplib.zFTP(settings['host'], settings['username'], password)

    def save_settings(self):
        open(self.settings_path, 'w').write(json.dumps(self.settings, indent=4, sort_keys=True)) # update settings file

    def status_message(self, *args):
        sublime.status_message(*args)
        print                 ('zFTP: ', *args)

    def ensure_password(self, on_ready):
        if self.zftp.password:
            on_ready()
        else:
            self._on_ready = on_ready
            sublime.active_window().show_input_panel("Password:", '', self._on_password_input, None, None)

    def _on_password_input(self, password):
        self.zftp.password = password
        self._on_ready()

plugin = Plugin()

class ZftpDownloadDatasetCommand(sublime_plugin.TextCommand):
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
        plugin.status_message    ('Downloading data set ' + dataset_name)
        sublime.set_timeout_async(self.download_dataset, 0)

    def download_dataset(self):
        try:
            dataset_content = plugin.zftp.download_dataset(self.dataset_name)
        except Exception as error:
            sublime.error_message(str(error))
            return

        dataset_name = self.dataset_name
        match = re.match(r'(.*?)\((.*?)\)', dataset_name)
        if match:
            is_pds       = True
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
        open(file_path, 'w').write(dataset_content) # write data set content

        sublime.active_window().open_file(file_path) # open the data set

class ZftpUploadDatasetCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self, edit):
        plugin.status_message    ('Uploading data set')
        sublime.set_timeout_async(self.upload_dataset, 0)

    def upload_dataset(self):
        file_path = self.view.file_name()[len(plugin.datasets_path) + 1:]
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
            plugin.zftp.upload_dataset(dataset_name, open(self.view.file_name(), 'rb'))
        except Exception as error:
            sublime.error_message(str(error))
            return

        plugin.status_message('Upload done successfully')

class ZftpSubmitJobCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self, edit):
        plugin.status_message    ('Submitting job')
        sublime.set_timeout_async(self.submit_job, 0)

    def submit_job(self):
        try:
            job_id = plugin.zftp.submit_jcl(open(self.view.file_name(), 'r').read())
        except Exception as error:
            sublime.error_message(str(error))
            return
        plugin.status_message("The job '%s' submitted" % job_id)

class ZftpSubmitJobAndPrintSpoolCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self, edit):
        plugin.status_message    ('Submitting job')
        sublime.set_timeout_async(self.submit_job_and_print_spool, 0)

    def submit_job_and_print_spool(self):
        try:
            job_id = plugin.zftp.submit_jcl(open(self.view.file_name(), 'r').read())
        except Exception as error:
            sublime.error_message(str(error))
            return
        plugin.status_message("The job '%s' submitted. Retrieving the spool" % job_id)
        spool = plugin.zftp.retrieve_job_spool(job_id)

        os.makedirs(plugin.spool_path, exist_ok=True)

        file_path = os.path.join(plugin.spool_path, job_id + '.jesp')
        open(file_path, 'w').write(spool)

        sublime.active_window().open_file(file_path)
