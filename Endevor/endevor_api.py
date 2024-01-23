# -*- coding: utf-8 -*-

import os
import re # regular expressions
import logging
import datetime
import io
import base64 # Base64 encoding
import csv # comma-separated values
import urllib.request # HTTP requests
import urllib.error
import xml.etree.ElementTree # XML
import xml.dom.minidom
import collections
import gzip
from pprint import pprint

class EndevorSCL:
    def endevor_path(method):
        def wrapper(*args, **kwargs):
            if 'path' in kwargs:
                path = kwargs['path']

                if type(path) is str:
                    path = path.split('/')

                environment, system, subsystem = path[:3]

                if len(path) > 3:
                    element_name = path[3]
                else:
                    element_name = '*'
                if len(path) > 4:
                    element_type = path[4]
                else:
                    element_type = '*'
                if len(path) > 5:
                    stage = path[5]
                else:
                    stage = '*'
            
                path = collections.OrderedDict()
                path['environment'] = environment
                path['system'] = system
                path['subsystem'] = subsystem
                path['element_name'] = element_name
                path['element_type'] = element_type
                path['stage'] = stage
                kwargs['path'] = path

            return method(*args, **kwargs)

        return wrapper

    @staticmethod
    def list_element(path, to):
        scl_statement = []
        scl_statement.append("LIST")
        scl_statement.append("  ELEMENT      '{0}' THROUGH '{0}'".format(path['element_name']))
        scl_statement.append("  FROM")
        scl_statement.append("    ENV        '%s'" % path['environment'])
        scl_statement.append("    SYS        '%s'" % path['system'])
        scl_statement.append("    SUB        '%s'" % path['subsystem'])
        scl_statement.append("    TYPE       '%s'" % path['element_type'])
        scl_statement.append("    STAGE      '%s'" % path['stage'])

        if type(to) == str:
            scl_statement.append("  TO " + to)
        else:
            scl_statement.append("  TO")
            for name, value in to.items():
                scl_statement.append('    %-10s %s' % (name, value))

        scl_statement.append("  OPTIONS")
        scl_statement.append("    SEARCH")
        scl_statement.append(".")

        return '\n'.join(scl_statement)

    @staticmethod
    def retrieve_element(path, to):
        scl_statement = []
        scl_statement.append("RETRIEVE")
        scl_statement.append("  ELEMENT      '%s'" % path['element_name'])
        scl_statement.append("  FROM")
        scl_statement.append("    ENV        '%s'" % path['environment'])
        scl_statement.append("    SYS        '%s'" % path['system'])
        scl_statement.append("    SUB        '%s'" % path['subsystem'])
        scl_statement.append("    TYPE       '%s'" % path['element_type'])
        scl_statement.append("    STAGE      '%s'" % path['stage'])

        if type(to) == str:
            scl_statement.append("  TO " + to)
        else:
            scl_statement.append("  TO")
            for name, value in to.items():
                scl_statement.append('    %-10s %s' % (name, value))

        scl_statement.append("  OPTIONS")
        scl_statement.append("    CCID       CCID")
        scl_statement.append("    COMMENT    COMMENT")
        scl_statement.append("    SEARCH")
        scl_statement.append("    NO SIGNOUT")
        scl_statement.append(".")

        return '\n'.join(scl_statement)

    @staticmethod
    def print_element(path, to, options):
        scl_statement = []
        scl_statement.append("PRINT")
        scl_statement.append("  ELEMENT      '%s'" % path['element_name'])
        scl_statement.append("  FROM")
        scl_statement.append("    ENV        '%s'" % path['environment'])
        scl_statement.append("    SYS        '%s'" % path['system'])
        scl_statement.append("    SUB        '%s'" % path['subsystem'])
        scl_statement.append("    TYPE       '%s'" % path['element_type'])
        scl_statement.append("    STAGE      '%s'" % path['stage'])

        if type(to) == str:
            scl_statement.append("  TO " + to)
        else:
            scl_statement.append("  TO")
            for name, value in to.items():
                scl_statement.append('    %-10s %s' % (name, value))

        scl_statement.append("  OPTIONS")
        for name, value in options.items():
            scl_statement.append('    %-10s %s' % (name, value))

        scl_statement.append(".")

        return '\n'.join(scl_statement)

    @staticmethod
    def update_element(path, from_clause):
        scl_statement = []
        scl_statement.append("UPDATE")
        scl_statement.append("  ELEMENT      '%s'" % path['element_name'])

        if type(from_clause) == str:
            scl_statement.append("  FROM " + from_clause)
        else:
            scl_statement.append("  FROM")
            for name, value in from_clause.items():
                scl_statement.append('    %-10s %s' % (name, value))

        scl_statement.append("  TO")
        scl_statement.append("    ENV        '%s'" % path['environment'])
        scl_statement.append("    SYS        '%s'" % path['system'])
        scl_statement.append("    SUB        '%s'" % path['subsystem'])
        scl_statement.append("    TYPE       '%s'" % path['element_type'])
        scl_statement.append("  OPTIONS")
        scl_statement.append("  BYPASS GENERATE PROCESSOR")
        scl_statement.append(".")

        return '\n'.join(scl_statement)

class EndevorSOAP:
    @staticmethod
    def generate_request(url, headers, data_source, username, password, statement, parameters, attachments):
        request = {}

        # prepare HTTP request headers:
        request['headers'] = {}
        request['headers'].update(headers)
        # XML must be encapsulated in a multipart MIME message:
        boundary = 'MIMEBoundary' # encapsulation boundary
        # format the content type header:
        content_type = 'multipart/related; boundary="{}"; type="text/xml"'.format(boundary)
        request['headers']['Content-Type'] = content_type

        # generate request XML:
        envelope_element = xml.etree.ElementTree.Element('soapenv:Envelope') # root element

        # define namespaces:
        envelope_element.attrib['xmlns:xsi'] = 'http://www.w3.org/2001/XMLSchema-instance'
        envelope_element.attrib['xmlns:soapenv'] = 'http://schemas.xmlsoap.org/soap/envelope/'    
        envelope_element.attrib['xmlns:ns1'] = 'http://mime.endevor.ca.com/xsd'
        envelope_element.attrib['xmlns:ns2'] = 'http://endevor.ca.com/xsd'
        envelope_element.attrib['xmlns:ns3'] = 'http://endevor.ca.com'

        header_element = xml.etree.ElementTree.SubElement(envelope_element, 'soapenv:Header')

        body_element = xml.etree.ElementTree.SubElement(envelope_element, 'soapenv:Body')

        submit_element = xml.etree.ElementTree.SubElement(body_element, 'ns3:submitSCL')

        login_element = xml.etree.ElementTree.SubElement(submit_element, 'ns3:loginProperties')

        data_source_element = xml.etree.ElementTree.SubElement(login_element, 'ns2:dataSource')
        data_source_element.text = data_source

        password_element = xml.etree.ElementTree.SubElement(login_element, 'ns2:password')
        password_element.text = password

        username_element = xml.etree.ElementTree.SubElement(login_element, 'ns2:userId')
        username_element.text = username

        scl_element = xml.etree.ElementTree.SubElement(submit_element, 'ns3:scl')

        if not attachments:
            # indicate there are no attachments:
            attachment_element = xml.etree.ElementTree.SubElement(scl_element, 'ns2:attachments')
            attachment_element.attrib['xsi:nil'] = 'true'

        for name, content in attachments.items():
            attachment_element = xml.etree.ElementTree.SubElement(scl_element, 'ns2:attachments')

            content_element = xml.etree.ElementTree.SubElement(attachment_element, 'ns1:DD')
            content_element.text = base64.b64encode(content.encode('iso-8859-1')).decode()

            name_element = xml.etree.ElementTree.SubElement(attachment_element, 'ns1:DDName')
            name_element.text = name

            content_type_element = xml.etree.ElementTree.SubElement(attachment_element, 'ns1:contentType')
            content_type_element.attrib['xsi:nil'] = 'true'

        statement_element = xml.etree.ElementTree.SubElement(scl_element, 'ns2:statement')
        statement_element.text = statement

        parameters_element = xml.etree.ElementTree.SubElement(scl_element, 'ns2:wsParameters')
        # format the parameters:
        parameters_element.text = ' '.join(['{}=\"{}\"'.format(name, value) for name, value in parameters.items()])

        envelope_tree = xml.etree.ElementTree.ElementTree(envelope_element)
        envelope_stream = io.BytesIO()
        # generate XML declaration:
        envelope_tree.write(envelope_stream, encoding='utf-8', xml_declaration=True)
        envelope = envelope_stream.getvalue().decode() # get XML string

        # pretty format XML:
        envelope = xml.dom.minidom.parseString(envelope).toprettyxml(indent='  ')

        # prepare HTTP request data:
        request_data = []
        request_data.append('--' + boundary) # encapsulation boundary
        # prepare MIME headers:
        request_data.append('Content-ID:') # Content-ID header is required
        request_data.append('')
        request_data.append(envelope) # add the XML
        request_data.append('--' + boundary)
        request_data = '\n'.join(request_data)
        request['data'] = request_data.replace('\n', '\r\n').encode() # use CRLF line endings

        url += '/EndevorService/services/EndevorService.EndevorServiceHttpSoap11Endpoint'
        request = urllib.request.Request(url, **request)
        return request

    @staticmethod
    def parse_response(response):
        # parse Endevor XML response:
        response_tree_root = xml.etree.ElementTree.fromstring(response)

        response_data = {} # structured response data

        for element in response_tree_root[1][0][0]: # Envelope/Body/submitSCLResponse/return path
            element_tag = re.sub(r'^{.*?}', '', element.tag) # remove tag name prefix

            if element_tag == 'attachments': # parse attachments
                attachment_name = None
                attachment_content = None

                for attachment_element in element:
                    # remove tag name prefix:
                    attachment_element_tag = re.sub(r'^{.*?}', '', attachment_element.tag)

                    if attachment_element_tag == 'DDName':
                        attachment_name = attachment_element.text
                    elif attachment_element_tag == 'DD':
                        # decode the attachment from Base64:
                        attachment_content = base64.b64decode(attachment_element.text).decode('iso-8859-1')
                        # remove trailing spaces at line ends:
                        attachment_content = '\n'.join([line.rstrip() for line in attachment_content.split('\n')])

                    if attachment_name and attachment_content: # if both have been found
                        if 'attachments' not in response_data:
                            response_data['attachments'] = {}

                        response_data['attachments'][attachment_name] = attachment_content
            else:
                response_data[element_tag] = element.text

        response_data['returnCode'] = int(response_data['returnCode'])
        response_data['reasonCode'] = int(response_data['reasonCode'])

        return response_data

    @staticmethod
    def format_element_list(attachment):
        element_list = []

        line = 'Element  Type     Environ  S System   Subsys   VVLL ProcGrp  UserID   NDRC PRRC Signout  '
        line += 'CCID         NS'
        element_list.append(line)

        line = '-------- -------- -------- - -------- -------- ---- -------- -------- ---- ---- -------- '
        line += '------------ --'
        element_list.append(line)

        for row in attachment:
            row['ENDEVOR RC'] = row['ENDEVOR RC'][1:]
            row['PROC RC'] = row['PROC RC'][1:]

            pattern = '{ELM NAME:<8} {TYPE NAME:<8} {ENV NAME:<8} {STG ID} {SYS NAME:<8} {SBS NAME:<8} '
            pattern += '{ELM VV}{ELM LL} {PROC GRP NAME:<8} {LAST ACT USRID:<8} {ENDEVOR RC:<4} {PROC RC:<4} '
            pattern += '{SIGNOUT ID:<8} {ELM LAST LL CCID:<12} {NOSOURCE}'

            element_list.append(pattern.format(**row))

        return '\n'.join(element_list)

    @staticmethod
    def submit_scl(interface, url, data_source, username, password, statement, parameters=None, attachments=None):
        def format_object(data, indent=0):
            if isinstance(data, dict):
                return '\n'.join(['  ' * indent + '{}:\n{}'.format(name, format_object(value, indent + 1)) for name, value in data.items()])
            else:
                return '\n'.join(['  ' * indent + line for line in str(data).split('\n')])

        if parameters is None:
            parameters = {}

        if attachments is None:
            attachments = {}

        if not re.search(r' *\.$', statement): # if there is no dot at the end of the statement
            statement += ' .' # then add it

        # categorize statement:
        statement_type = None
        statement_subtype = None
        if statement.startswith('RET'):
            statement_type = 'RETRIEVE'
        elif statement.startswith('UPD'):
            statement_type = 'UPDATE'
        elif statement.startswith('PRI'):
            statement_type = 'PRINT'
        elif statement.startswith('LIS'):
            statement_type = 'LIST'
            if re.search(r'^LIST? +ELE(MENT)?', statement):
                statement_subtype = 'LIST ELEMENT'

        # set statement category in parameters if it's not set already:
        if 'Category' not in parameters:
            if statement_type in ['RETRIEVE', 'UPDATE']:
                parameters['Category'] = 'L'
            elif statement_type in ['PRINT']:
                parameters['Category'] = 'E'
            elif statement_type in ['LIST']:
                parameters['Category'] = 'C'
        
        headers = {'Accept-Encoding': 'gzip'}
        request = EndevorSOAP.generate_request(url, headers, data_source, username, password, statement, parameters, attachments)

        # send the request:
        response = urllib.request.urlopen(request)
        response = response.read()
        response = gzip.decompress(response).decode()
        response = EndevorSOAP.parse_response(response)

        if response['returnCode'] > 0: # check the return code
            message = None
            if 'attachments' in response:
                if 'C1MSGS1' in response['attachments']:
                    message = response['attachments']['C1MSGS1']
                elif 'APIMSGS' in response['attachments']:
                    message = response['attachments']['APIMSGS']
            
            if not message:
                message = response['message']

            print(format_object(response))

            raise Exception(message)

        if 'APIEXTR' in response['attachments']:
            attachment = response['attachments']['APIEXTR']
            attachment = [row for row in csv.DictReader(attachment.split('\n'))]

            if statement_subtype == 'LIST ELEMENT':
                # format element list:
                attachment = format_element_list(attachment)

            response['attachments']['APIEXTR'] = attachment

        return response

class EndevorREST:
    @staticmethod
    def generate_request(url, headers, data_source, username, password, statement, file_content=None):
        url += '/EndevorService/api/v2/{}/scl'.format(data_source)
        request = {}
        request['method'] = 'POST'
        boundary = 'MIMEBoundary'
        request['headers'] = {'Content-Type': 'multipart/form-data; boundary={}'.format(boundary)}
        request['headers'].update(headers)
        credentials = '%s:%s' % (username, password)
        credentials = base64.b64encode(credentials.encode()).decode()
        request['headers']['Authorization'] = "Basic %s" % credentials
        request['data'] = {}
        request['data']['sclString'] = statement
        request['data']['submitType'] = 'Element'
        if file_content is not None:
            request['data']['fromLocalFile'] = file_content
        
        body = []
        for field_name in request['data']:
            body.append('--' + boundary)
            body.append('Content-Disposition: form-data; name="{0}"'.format(field_name))
            body.append('')
            body.append(request['data'][field_name])
        body.append('--' + boundary + '--')
        body.append('')
        request['data'] = '\r\n'.join(body)
        request['data'] = request['data'].encode()
        request['headers']['Content-Length'] = len(request['data'])

        request = urllib.request.Request(url, **request)
        return request

    @staticmethod
    def submit_scl(interface, url, data_source, username, password, statement, parameters=None, files=None):
        headers = {'Accept-Encoding': 'gzip'}
        file_content = files['INPUT'] if files else None
        request = EndevorREST.generate_request(url, headers, data_source, username, password, statement, file_content)
        response = urllib.request.urlopen(request)
        response = gzip.decompress(response.read())
        response = response.decode(encoding='utf-8', errors='ignore')
        return response

class EndevorHTTP:
    def __init__(self, interface, urls, data_source, username, password, logging_level=logging.ERROR):
        if type(urls) is str:
            urls = [urls]
        self.urls = urls

        self.data_source = data_source.upper()
        self.username = username.upper()
        self.password = password
        self.interface = interface

        # set up logging:
        self.logger = logging.getLogger('endevor')
        self.logger.setLevel(logging_level)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter("%(name)s[%(asctime)s]: %(message)s", "%H:%M:%S"))
            self.logger.addHandler(stream_handler)

    def execute_scl(self, statement, parameters=None, files=None):
        # iterate through URL addreses trying to execute SCL:
        url_index = 0
        while True:
            try:
                # get next URL:
                url = self.urls[url_index]
                url_index += 1

                # try to execute SCL:
                start_time = datetime.datetime.now()
                self.logger.info("executing SCL through {}:\n{}".format(url, statement))
                interface = EndevorSOAP if self.interface == 'soap' else EndevorREST
                response = interface.submit_scl(self.interface, url, self.data_source, self.username, self.password, statement, parameters, files)
                end_time = datetime.datetime.now()
                elapsed_time = end_time - start_time
                elapsed_time = str(int(elapsed_time.total_seconds() * 1000))
                self.logger.info("SCL executed in " + elapsed_time + " ms")

                return response

            except urllib.error.URLError as error:
                if url_index == len(self.urls): # if it's the last URL
                    raise # then raise the exception
                
                self.logger.info(str(error))

    @EndevorSCL.endevor_path
    def retrieve_element(self, path):
        self.logger.info('retrieving element %s' % '/'.join(path.values()))

        if self.interface == 'soap':
            attachment_name = 'CONTENT'
            to = collections.OrderedDict()
            to['ATTACHMENT'] = attachment_name
            to['PATH'] = attachment_name
            to['LFSFILE'] = attachment_name
        else:
            to = 'LOCALFILE'

        scl_statement = EndevorSCL.retrieve_element(path, to)
        response = self.execute_scl(scl_statement)

        if self.interface == 'soap':
            if attachment_name in response['attachments']:
                response['content'] = response['attachments'][attachment_name]
                del response['attachments'][attachment_name]
            else:
                response['content'] = ''
            # determine element type:
            if 'APIMSGS' in response['attachments']:
                match = re.search(r'^ .{90}TYPE: (\S+) +STAGE ID: (\S+)', response['attachments']['APIMSGS'], re.M)
                if match:
                    response['element_type'] = match.group(1)
                    response['stage'] = match.group(2)
        else:
            response = {'content': '\n'.join([line.rstrip() for line in response.split('\n')])}
            scl_statement = EndevorSCL.list_element(path, to)
            list_element = self.execute_scl(scl_statement)
            match = re.search(r"TYPE +'(\S+) *' +STAGE +NUMBER +(\S+)", list_element)
            response['element_type'] = match.group(1)
            response['stage'] = match.group(2)

        return response

    @EndevorSCL.endevor_path
    def print_element(self, path):
        self.logger.info('printing element %s' % '/'.join(path.values()))

        if self.interface == 'soap':
            attachment_name = 'CONTENT'
            to = collections.OrderedDict()
            to['ATTACHMENT'] = attachment_name
        else:
            to = 'LOCALFILE'

        options = collections.OrderedDict()
        options['LISTING'] = 'COMPONENT'
        options['LIST'] = 'TEXT'
        options['STRING'] = 'LISTLIB'
        options['NOSEARCH'] = ''

        scl_statement = EndevorSCL.print_element(path, to, options)

        response = self.execute_scl(scl_statement)

        if self.interface == 'soap':
            if attachment_name in response['attachments']:
                response['content'] = response['attachments'][attachment_name]
                del response['attachments'][attachment_name]
        else:
            response = {'content': '\n'.join([line.rstrip() for line in response.split('\n')])}

        return response

    @EndevorSCL.endevor_path
    def update_element(self, path, element_content):
        self.logger.info('updating element %s' % '/'.join(path.values()))

        file_name = 'INPUT'
        if self.interface == 'soap':
            from_clause = {}
            from_clause['ATTACHMENT'] = file_name
            from_clause['PATH'] = file_name
            from_clause['LFSFILE'] = file_name
        else:
            from_clause = 'LOCALFILE'
        scl_statement = EndevorSCL.update_element(path, from_clause)

        response = self.execute_scl(scl_statement, files={file_name: element_content})

        return response

    def compare_elements(self, left_path, right_path, compare_utility):
        self.logger.info('comparing %s element with %s element' % ('/'.join(left_path), '/'.join(right_path)))

        left_content = self.retrieve_element(path=left_path)['content']
        left_content = re.sub(r' *\d+$', '', left_content, flags=re.M)
        left_filename = os.path.join(tempfile.gettempdir(), '-'.join(left_path))
        open(left_filename, 'w').write(left_content)

        right_content = self.retrieve_element(path=right_path)['content']
        right_content = re.sub(r' *\d+$', '', right_content, flags=re.M)
        right_filename = os.path.join(tempfile.gettempdir(), '-'.join(right_path))
        open(right_filename, 'w').write(right_content)

        subprocess.call([compare_utility, left_filename, right_filename])

        os.remove(left_filename)
        os.remove(right_filename)

class EndevorFTP:
    def __init__(self, zftp, jcl_variables, logging_level=logging.ERROR):
        self._zftp = zftp
        self._jcl_variables = jcl_variables

        # set up logging:
        self.logger = logging.getLogger('endevor')
        self.logger.setLevel(logging_level)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter("%(name)s[%(asctime)s]: %(message)s", "%H:%M:%S"))
            self.logger.addHandler(stream_handler)

    def execute_scl(self, scl):
        jcl_variables = {}
        jcl_variables['job_name'] = self._zftp.username[:4] + 'NDRV'
        jcl_variables['job_card'] = self._jcl_variables['job_card']

        steplib = ['//STEPLIB  DD   DISP=SHR,DSN={self._jcl_variables["STEPLIB"][0]}']
        for library in self._jcl_variables["STEPLIB"][1:]:
            steplib.append('//         DD   DISP=SHR,DSN={library}')
        jcl_variables['STEPLIB'] = '\n'.join(steplib)

        jcl_variables['PRDADSN'] = self._jcl_variables['PRDADSN']
        jcl_variables['scl'] = scl

        jcl = open(os.path.join(os.path.dirname(__file__), 'endevor_jcl.txt')).read().format(**jcl_variables)

        self.logger.info("executing SCL:\n{}".format(scl))
        job_id = self._zftp.submit_jcl(jcl)
        job_info = self._zftp.wait_for_job_end(job_id)
        if job_info['rc'] > 0:
            message = self._zftp.retrieve_job_spool(job_id, 'C1MSGS1')
            if job_info['rc'] != 4 or 'C1G0313W' not in message:
                self._zftp.purge_job(job_id)
                raise Exception(message)

        sysout = self._zftp.retrieve_job_spool(job_id, 'C1PRINT')
        self._zftp.purge_job(job_id)
        self.logger.info('SCL executed')

        return {'content': '\n'.join(sysout.split('\n')[:-1])}

    @EndevorSCL.endevor_path
    def retrieve_element(self, path):
        self.logger.info('retrieving element %s' % '/'.join(path.values()))

        to = collections.OrderedDict()
        to['DDNAME'] = 'C1PRINT'
        scl_statement = EndevorSCL.retrieve_element(path, to)

        response = self.execute_scl(scl_statement)

        return response

    @EndevorSCL.endevor_path
    def fast_retrieve_element(self, path, dataset_prefix):
        self.logger.info('retrieving element %s' % '/'.join(path.values()))

        dataset_name = []
        dataset_name.append(dataset_prefix)
        dataset_name.append(path['system'])
        dataset_name.append(path['subsystem'])
        dataset_name.append(path['environment'][0] + path['stage'])
        dataset_name.append(path['element_type'])
        dataset_name = '.'.join(dataset_name)
        dataset_name = '{}({})'.format(dataset_name, path['element_name'])
        
        element_content = self._zftp.download_dataset(dataset_name)

        return {'content': element_content}

    @EndevorSCL.endevor_path
    def print_element(self, path):
        self.logger.info('printing element %s' % '/'.join(path.values()))

        scl_statement = EndevorSCL.print_element(path)

        return self.execute_scl(scl_statement)

    @EndevorSCL.endevor_path
    def validate_sandbox(self, path):
        self.logger.info('validating sandbox %s' % '/'.join(path.values()))

        jcl_variables = {}
        jcl_variables['job_name'] = self._zftp.username[:4] + 'NDRV'
        jcl_variables['job_card'] = self._jcl_variables['job_card']

        steplib = ['//STEPLIB  DD   DISP=SHR,DSN={self._jcl_variables["STEPLIB"][0]}']
        for library in self._jcl_variables["STEPLIB"][1:]:
            steplib.append('//         DD   DISP=SHR,DSN={library}')
        jcl_variables['STEPLIB'] = '\n'.join(steplib)

        jcl_variables['PRDADSN'] = self._jcl_variables['PRDADSN']
        jcl_variables['script_library'] = self._jcl_variables['script_library']

        jcl_variables['environment'] = path['environment']
        jcl_variables['system'] = path['system']
        jcl_variables['subsystem'] = path['subsystem']

        jcl = open(os.path.join(os.path.dirname(__file__), 'endevor_validate_sandbox.txt')).read()

        return self._zftp.submit_jcl(jcl.format(**jcl_variables))

    @EndevorSCL.endevor_path
    def smart_generate(self, path):
        self.logger.info('performing SMARTGEN for sandbox %s' % '/'.join(path.values()))

        jcl = open(os.path.join(os.path.dirname(__file__), 'endevor_smart_generate.txt')).read()

        jcl_variables = {}
        jcl_variables['job_name'] = self._zftp.username[:4] + 'NDRV'
        jcl_variables['job_card'] = self._jcl_variables['job_card']

        steplib = ['//STEPLIB  DD   DISP=SHR,DSN={self._jcl_variables["STEPLIB"][0]}']
        for library in self._jcl_variables["STEPLIB"][1:]:
            steplib.append('//         DD   DISP=SHR,DSN={library}')
        jcl_variables['STEPLIB'] = '\n'.join(steplib)

        jcl_variables['PRDADSN'] = self._jcl_variables['PRDADSN']
        jcl_variables['script_library'] = self._jcl_variables['script_library']

        jcl_variables['environment'] = path['environment']
        jcl_variables['system'] = path['system']
        jcl_variables['subsystem'] = path['subsystem']
        
        return self._zftp.submit_jcl(jcl.format(**jcl_variables))
