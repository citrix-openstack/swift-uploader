import logging
import optparse
import os
import sys
import re
import time
import hashlib

from openstack import connection
from openstack import profile
from openstack import utils

class UploadException(Exception):
    pass

def get_parser():
    usage = "usage: %prog [options] <source directory> <target path>"

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                      default=False, help='enable verbose (debug) logging')
    parser.add_option('--auth_url', dest='auth_url', default="https://identity.api.rackspacecloud.com/v2.0/",
                      help='auth url')
    parser.add_option('--username', dest='username', default="citrix.nodepool2",
                      help='Username')
    parser.add_option('--project_name', dest='project_name', default="874240",
                      help='Project Name')
    parser.add_option('--password', dest='password',
                      help='Password')
    parser.add_option('-c', '--container', dest='container', default="XenLogs",
                      help='Container to upload to.')
    parser.add_option('-r', '--region', dest='region', default='IAD',
                      help='Region to upload to.')

    return parser

def get_content_encoding(filename):
    if filename.endswith('.gz'):
        return 'gzip'
    return None

def get_content_type(filepath):
    filename=os.path.split(filepath)[-1]
    split_fn = filename.lower().split('.')
    if split_fn[-1] in ['gz']:
        split_fn = split_fn[:-1]
    if re.matches('^[0-9-]*$', split_fn[-1]):
        split_fn = split_fn[:-1]
    if split_fn[-1] in ['txt', 'log', 'conf', 'sh']:
        return 'text/plain'
    if split_fn[0] in ['messages', 'smlog']:
        return 'text/plain'
    if split_fn[-1] in ['html']:
        return 'text/html'
    return None

def get_icon(filepath):
    content_type = get_content_type(filepath)
    type_to_icon = {
        "text/plain": "text.png",
        "text/html": "html.png"
    }
    return type_to_icon.get(content_type, "blank.png")

_START_STANSA = """
<html>
 <head>
  <title>Index of %(prefix)s</title>
 </head>
 <body>
  <h1>Index of %(prefix)s</ht>
  <table cellspacing="2">
  <tr><th></th><th>Name</th><th>Last Modified</th><th>Size</th></tr>
"""
_FILE_STANSA = """
  <tr><td><img src="/apaxy/icons/%(icon)s"></td><td><a href="%(filename)s">%(filename)s</a></td><td>%(modified)s</td><td>%(size)s</td></tr>
"""
_DIR_STANSA = """
  <tr><td><img src="/apaxy/icons/folder.png"></td><td><a href="%(location)s/index.html">%(displayname)s</a></td><td>-</td><td>-</td></tr>
"""
_END_STANSA = """  </table>
 </body>
</html>
"""
def _html_start_stansa(prefix):
    return _START_STANSA % locals()

def _html_file_stansa(filename, modified, size):
    icon = filename
    params = locals()
    params["icon"] = get_icon(filename)
    return _FILE_STANSA % params

def _html_dir_stansa(location, displayname):
    return _DIR_STANSA % locals()

def _html_end_stansa():
    return _END_STANSA % locals()

def sizeof_fmt(num, suffix='B'):
    if abs(num) < 1024.0:
        return "%3d %s" % (num, suffix)
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)


def create_connection(auth_url, region, project_name, username, password):
    prof = profile.Profile()
    prof.set_region(profile.Profile.ALL, region)

    conn = connection.Connection(
        profile=prof,
        user_agent='citrixswiftuploader',
        auth_url=auth_url,
        project_name=project_name,
        username=username,
        password=password
    )
    conn.authorize()
    return conn

class SwiftUploader(object):
    logger = logging.getLogger('citrix.swiftupload')

    def __init__(self, auth_url, region, project_name, username, password):
        self.conn = create_connection(auth_url, region,
                                      project_name,
                                      username, password)


    def upload_one_file(self, container, source, target, attempt=0):
        content_encoding=get_content_encoding(source)
        content_type=get_content_type(source)
        self.logger.info('Uploading %s to %s[%s:%s]', source, target, content_encoding, content_type)

        obj = None
        chksum = -1
        with open(source, 'rb') as f:
            data = f.read()
            chksum = hashlib.sha224(data).hexdigest()
            # pylint: disable=no-member
            obj = self.conn.object_store.upload_object(container=container,
                                                       name=target, data=data,
                                                       content_encoding=content_encoding,
                                                       content_type=content_type)

        if (obj == None):
            if attempt < 5:
                self.logger.error('Upload of %s to %s failed - retrying'%(source, target))
                self.upload_one_file(container, source, target, attempt+1)
            else:
                raise UploadException('Failed to upload %s'%source)

    def _order_files(self, filenames):
        filenames.sort()
        if 'run_tests.log' in filenames:
            filenames.remove('run_tests.log')
            filenames.insert(0, 'run_tests.log')

    def _upload(self, local_dir, filename, cf_prefix, container_name):
        full_path = os.path.join(local_dir, filename)
        if os.path.isdir(full_path):
            index = _html_start_stansa(os.path.join(cf_prefix, filename))
            index = index + _html_dir_stansa(os.path.join('/', cf_prefix, os.path.dirname(filename)), 'Parent directory')
            dir_listing = os.listdir(full_path)
            self._order_files(dir_listing)
            for subfile in dir_listing:
                # Ignore symlinks
                if os.path.islink(os.path.join(full_path, subfile)):
                    continue
                index = index + self._upload(local_dir,
                                             os.path.join(filename, subfile),
                                             cf_prefix, container_name)
            index = index + _html_end_stansa()
            self.store_object(container_name, '%s/index.html'%(os.path.join(cf_prefix, filename)), index)
            self.logger.info('Added index page at %s', os.path.join(cf_prefix, filename))
            return _html_dir_stansa(os.path.split(filename)[-1], os.path.split(filename)[-1])
        else:
            cf_name = os.path.join(cf_prefix, filename)
            self.upload_one_file(container_name, full_path, cf_name)
            stats = os.stat(full_path)
            return _html_file_stansa(os.path.split(filename)[-1],
                                     time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stats.st_mtime)),
                                     sizeof_fmt(stats.st_size))

    def upload(self, container_name, local_files, cf_prefix):
        container = None
        # pylint: disable=no-member
        for cont in self.conn.object_store.containers():
            if cont.name == container_name:
                container = cont
                break
        if container == None:
            # pylint: disable=no-member
            container = self.conn.object_store.create_container(name=container_name)

        contents = _html_start_stansa(cf_prefix)
        self._order_files(local_files)
        for filename in local_files:
            if not os.path.exists(filename):
                self.logger.warn('File %s does not exist', filename)
                continue
            filename = filename.rstrip('/')
            contents = contents + self._upload(os.path.dirname(filename), os.path.basename(filename), cf_prefix, container_name)

        contents = contents + _html_end_stansa()
        self.store_object(container_name, '%s/index.html'%cf_prefix, contents)
        self.logger.info('Added index page at %s', os.path.join(cf_prefix))


    def store_object(self, container_name, location, contents):
        # pylint: disable=no-member
        self.conn.object_store.upload_object(container=container_name,
                                             name=location,
                                             data=contents)



def main():
    parser = get_parser()
    (options, args) = parser.parse_args()

    level = logging.DEBUG if options.verbose else logging.INFO
    logging.basicConfig(
        format=u'%(asctime)s %(levelname)s %(name)s %(message)s',
        level=level)

    for logger_name in ['paramiko.transport', 'paramiko.transport.sftp',
                        'requests.packages.urllib3.connectionpool']:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    local_dirs = args[:-1]
    cf_prefix = args[-1]

    uploader = SwiftUploader(options.auth_url,
                             options.region,
                             options.project_name,
                             options.username,
                             options.password)
    uploader.upload(options.container, local_dirs, cf_prefix)


if __name__ == "__main__":
    sys.exit(main())
