# -*- coding: utf-8 -*-

import io
import re
import ftplib
import logging
import time
import ebcdic

class ZFTP(ftplib.FTP):
    def __init__(self, host=None, username=None, password=None, logging_level=logging.ERROR, proxy=None):
        ftplib.FTP.__init__(self)

        self.host = host
        self.username = username.upper()
        self.password = password
        self.proxy = proxy

        self._authorized = False
        self._mode = 'SEQ'

        self.logger = logging.getLogger('zftplib')
        self.logger.setLevel(logging_level)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter("%(name)s[%(asctime)s]: %(message)s", "%H:%M:%S"))
            self.logger.addHandler(stream_handler)

    def connect_and_login(self):
        self.logger.info('connecting to {}'.format(self.host))
        host = self.host
        port = 0
        match = re.match(r'(\S+?):(\d+)', host)
        if match:
            host = match.group(1)
            port = int(match.group(2))
        self.connect(host, port=port)

        self.logger.info("logging in as '{}'".format(self.username))
        self.login(self.username, self.password)
        self.logger.info('logged in')

        self._authorized = True
        self._mode = None

        self.voidcmd('SITE JESOWNER=* JESJOBNAME=*')

    def _reconnect_on_error(handler):
        def wrapper(self, *args, **kwargs):
            if not self._authorized:
                self.connect_and_login()

            retry = True
            while True:
                try:
                    return handler(self, *args, **kwargs)
                except (ConnectionResetError, ConnectionAbortedError, EOFError) as error:
                    if not retry:
                        raise
                    self.connect_and_login()
                    retry = False

        return wrapper

    def _switch_mode(self, mode):
        if self._mode != mode:
            self.voidcmd('SITE FILE=%s' % mode)
            self._mode = mode

    @_reconnect_on_error
    def download_dataset(self, dataset_name):
        self._switch_mode('SEQ')

        self.logger.info("downloading data set '%s'" % dataset_name)
        result = []
        self.retrlines("RETR '%s'" % dataset_name, lambda line: result.append(line.rstrip()))
        
        return '\n'.join(result)

    @_reconnect_on_error
    def upload_dataset(self, dataset_name, file):
        self._switch_mode('SEQ')

        self.logger.info("uploading data set '%s'" % dataset_name)
        return self.storlines("STOR '%s'" % dataset_name, file)

    @_reconnect_on_error
    def submit_jcl(self, jcl):
        self._switch_mode('JES')

        stream = io.BytesIO(jcl.encode('utf-8'))
        job_name = re.search(r'^\/\/(\S+)', jcl).group(1)

        self.logger.info("submitting job '%s'" % job_name)
        reply = self.storlines("STOR JOB", stream)

        match = re.search(r'It is known to JES as (.+)', reply)
        job_id = match.group(1)
        self.logger.info("job %s submitted" % job_id)

        return job_id

    @_reconnect_on_error
    def get_job_info(self, job_id):
        self._switch_mode('JES')

        job_info = {}

        response = []
        self.dir(job_id, lambda line: response.append(line.rstrip()))

        match = re.match(r'(\S+) +(\S+) +(\S+) +(\S+) +(\S+)(?: +(\S+))?', response[1])
        job_info['status'] = match.group(4)
        if match.group(6):
            match = re.match(r'RC=(\d+)', match.group(6))
            if match:
                job_info['rc'] = int(match.group(1))

        job_spool_list = {}
        for match in re.finditer(r'^ {9}(\d{3}) (.{8}) (.{8}) (.) (.{8}) (.{9})', '\n'.join(response[4:-1]), re.M):
            job_spool_list[int(match.group(1))] = match.group(5).rstrip()
        job_info['spool_list'] = job_spool_list
            
        return job_info

    @_reconnect_on_error
    def wait_for_job_start(self, job_id):
        self.logger.info('waiting for %s job to start' % job_id)
        while True:
            try:
                return self.get_job_info(job_id)
            except ftplib.error_perm as error:
                if re.search('^550 .*? not found', str(error)):
                    time.sleep(0.5)
                    continue
                else:
                    raise

    @_reconnect_on_error
    def wait_for_job_end(self, job_id):
        self.logger.info('waiting for %s job to finish' % job_id)
        while True:
            job_info = self.get_job_info(job_id)
            if job_info['status'] == 'OUTPUT':
                return job_info
            time.sleep(0.5)

    @_reconnect_on_error
    def retrieve_job_spool(self, job_id, dd=None, binary=None):
        if binary is None:
            binary = False

        self._switch_mode('JES')

        spool_target = job_id

        if dd is not None:
            dd = str(dd)
            if not re.search(r'^\d', dd):
                job_spool_list = self.get_job_info(job_id)['spool_list']
                dd_id = None
                for dd_key, dd_name in job_spool_list.items():
                    if dd_name == dd:
                        dd_id = dd_key
                        break
                if dd_id == None:
                    raise Exception('DD {} not found'.format(dd))
                dd = dd_id
            spool_target += '.' + str(dd)

        job_spool = []
        spool_bytes = bytearray()

        def add_chunk(chunk):
            nonlocal spool_bytes
            spool_bytes += chunk

        self.voidcmd('MODE B') # set block mode
        self.logger.info('retrieving %s job spool' % spool_target)
        while True:
            try:
                self.retrbinary("RETR " + spool_target, add_chunk)
            except ftplib.error_perm as error:
                if re.search('^550 (.*? not found)|(No spool files available for)', str(error)) and retry:
                    continue
                else:
                    raise
            break
        self.voidcmd('MODE S')
        
        index = 0
        while index < len(spool_bytes):
            record_size = int.from_bytes(spool_bytes[index + 1 : index + 3], 'big')
            index += 3
            record = spool_bytes[index : index + record_size]
            if not binary:
                record = record.decode('cp1047')
            job_spool.append(record)
            index += record_size

        if not binary:
            job_spool = '\n'.join(job_spool)
            
        return job_spool

    @_reconnect_on_error
    def purge_job(self, job_id):
        self.logger.info('purging job %s' % job_id)
        self._switch_mode('JES')
        result = self.delete(job_id)
        return result
