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
    global c_args, datetime_format, start_time_hosts_detection
    # Have thread number start at 1 for human display.
    thread_number = i + 1
    # Download assigned hosts in this thread.
    while True:
        logger.debug('Thread %s: Looking for the next enclosure' % (thread_number))
        ids = q.get()
        # Chunk received. Start time.
        if not start_time_hosts_detection:
            start_time_hosts_detection = time.time()
        # Find start & end host ids for logging.
        if not ',' in ids:
            # Only one host_id or one range, no comma found.
            ids_range = ids
        else:
            try:
                thread_start = ids[:ids.index(',')]
                thread_end = ids[ids.rindex(',')+1:]
                ids_range = '%s-%s' % (thread_start, thread_end)
            except ValueError, e:
                # Only one host_id, no comma found.
                ids_range = ids
        logger.info('Thread %s: Downloading new hosts.' % (thread_number))
        logger.debug('Thread %s: Downloading new hosts: %s' % (thread_number, ids))
        # Set parameters.
        params = {'action': 'list',
                  'ids': ids,
                  'output_format': c_args.format,}
        # Suppress duplicate data for CSV format.
        if 'CSV' in params['output_format']:
            params.update({'suppress_duplicated_data_from_csv': '1'})
        # Add user parameter options, if applicable.
        if c_args.parameters:
            user_params = ast.literal_eval(c_args.parameters)
            params.update(user_params)
        # Download host list detection chunk.
        response = qgc.request('/api/2.0/fo/asset/host/vm/detection/',
                           params)
        q.task_done()
        # Don't write to file if benchmarking.
        if not c_args.benchmark:
            file_extension = 'csv'
            if c_args.format == 'XML':
                file_extension = 'xml'
            filename = '%s/%s-host_ids-%s.%s' % (c_args.output_directory, datetime_format, ids_range, file_extension)
            logger.debug('Writing hosts file: %s' % filename)
            with open(filename, 'w') as host_file:
                print(response, file = host_file)
        logger.debug('Thread %s: Finished downloading.: %s' % (thread_number, ids))

def save_config():
    """
    :return: Completed save.
    """
    global host_id_start
    # Save start and end to file.
    cfgfile = open("config.ini",'w')
    try:
        Config.add_section('Host ID')
    except ConfigParser.DuplicateSectionError, e:
        # File already exists.
        pass
    Config.set('Host ID','start',host_id_start)
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

def ids_in_id_list(tree):
    """Return set of extracted IPs from IP list XML.
    """
    ids = []
    # Grab all IDs and ID ranges.
    id_list = tree.xpath('//ID_SET/descendant::*/text()')
    for i in id_list:
        logger.debug('ID: %s' % i)
        if '-' in i:
            id_start = i[:i.find('-')]
            id_end = i[i.find('-')+1:]
            ids += range(int(id_start),int(id_end)+1)
        else:
            ids += [int(i)]
    return ids

def chunk_to_parameter(chunk):
    """
    :param chunk: List of numbers.
    :return: String of numbers, comma delimited, no spaces.
    """
    numbers = ''
    for number in chunk:
        numbers += '%s,' % number
    # Remove last comma.
    numbers = numbers[:-1]
    return numbers

def add_work_and_find_end_host_id(id_start, num_hosts_per_call):
    """
    :param id_start: Host ID to start querying.
    :param num_hosts_per_call: Number of hosts to query per call.
    :return: Last host ID.
    """
    global hosts_queue, logger, num_hosts
    chunk = []
    while True:
        id_start += 1
        logger.debug('Calling host API to identify host ids.')
        tree = qgc.request('/api/2.0/fo/asset/host/',
                           {'action': 'list',
                            'id_min': str(id_start),
                            'details': 'None',
                            'truncation_limit': num_hosts_per_call,})
        # Extract host ids.
        ids = ids_in_id_list(etree.fromstring(tree))
        # Add length to total number of hosts.
        num_hosts += len(ids)
        logger.info('Found %s id(s), will now queue.' % str(len(ids)))
        logger.debug('ids found: %s' % str(ids))
        # Are there any more hosts?
        if not ids:
            # No more new hosts.
            logger.info('No more new hosts.')
            # Is the current chunk incomplete?
            if chunk:
                # Send it to work queue.
                # Add work to the queue.
                logger.debug('Queuing remaining id(s): %s' % str(chunk))
                hosts_queue.put(chunk_to_parameter(chunk))
            break
        # For next round, find last host id, set to new start host id.
        id_start = ids[len(ids)-1]
        # Add hosts to work queue by popping until chunks are full.
        # Popping removes from end, so reverse to maintain order.
        ids.reverse()
        # Work until ids is empty.
        while ids:
            # Add to chunk.
            chunk.append(ids.pop())
            logger.debug('id added: %s' % str(chunk[-1]))
            # Is chunk is full?
            if len(chunk) == c_args.hosts_to_download_per_call:
                # Add work to the queue.
                logger.debug('Queuing: %s' % str(chunk))
                hosts_queue.put(chunk_to_parameter(chunk))
                # Reset chunk.
                chunk = []
    # Return last host, which was saved in id_start from while loop.
        logger.debug('Done processing up to host id: %s' % str(id_start))
    return id_start

#
#  Begin
#
# Set timers.
start_time_hosts_detection = False
start_time = time.time()
# Declare the command line flags/options we want to allow.
parser = argparse.ArgumentParser(
    description='Download hosts concurrently and efficiently via host list detection API.')
# parser.add_argument('-a', '--override_all_apps',
#                     help='Generate report for all webapps. Automatically selected for first run.')
# Do not store files.
parser.add_argument('--benchmark',
                    action = 'store_true',
                    help = argparse.SUPPRESS)
parser.add_argument('--config',
                    help = 'Configuration for Qualys connector.')
parser.add_argument('-d', '--hosts_to_download_per_call',
                     default=1000,
                     help='Override default number of hosts (1000) to download per call for host vulnerability data.')
parser.add_argument('-f', '--format',
                    default='CSV_NO_METADATA',
                    help='Set host list detection output format. (Default = CSV_NO_METADATA)')
parser.add_argument('-i','--host_id_discovery_truncation_limit',
                     default=5000,
                     help='Override default truncation limit (5000) for host ID discovery.')
parser.add_argument('-o', '--output_directory',
                    default='data',
                    help='Set directory for data output. (Default = data)')
parser.add_argument('-p', '--parameters',
                    help='Set host list detection parameters (Default: {\'suppress_duplicated_data_from_csv\': \'1\'})\n(Example: \"{\'include_search_list_titles\': \'SSL+certificate\', \'active_kernels_only\': \'1\'}\")')
parser.add_argument('-t', '--threads',
                    default=2,
                    help='Number of concurrent threads to call the host list detection API with. (Default = 2)')
parser.add_argument('-v', '--verbose',
                    action = 'store_true',
                    help='Outputs additional information to log.')
# Parse arguments.
c_args = parser.parse_args()
c_args.hosts_to_download_per_call = int(c_args.hosts_to_download_per_call)
# Create log and data directories.
PATH_LOG = 'log'
if not os.path.exists(PATH_LOG):
    os.makedirs(PATH_LOG)
if not os.path.exists(c_args.output_directory):
    os.makedirs(c_args.output_directory)
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
    logging.getLogger('qualysapi').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
# This handler writes everything to a file.
logger_file = logging.FileHandler(LOG_FILENAME)
logger_file.setFormatter(logging.Formatter("%(asctime)s %(name)-12s %(levelname)s %(funcName)s %(lineno)d %(message)s"))
# This handler prints to screen.
logger_console = logging.StreamHandler(sys.stdout)
if c_args.verbose:
    logger_file.setLevel(logging.DEBUG)
    logger_console.setLevel(logging.DEBUG)
else:
    logger_file.setLevel(logging.INFO)
    logger_console.setLevel(logging.ERROR)
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
    logger.debug('Read host_id_start from config file: %s' % str(host_id_start))
except ConfigParser.NoSectionError, e:
    # Discover start host_id, minimum is 1.
    host_id_start = 1
# Confirm start id. May be pushed back due to purging.
host_id_start = int(find_start_host_id(host_id_start))
logger.debug('New host_id_start: %s' % host_id_start)
# Keep track of number of hosts.
num_hosts = 0
# Set up multi-threading.
# Number of threads.
threads = int(c_args.threads)
# Set up some global variables
hosts_queue = Queue()
# Set up some threads to fetch the enclosures
for i in range(threads):
    worker = Thread(target=download_hosts, args=(i, hosts_queue,))
    worker.setDaemon(True)
    worker.start()
# Find hosts and queue work.
host_id_end = add_work_and_find_end_host_id(host_id_start, c_args.host_id_discovery_truncation_limit)
logger.debug('host_id_end: %s' % str(host_id_end))
elapsed_time_host_ids = time.time() - start_time
# Save configuration
save_config()
# Now wait for the queue to be empty, indicating that we have
# processed all of the downloads.
logger.info('*** All hosts queued. Waiting for downloads to complete.')
hosts_queue.join()
logger.info('*** Done')
elapsed_time = time.time() - start_time
elapsed_time_hosts_detection = time.time() - start_time_hosts_detection
logger.info('Number of threads: %s' % str(c_args.threads))
logger.info('Number of hosts downloaded per call: %s' % str(c_args.hosts_to_download_per_call))
logger.info('Number of hosts downloaded: %s' % num_hosts)
logger.info('Seconds elapsed to download all hosts ids: %s' % elapsed_time_host_ids)
logger.info('Seconds elapsed to download all hosts detection data: %s' % elapsed_time_hosts_detection)
logger.info('Seconds elapsed total: %s' % elapsed_time)