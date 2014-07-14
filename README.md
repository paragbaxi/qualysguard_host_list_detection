qualysguard_host_list_detection
===============================

Multithreaded proof of concept for efficiently downloading QualysGuard VM data via the host list detection.

Usage
=====

    usage: qualysguard_host_list_detection.py [-h] [--config CONFIG]
                                              [-d HOSTS_TO_DOWNLOAD_PER_CALL]
                                              [-f FORMAT]
                                              [-i HOST_ID_DISCOVERY_TRUNCATION_LIMIT]
                                              [-o OUTPUT_DIRECTORY]
                                              [-p PARAMETERS] [-t THREADS] [-v]
    
    Download hosts concurrently and efficiently via host list detection API.
    
    optional arguments:
      -h, --help            show this help message and exit
      --config CONFIG       Configuration for Qualys connector.
      -d HOSTS_TO_DOWNLOAD_PER_CALL, --hosts_to_download_per_call HOSTS_TO_DOWNLOAD_PER_CALL
                            Override default number of hosts (1000) to download
                            per call for host vulnerability data.
      -f FORMAT, --format FORMAT
                            Set host list detection output format. (Default =
                            CSV_NO_METADATA)
      -i HOST_ID_DISCOVERY_TRUNCATION_LIMIT, --host_id_discovery_truncation_limit HOST_ID_DISCOVERY_TRUNCATION_LIMIT
                            Override default truncation limit (5000) for host ID
                            discovery.
      -o OUTPUT_DIRECTORY, --output_directory OUTPUT_DIRECTORY
                            Set directory for data output. (Default = data)
      -p PARAMETERS, --parameters PARAMETERS
                            Set host list detection parameters (Default:
                            {'suppress_duplicated_data_from_csv': '1'}) (Example:
                            "{'include_search_list_titles': 'SSL+certificate',
                            'active_kernels_only': '1'}")
      -t THREADS, --threads THREADS
                            Number of concurrent threads to call the host list
                            detection API with. (Default = 2)
      -v, --verbose         Outputs additional information to log.
      
Example run
===========

    $ python qualysguard_host_list_detection.py --config customer_lab.ini --hosts_to_download_per_call 100 --host_id_discovery_truncation_limit 400 --threads 4
    INFO:root:Found 400 id(s), will now queue.
    INFO:root:Thread 2: Downloading new hosts.
    INFO:root:Thread 3: Downloading new hosts.
    INFO:root:Thread 1: Downloading new hosts.
    INFO:root:Thread 4: Downloading new hosts.
    INFO:root:Found 400 id(s), will now queue.
    INFO:root:Found 400 id(s), will now queue.
    INFO:root:Found 112 id(s), will now queue.
    INFO:root:No more new hosts.
    INFO:root:*** All hosts queued. Waiting for downloads to complete.
    INFO:root:Thread 2: Downloading new hosts.
    INFO:root:Thread 1: Downloading new hosts.
    INFO:root:Thread 4: Downloading new hosts.
    INFO:root:Thread 3: Downloading new hosts.
    INFO:root:Thread 1: Downloading new hosts.
    INFO:root:Thread 2: Downloading new hosts.
    INFO:root:Thread 3: Downloading new hosts.
    INFO:root:Thread 1: Downloading new hosts.
    INFO:root:Thread 2: Downloading new hosts.
    INFO:root:Thread 3: Downloading new hosts.
    INFO:root:*** Done
    INFO:root:Number of threads: 4
    INFO:root:Number of hosts downloaded per call: 100
    INFO:root:Number of hosts downloaded: 1312
    INFO:root:Seconds elapsed to download all hosts ids: 18.7813980579
    INFO:root:Seconds elapsed to download all hosts detection data: 50.2793819904
    INFO:root:Seconds elapsed total: 56.7866261005
