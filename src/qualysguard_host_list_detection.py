from __future__ import print_function
__author__ = 'Parag Baxi'

# System modules
import argparse
import ast
import ConfigParser
import datetime
import logging
import os
import sys
import time

from Queue import Queue
from threading import Thread

# Local modules
import qualysapi

from lxml import objectify, etree

def download_hosts(i, q):
    """This is the worker thread function.
    It processes items in the queue one after
    another.  These daemon threads go into an
    infinite loop, and only exit when
    the main thread ends.
    """
    global c_args, datetime_format, PATH_DATA
    number_of_hosts = c_args.host_id_download_truncation_limit
    while True:
        print('%s: Looking for the next enclosure' % i)
        thread_start = q.get()
        print('%s: Downloading:' % i, thread_start)
        # Find end host id.
        thread_end = thread_start+(number_of_hosts-1)
        # Set parameters.
        params = {'action': 'list',
                  'id_min': str(thread_start),
                  'id_max': str(thread_end),
                  'output_format': c_args.format,}
        # Suppress duplicate data for CSV format.
        if 'CSV' in params['output_format']:
            params.update({'suppress_duplicated_data_from_csv': '1'})
        # Add user parameter options, if applicable.
        if c_args.options:
            user_params = ast.literal_eval(c_args.options)
            params.update(user_params)
        # Download host list detection chunk.
        response = qgc.request('/api/2.0/fo/asset/host/vm/detection/',
                           params)
        file_extension = 'csv'
        if c_args.format == 'XML':
            file_extension = 'xml'
        filename = '%s/%s-%s-%s.%s' % (PATH_DATA, datetime_format, thread_start, thread_end, file_extension)
        with open(filename, 'w') as host_file:
            print(response, file = host_file)
        q.task_done()

def save_config():
    """
    :return: Completed save.
    """
    global host_id_start, host_id_end
    # Save start and end to file.
    cfgfile = open("config.ini",'w')
    try:
        Config.add_section('Host ID')
    except ConfigParser.DuplicateSectionError, e:
        # File already exists.
        pass
    Config.set('Host ID','start',host_id_start)
    Config.set('Host ID','end',host_id_end)
    Config.write(cfgfile)
    cfgfile.close()
    return True

def find_start_host_id(id_start):
    """
    :param id_start: Host ID to start querying.
    :return: Start Host ID.
    """
    global qgc
    tree = qgc.request('/api/2.0/fo/asset/host/',
        {'action': 'list',
         'id_min': str(id_start),
         'details': 'None',
         'truncation_limit': '1',})
    # Objectify.
    host_list_output = objectify.fromstring(tree)
    # Find start ID.
    host_id_start = id_start = host_list_output.RESPONSE.ID_SET.ID.text
    return host_id_start

def find_end_host_id(id_start, host_id_truncation_limit):
    """
    :param id_start: Host ID to start querying.
    :param host_id_truncation_limit: Number of hosts to query per call.
    :return: Last host ID.
    """
    while True:
        id_start += 1
        logger.info('Calling host API.')
        tree = qgc.request('/api/2.0/fo/asset/host/',
            {'action': 'list',
             'id_min': str(id_start),
             'details': 'None',
             'truncation_limit': host_id_truncation_limit,})
        # Objectify.
        tree = etree.fromstring(tree)
        # Find last ID.
        expr = '(//ID)[last()]'
        try:
            last_id = int(tree.xpath(expr)[0].text)
        except IndexError, e:
            # No ID tag.
            logger.info('No ID tag.')
            last_id = 0
        # Find last ending range.
        expr = '(//ID_RANGE)[last()]'
        try:
            last_id_range = tree.xpath(expr)[0].text
            ending_range = int(last_id_range.split('-')[1])
        except IndexError, e:
            # No ID_RANGE tag.
            logger.info('No ID_RANGE tag.')
            ending_range = 0
        if (not last_id) and (not ending_range):
            # No more hosts.
            logger.info('No more hosts.')
            break
        # Find last host id, set to new start host id.
        id_start = max(last_id, ending_range)
    return id_start

def qualys_api(url, parameters):
    """
    :param hosts: Hosts to download.
    :return: Hosts' data.
    """
    response = qualysapi.request(url, parameters)
    return objectify.parse(response).getroot()

#
#  Begin
#
start_time = time.time()
# Declare the command line flags/options we want to allow.
parser = argparse.ArgumentParser(
    description='Download hosts concurrently and efficiently via host list detection API.')
# parser.add_argument('-a', '--override_all_apps',
#                     help='Generate report for all webapps. Automatically selected for first run.')
parser.add_argument('--config',
                    help = 'Configuration for Qualys connector.')
parser.add_argument('-f', '--format',
                    default='CSV_NO_METADATA',
                    help='Set host list detection output format (Default = CSV_NO_METADATA)')
parser.add_argument('--host_id_discovery_truncation_limit',
                     default=5000,
                     help='Override default truncation limit (5000) For host ID discovery.')
parser.add_argument('--host_id_download_truncation_limit',
                     default=5000,
                     help='Override default truncation limit (5000) For host ID discovery.')
parser.add_argument('-o', '--options',
                    help='Set host list detection options (Default: {\'suppress_duplicated_data_from_csv\': \'1\'})\n(Example: \"{\'include_search_list_titles\': \'SSL+certificate\', \'active_kernels_only\': \'1\'}\")')
parser.add_argument('-t', '--threads',
                    default=2,
                    help='Number of concurrent threads to call the host list detection API with. (Default = 2)')
parser.add_argument('-v', '--verbose',
                    action='store_true',
                    help='Outputs additional information to log.')
# Parse arguments.
c_args = parser.parse_args()
# Create log and data directories.
PATH_LOG = 'log'
if not os.path.exists(PATH_LOG):
    os.makedirs(PATH_LOG)
PATH_DATA = 'data'
if not os.path.exists(PATH_DATA):
    os.makedirs(PATH_DATA)
# Set log options.
datetime_format = datetime.datetime.now().strftime('%Y-%m-%d.%H-%M-%S')
LOG_FILENAME = '%s/%s-%s.log' % (PATH_LOG,
                                 __file__,
                                 datetime_format)
# Make a global logging object.
logger = logging.getLogger()
if c_args.verbose:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)
# This handler writes everything to a file.
logger_file = logging.FileHandler(LOG_FILENAME)
logger_file.setFormatter(logging.Formatter("%(asctime)s %(name)-12s %(levelname)s %(funcName)s %(lineno)d %(message)s"))
logger_file.setLevel(logging.INFO)
# This handler prints to screen.
logger_console = logging.StreamHandler(sys.stdout)
logger_console.setLevel(logging.ERROR)
if c_args.verbose:
    logger_file.setLevel(logging.DEBUG)
    logger_console.setLevel(logging.DEBUG)
logger.addHandler(logger_file)
logger.addHandler(logger_console)
# Configure Qualys API connector.
if c_args.config:
    qgc = qualysapi.connect(c_args.config)
else:
    qgc = qualysapi.connect()
# Read config file, if available.
Config = ConfigParser.ConfigParser()
Config.read('config.ini')
try:
    host_id_start = Config.getint('Host ID', 'start')
    logger.info('Read host_id_start from config file: %s' % str(host_id_start))
    host_id_end = Config.getint('Host ID', 'end')
    logger.info('Read host_id_end from config file: %s' % str(host_id_end))
except ConfigParser.NoSectionError, e:
    # Discover start host_id, minimum is 1.
    host_id_start = 1
# Confirm start id. May be pushed back due to purging.
host_id_start = int(find_start_host_id(host_id_start))
logger.info(host_id_start)
# Find ending host_id.
start_id = host_id_start
# Resume if possible.
try:
    start_id = host_id_end
except NameError, e:
    # No previous data. Start from first host id.
    start_id = host_id_start
host_id_end = find_end_host_id(start_id, c_args.host_id_discovery_truncation_limit)
logger.info(host_id_end)
# Save configuration
save_config()
# Download in increments of 1,000 host IDs, not 1,000 hosts.
# For example, from 1000 to 10000:
# 1000-1999
# 2000-2999
# 3000-3999
# ...
# 9000-9999
# 10000-10999

# Number of threads.
threads = int(c_args.threads)
# Set up some global variables
hosts_queue = Queue()
# Requests will be chunked into 1,000 hosts request.
chunks = []
# Chunk.
start_of_chunk = host_id_start
while start_of_chunk <= host_id_end:
    chunks.append(start_of_chunk)
    start_of_chunk += 1000
# Add ending chunk.
chunks.append(start_of_chunk )
# Set up some threads to fetch the enclosures
for i in range(threads):
    worker = Thread(target=download_hosts, args=(i, hosts_queue,))
    worker.setDaemon(True)
    worker.start()
# Download the feed(s) and put the enclosure URLs into
# the queue.
for chunk in chunks:
    logger.debug('Queuing: %s' % str(chunk))
    hosts_queue.put(chunk)

# Now wait for the queue to be empty, indicating that we have
# processed all of the downloads.
logger.info('*** Main thread waiting')
hosts_queue.join()
logger.info('*** Done')
elapsed_time = time.time() - start_time
logger.info(elapsed_time)

