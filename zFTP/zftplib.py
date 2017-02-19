# -*- coding: utf-8 -*-

import io
import re
import ftplib

class zFTP(ftplib.FTP):
    def __init__(self, host=None, username=None, password=None):
        ftplib.FTP.__init__(self)

        self.host        = host
        self.username    = username
        self.password    = password

        self._authorized = False
        self._mode       = 'SEQ'

    def _connect_and_login(self):
        self.connect(self.host)
        self.login  (self.username, self.password)
        self._authorized = True

        self.voidcmd('SITE JESJOBNAME=*')

    def _reconnect_on_error(self, handler, args, kwargs):
        if not self._authorized:
            self._connect_and_login()

        retry = True
        while True:
            try:
                return handler(*args, **kwargs)
            except EOFError as error:
                if not retry:
                    raise
                self._connect_and_login()
                retry = False

    def _switch_mode(self, mode):
        if self._mode != mode:
            self.voidcmd('SITE FILE=%s' % mode)
            self._mode = mode

    def _download_dataset(self, dataset_name):
        self._switch_mode('SEQ')
        result = []
        self.retrlines("RETR '%s'" % dataset_name, lambda line: result.append(line.rstrip()))
        return '\n'.join(result)

    def download_dataset(self, *args, **kwargs):
        return self._reconnect_on_error(self._download_dataset, args, kwargs)

    def _upload_dataset(self, dataset_name, file):
        self._switch_mode('SEQ')
        return self.storlines("STOR '%s'" % dataset_name, file)

    def upload_dataset(self, *args, **kwargs):
        return self._reconnect_on_error(self._upload_dataset, args, kwargs)

    def _submit_jcl(self, jcl):
        self._switch_mode('JES')
        stream = io.BytesIO(jcl.encode('utf-8'))
        reply  = self.storlines("STOR JOB", stream)
        match  = re.search(r'It is known to JES as (.+)', reply)
        job_id = match.group(1)
        return job_id

    def submit_jcl(self, *args, **kwargs):
        return self._reconnect_on_error(self._submit_jcl, args, kwargs)

    def _retrieve_job_spool(self, job_id, dd_id=None):
        self._switch_mode('JES')

        spool_target = job_id
        if dd_id:
            spool_target += '.' + dd_id

        job_spool    = []    
        self.retrlines("RETR " + spool_target, lambda line: job_spool.append(line.rstrip()))
        return '\n'.join(job_spool)

    def retrieve_job_spool(self, *args, **kwargs):
        return self._reconnect_on_error(self._retrieve_job_spool, args, kwargs)

    def _purge_job(self, job_id):
        self._switch_mode('JES')
        result = self.delete(job_id)
        return result

    def purge_job(self, *args, **kwargs):
        return self._reconnect_on_error(self._purge_job, args, kwargs)
