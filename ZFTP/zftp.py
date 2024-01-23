# -*- coding: utf-8 -*-

# standard modules:
import os
import base64
import sys
import json
import ftplib
import re
import logging

# sublime modules:
import sublime
import sublime_plugin

# add the current directory to the module path if it's not there yet:
module_path = os.path.dirname(__file__)
if module_path not in sys.path:
    sys.path.append(module_path)

import zftplib
import jcl_parser
import jinja2 # Jinja2 template engine

class ZFTPPlugin:
    def __init__(self):
        plugin_path = os.path.dirname(__file__)

        self.settings_path = os.path.join(plugin_path, 'zftp.json') # load plugin settings
        self.datasets_path = os.path.join(plugin_path, 'data_sets')
        self.spool_path = os.path.join(plugin_path, 'spool')

        settings = json.loads(open(self.settings_path).read()) # parse JSON
        self.settings = settings

        password = settings['password'] if 'password' in settings else None
        proxy = settings['proxy'] if 'proxy' in settings else None
        self.zftp = zftplib.ZFTP(settings['host'], settings['username'], password, logging.INFO, proxy=proxy)

    def save_settings(self):
        open(self.settings_path, 'w').write(json.dumps(self.settings, indent=4, sort_keys=True)) # update settings file

    def status_message(self, *args):
        sublime.status_message(*args)
        print('z/FTP:', *args)

    def ensure_password(self, on_ready):
        if self.zftp.password:
            on_ready()
        else:
            self._on_ready = on_ready
            sublime.active_window().show_input_panel("Password:", '', self._on_password_input, None, None)

    def _on_password_input(self, password):
        self.zftp.password = password
        self._on_ready()

    def submit_job(self, file_name, templated=False, print_spool=False):
        try:
            file_dirname = os.path.dirname(file_name)
            file_basename = os.path.basename(file_name)
            file_content = open(file_name, 'r').read()

            if not re.match(r'//\S+ +JOB', file_content):
                sublime.error_message('Not a valid JCL job')
                return

            if templated:
                loader = jinja2.FileSystemLoader(os.path.dirname(file_name))
                try:
                    template_data = open(os.path.join(file_dirname, file_basename.split('.')[0] + '.template.json')).read()
                    template_data = json.loads(template_data)
                except FileNotFoundError:
                    template_data = {}

                template = jinja2.Environment(loader=loader, lstrip_blocks=True).from_string(file_content)
                jcl = template.render(template_data)
            else:
                jcl = file_content
            
            job_id = self.zftp.submit_jcl(jcl)

        except Exception as error:
            sublime.error_message(str(error))
            raise
        
        self.status_message("The job '%s' submitted" % job_id)

        if print_spool:
            spool = self.zftp.retrieve_job_spool(job_id, retry=True)

            os.makedirs(self.spool_path, exist_ok=True)
            file_path = os.path.join(self.spool_path, job_id + '.jesp')
            open(file_path, 'w', errors='ignore').write(spool)

            sublime.active_window().open_file(file_path)

plugin = ZFTPPlugin()

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
        plugin.status_message('Downloading data set ' + dataset_name)
        sublime.set_timeout_async(self.download_dataset, 0)

    def download_dataset(self):
        try:
            dataset_content = plugin.zftp.download_dataset(self.dataset_name)
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

class ZftpUploadDatasetCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Uploading data set')
        sublime.set_timeout_async(self.upload_dataset, 0)

    def upload_dataset(self):
        file_name = self.view.file_name()
        if not file_name.startswith(plugin.datasets_path):
            sublime.error_message('The file is not a z/FTP data set')
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
            plugin.zftp.upload_dataset(dataset_name, open(self.view.file_name(), 'rb'))
        except Exception as error:
            sublime.error_message(str(error))
            return

        plugin.status_message('Upload done successfully')

class ZftpSubmitJobCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Submitting job')
        sublime.set_timeout_async(self.submit_job, 0)

    def submit_job(self):
        plugin.submit_job(self.view.file_name(), templated=False, print_spool=False)

class ZftpSubmitJobAndPrintSpoolCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Submitting job')
        sublime.set_timeout_async(self.submit_job_and_print_spool, 0)

    def submit_job_and_print_spool(self):
        plugin.submit_job(self.view.file_name(), templated=False, print_spool=True)

class ZftpSubmitTemplatedJobCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Submitting job')
        sublime.set_timeout_async(self.submit_job, 0)

    def submit_job(self):
        plugin.submit_job(self.view.file_name(), templated=True, print_spool=False)

class ZftpSubmitTemplatedJobAndPrintSpoolCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        plugin.status_message('Submitting job')
        sublime.set_timeout_async(self.submit_job_and_print_spool, 0)

    def submit_job_and_print_spool(self):
        plugin.submit_job(self.view.file_name(), templated=True, print_spool=True)

class ZftpPrintJobSpoolCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        sublime.active_window().show_input_panel("Job spool target:", '<job id>[.<DD name>]', self.on_spool_target, None, None)

    def on_spool_target(self, spool_target):
        self.spool_target = spool_target
        plugin.status_message("Retrieving '%s' job spool" % spool_target)
        sublime.set_timeout_async(self.print_spool, 0)

    def print_spool(self):
        try:
            match = re.match(r'([^.]+)(?:\.(.*))?', self.spool_target)
            job_id = match.group(1)
            dd_name = match.group(2)
            job_spool = plugin.zftp.retrieve_job_spool(job_id, dd_name)
        except Exception as error:
            sublime.error_message(str(error))
            raise
        
        os.makedirs(plugin.spool_path, exist_ok=True)
        file_path = os.path.join(plugin.spool_path, self.spool_target + '.txt')
        open(file_path, 'w', errors='ignore').write(job_spool)

        sublime.active_window().open_file(file_path)

class ZftpRestoreJobJcl(sublime_plugin.TextCommand):
    def run(self, edit):
        plugin.ensure_password(self.execute_command)

    def execute_command(self):
        sublime.active_window().show_input_panel("Job id:", '', self.on_job_id_input, None, None)

    def on_job_id_input(self, job_id):
        self.job_id = job_id
        plugin.status_message("Restoring '%s' job JCL " % job_id)
        sublime.set_timeout_async(self.print_spool, 0)

    def print_spool(self):
        try:
            job_jcl = plugin.zftp.retrieve_job_spool(self.job_id, 2)
        except Exception as error:
            sublime.error_message(str(error))
            raise

        file_path = os.path.join(plugin.spool_path, self.job_id + '.jcl')
        open(file_path, 'w', errors='ignore').write(jcl_parser.restore_jcl(job_jcl))

        sublime.active_window().open_file(file_path)
