# -*- coding: utf-8 -*-

# standard modules:
import logging
import re
from pprint import pprint

import requests

class ZOSMF:
    def __init__(self, **kwargs):
        if 'logging_level' not in kwargs:
            kwargs['logging_level'] = logging.INFO

        self.url = kwargs['url']
        self.username = kwargs['username']
        self.password = kwargs['password']

        if 'logger' in kwargs:
            self.logger = kwargs['logger']
        else:
            self.logger = logging.getLogger('zosmf')
            self.logger.setLevel(logging.WARNING)
            if not self.logger.handlers:
                stream_handler = logging.StreamHandler()
                stream_handler.setFormatter(logging.Formatter("%(message)s"))
                self.logger.addHandler(stream_handler)

    def request(self, method, path, **kwargs):
        headers = {'X-CSRF-ZOSMF-HEADER': ''}

        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers

        response = requests.request(method, self.url + path, auth=(self.username, self.password), **kwargs)
        if response.headers['Content-Type'] == 'application/json':
            response_json = response.json()
            if 'rc' in response_json and int(response_json['rc']):
                pprint(response_json)
                raise Exception(response_json['message'])

        return response

    def execute_system_command(self, command):
        response = self.request('PUT', '/zosmf/restconsoles/consoles/defcn', json={'cmd': command})
        return response.json()['cmd-response'].replace('\r', '\n')

    def list_jobs(self, **kwargs):
        return self.request('GET', '/zosmf/restjobs/jobs', params=kwargs).json()

    def list_spool_files(self, job_id, job_name=None):
        if not job_name:
            self.logger.info('searching for {} job'.format(job_id))
            job = self.list_jobs(jobid=job_id)
            job_name = job[0]['jobname']
        return self.request('GET', '/zosmf/restjobs/jobs/{}/{}/files'.format(job_name, job_id)).json()

    def retrieve_job_spool(self, job_id, job_name=None, spool_id=None, dd_name=None):
        if not job_name:
            self.logger.info('searching for {} job'.format(job_id))
            jobs = self.list_jobs(jobid=job_id)
            if not jobs:
                raise Exception('job {} not found'.format(job_id))
            job_name = jobs[0]['jobname']

        if spool_id:
            self.logger.info('retrieving {} spool'.format(job_id))
            url = '/zosmf/restjobs/jobs/{}/{}/files/{}/records'.format(job_name, job_id, spool_id)
            return self.request('GET', url).content.decode('utf-8', errors='ignore')

        spool_files = self.list_spool_files(job_id, job_name=job_name)
        
        if dd_name is not None:
            for spool_file in spool_files:
                if spool_file['ddname'] == dd_name:
                    spool_files = [spool_file]
                    break
        
        job_spool = ''
        for spool_file in spool_files:
            job_spool += self.retrieve_job_spool(job_id, job_name=job_name, spool_id=spool_file['id'])
        return job_spool

    def find_unique_jobname(self, prefix):
        jobs = self.list_jobs(owner='*', prefix='{}*'.format(prefix))
        job_names = [job['jobname'] for job in jobs if job['status'] in ('ACTIVE', 'INPUT')]
        job_name = prefix
        index = 2
        while True:
            if job_name not in job_names:
                break
            job_name = prefix + str(index)
            index += 1
        return job_name

    def submit_job(self, jcl, unique_jobname_prefix=None):
        if unique_jobname_prefix is not None:
            if unique_jobname_prefix is True:
                unique_jobname_prefix = self.username[:5]
            jobname = self.find_unique_jobname(unique_jobname_prefix)
            jcl = re.sub(r'^//\S* +JOB ', '//{:8} JOB '.format(jobname), jcl)

        headers = {'Content-Type': 'text/plain'}

        jobname = re.search(r'^//(\S*) +JOB ', jcl).group(1)
        self.logger.info('submitting job {}'.format(jobname))

        return self.request('PUT', '/zosmf/restjobs/jobs', headers=headers, data=jcl.encode()).json()

    def execute_job(self, jcl, spool):
        with Spinner() as spinner:
            spinner.message = 'submitting job'
            job = self.submit_job(jcl, unique_jobname_prefix=True)

            job_id = '{}/{}'.format(job["jobname"], job["jobid"])
            spinner.message = 'waiting for job to finish'
            job_status = self.wait_for_job_end(job_id)

            spinner.message = 'retrieving job spool'

            if not job_status['retcode'].startswith('CC'):
                spool = []
                spool.append(self.retrieve_job_spool(job_id, dd='JESMSGLG').strip())
                spool.append(self.retrieve_job_spool(job_id, dd='JESJCL').strip())
                spool.append(self.retrieve_job_spool(job_id, dd='JESYSMSG').strip())
                self.purge_job(job_id)
                return '\n'.join(spool)
                    
            spool = self.retrieve_job_spool(job_id, **spool).strip()

            match = re.match(r'CC +(\d+)', job_status['retcode'])
            if match and int(match.group(1)) <= 4:
                spinner.message = 'purging job'
                self.purge_job(job_id)

            print('\r', end='')

            return spool

    def get_job_status(self, job_id, step_data=None):
        step_data = 'Y' if step_data == True else 'N'
        return self.request('GET', '/zosmf/restjobs/jobs/{}?step-data={}'.format(job_id, step_data)).json()

    def wait_for_job_start(self, job_id):
        jobname = job_id.split('/')[1]
        self.logger.info('waiting for {} to start'.format(jobname))
        while True:
            job_status = self.get_job_status(job_id)
            if job_status['status'] != 'INPUT':
                return job_status
            time.sleep(0.5)

    def wait_for_job_end(self, job_id):
        jobname = job_id.split('/')[1]
        self.logger.info('waiting for {} to finish'.format(jobname))
        while True:
            job_status = self.get_job_status(job_id)
            if job_status['status'] == 'OUTPUT':
                return job_status
            time.sleep(0.5)

    def purge_job(self, job_id):
        jobname = job_id.split('/')[1]
        self.logger.info('purging {} spool'.format(jobname))
        return self.request('DELETE', '/zosmf/restjobs/jobs/{}'.format(job_id)).json()

    def download_dataset(self, dataset_name):
        self.logger.info('downloading data set {}'.format(dataset_name))

        dataset_content = self.request('GET', requests.utils.quote('/zosmf/restfiles/ds/{}'.format(dataset_name))).content.decode()

        dataset_list = self.list_data_sets(dataset_name.split('(')[0])
        recfm = dataset_list['items'][0]['recfm']
        if 'A' in recfm:
            dataset_content = '\n'.join([line[1:] for line in dataset_content.split('\n')])
        
        return dataset_content

    def upload_dataset(self, dataset_name, dataset_content):
        self.logger.info('uploading data set {}'.format(dataset_name))

        recfm = self.list_data_sets(dataset_name.split('(')[0])['items'][0]['recfm']
        if 'A' in recfm:
            dataset_content = '\n'.join([line if line else ' ' for line in dataset_content.split('\n')])

        url = '/zosmf/restfiles/ds/{}'.format(dataset_name)
        headers = {'X-IBM-Data-Type': 'text'}
        return self.request('PUT', url, headers=headers, data=dataset_content)

    def download_file(self, filename):
        self.logger.info('downloading file {}'.format(filename))
        return self.request('GET', '/zosmf/restfiles/fs{}'.format(filename)).content

    def access_method_services(self, command):
        headers = {'Content-Type': 'application/json'}
        return self.request('PUT', '/zosmf/restfiles/ams', json={'input': [command]}).json()

    def list_data_sets(self, filter):
        headers = {'X-IBM-Attributes': 'base'}
        return self.request('GET', '/zosmf/restfiles/ds', params={'dslevel': filter}, headers=headers).json()
