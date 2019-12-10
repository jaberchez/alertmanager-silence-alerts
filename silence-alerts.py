#! /usr/bin/python3

###################################################################################################################
# Descripcion: Script to silence alerts in Alertmanager
#
# Departament: Innovation
###################################################################################################################

# Imports
#------------------------------------------------------------------------------------------------------------------
from datetime import datetime
from datetime import timedelta
from kubernetes import client, config, stream
from kubernetes.client.rest import ApiException
from kubernetes.config import ConfigException
from json.decoder import JSONDecodeError
from time import process_time
stream = stream.stream

import os
import sys
import re
import signal
import yaml
import subprocess
import random
import json
import pytz
import atexit
import timeit
#------------------------------------------------------------------------------------------------------------------

# Variables
#------------------------------------------------------------------------------------------------------------------
current_date      = datetime.now()
process_init_time = timeit.default_timer()
file_conf         = None
default_file_conf = None
conf              = {}


k8s_conn_default  = 'in'
k8s_instance      = None
amtool            = 'amtool --alertmanager.url=http://localhost:9093'
#------------------------------------------------------------------------------------------------------------------

# Funciones
#==================================================================================================================
# Description: Handle signals
# Parameters:  Signal and frame of the object
# Return:      Nothing, exit the script

def signal_handler(sig, frame):
   name_signal = ''

   if sig == 2:
      name_signal = "SIGINT"
   elif sig == 15:
      name_signal = "SIGTERM"
   else:
      name_signal = "UNKNOWN"

   print("\nGot signal: " + name_signal)
   sys.exit(0)
#==================================================================================================================

#==================================================================================================================
# Description: Main
# Parameters:  None
# Return:      Nothing

def main():
   k8s_load_config() 
   load_file_conf()
   silence_alerts()
#==================================================================================================================

#==================================================================================================================
# Description: Load file conf (yaml format)
# Parameters:  None
# Return:      Nothing, if any issue exit the script

def load_file_conf():
   global file_conf
   global conf

   if not os.path.exists(file_conf):
      print("[ERROR] File \"{0}\" not found".format(file_conf))
      sys.exit(1)

   with open(file_conf) as stream:
      try:
         conf = yaml.load(stream, Loader=yaml.FullLoader)
      except yaml.YAMLError as ex:
         print("[ERROR] {}".format(ex))
         sys.exit(1)
#==================================================================================================================

#==================================================================================================================
# Description: Make sanity checks and call make_silence() 
# Parameters:  None
# Return:      Nothing, if any issue exit the script

def silence_alerts():
   global conf

   every_directive_exists = False
   every_directives       = ["everyDay", "everyMonday", "everyTuesday", 
                             "everyWednesday", "everyThursday", "everyFriday", 
                             "everySaturday", "everySunday", "fixed"]

   if not 'alerts' in conf:
      print("[ERROR] alerts section not found")
      sys.exit(1)

   if len(conf['alerts']) == 0:
      #print("No alerts found")
      sys.exit(0)

   # Sanity checks
   if not 'global' in conf:
      print("[ERROR] global section not found")
      sys.exit(1)

   if 'comment' in conf['global']:
      if len(conf['global']['comment']) == 0:
         print("[ERROR] global.comment is empty")
         sys.exit(1)
   else:
      print("[ERROR] global.comment directive not found")
      sys.exit(1)

   if 'author' in conf['global']:
      if len(conf['global']['author']) == 0:
         print("[ERROR] global.author is empty")
         sys.exit(1)
   else:
      print("[ERROR] global.author directive not found")
      sys.exit(1)

   for alert in conf['alerts']:
      if not 'when' in alert:
         print("[ERROR] when directive not found in alert")
         sys.exit(1)

      if not 'labels' in alert:
         print("[ERROR] labels directive not found in alert")
         sys.exit(1)

      for c in every_directives:
         if c in alert['when']:
            every_directive_exists = True
            break
            
      if every_directive_exists:
         every_directive_exists = False
      else:
         print("[ERROR] No directive every* or fixed found in when")
         sys.exit(1)

      make_silence(alert)
#==================================================================================================================

#==================================================================================================================
# Description: Sanity checks for dates
# Parameters:  Alert
# Return:      Nothing, if any issue exit the script

def check_time(alert):
   when_type = list(alert['when'])[0]

   if not 'timeStart' in alert['when'][when_type] and not 'timeEnd' in alert['when'][when_type]:
      print("[ERROR] timeStart or timeEnd not found")
      sys.exit(1)

   if not re.match(r'^\d{1,2}:\d{1,2}:\d{1,2}$', alert['when'][when_type]['timeStart']):
      print('[ERROR] Format timeStart incorrect: {}'.format(alert['when'][when_type]['timeStart']))
      sys.exit(1)

   if not re.match(r'^\d{1,2}:\d{1,2}:\d{1,2}$', alert['when'][when_type]['timeEnd']):
      print('[ERROR] Format timeEnd incorrect: {}'.format(alert['when'][when_type]['timeEnd']))
      sys.exit(1)

   if when_type == 'fixed':
      # If it is fixed we also check dateStart and dateEnd
      if not 'dateStart' in alert['when'][when_type] and not 'dateEnd' in alert['when'][when_type]:
         print('[ERROR] dateStart or dateEnd not found')
         sys.exit(1)

      if not re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', alert['when'][when_type]['dateStart']):
         print('[ERROR] Format dateStart incorrect: {}'.format(alert['when'][when_type]['dateStart']))
         sys.exit(1)

      if not re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', alert['when'][when_type]['dateEnd']):
         print('[ERROR] Format dateEnd incorrect: {}'.format(alert['when'][when_type]['dateEnd']))
         sys.exit(1)
#==================================================================================================================

#==================================================================================================================
# Description: Make the alert silence
# Parameters:  Alert
# Return:      Nothing, if any issue exit the script

def make_silence(alert):
   global current_date
   global amtool

   when_type        = list(alert['when'])[0]
   cmd              = ''

   time_start       = ''
   time_end         = ''

   date_start       = ''
   date_end         = ''

   found_alertname  = False

   # Check if today we have to silence the alert
   if when_type == 'everyDay':
      # We check exceptions
      if 'except' in alert['when'][when_type]:
         weekdays   = ['monday',   'tuesday', 'wednesday', 
                       'thursday', 'friday',  'saturday', 'sunday']
         weekday    = weekdays[current_date.weekday()]

         for exc in alert['when'][when_type]['except']:
            if weekday == exc.lower():
               # Today is an exception, so we don't silence the alert
               return
   elif when_type == 'everyMonday':
      if current_date.weekday() != 0:
         return
   elif when_type == 'everyTuesday':
      if current_date.weekday() != 1:
         return
   elif when_type == 'everyWednesday':
      if current_date.weekday() != 2:
         return
   elif when_type == 'everyThursday':
      if current_date.weekday() != 3:
         return
   elif when_type == 'everyFriday':
      if current_date.weekday() != 4:
         return
   elif when_type == 'everySaturday':
      if current_date.weekday() != 5:
         return
   elif when_type == 'everySunday':
      if current_date.weekday() != 6:
         return

   # Sanity checks for time and date
   check_time(alert)

   cmd = amtool + ' silence add'

   if 'comment' in alert:
      cmd    = cmd + " --comment " + '\"' + alert['comment'] + '\"'
   else:
      cmd    = cmd + " --comment=" + '\"' + conf['global']['comment'] + '\"'

   if 'author' in alert:
      cmd    = cmd + " --author " + '\"' + alert['author'] + '\"'
   else:
      cmd    = cmd + " --author=" + '\"' + conf['global']['author'] + '\"'

   time_start = alert['when'][when_type]['timeStart']
   time_end   = alert['when'][when_type]['timeEnd']

   # If when type is fixed we also get the dateStart and dateEnd
   if when_type == 'fixed':
      date_start      = alert['when'][when_type]['dateStart']
      date_end        = alert['when'][when_type]['dateEnd']

      month_day_start = int(re.sub(r'^(\d{1,2})-\d{1,2}-\d{4}$', r'\1', date_start))
      month_start     = int(re.sub(r'^\d{1,2}-(\d{1,2})-\d{4}$', r'\1', date_start))
      year_start      = int(re.sub(r'^\d{1,2}-\d{1,2}-(\d{4})$', r'\1', date_start))

      month_day_end   = int(re.sub(r'^(\d{1,2})-\d{1,2}-\d{4}$', r'\1', date_end))
      month_end       = int(re.sub(r'^\d{1,2}-(\d{1,2})-\d{4}$', r'\1', date_end))
      year_end        = int(re.sub(r'^\d{1,2}-\d{1,2}-(\d{4})$', r'\1', date_end))


   # We get the start/end hour, min and second to create the command with the
   # correct time
   hour_start = int(re.sub(r'^(\d{1,2}):\d{1,2}:\d{1,2}$', r'\1', time_start))
   min_start  = int(re.sub(r'^\d{1,2}:(\d{1,2}):\d{1,2}$', r'\1', time_start))
   sec_start  = int(re.sub(r'^\d{1,2}:\d{1,2}:(\d{1,2})$', r'\1', time_start))

   hour_end   = int(re.sub(r'^(\d{1,2}):\d{1,2}:\d{1,2}$', r'\1', time_end))
   min_end    = int(re.sub(r'^\d{1,2}:(\d{1,2}):\d{1,2}$', r'\1', time_end))
   sec_end    = int(re.sub(r'^\d{1,2}:\d{1,2}:(\d{1,2})$', r'\1', time_end))

   # Example date format for amtool: 2019-10-25T22:00:00-00:00
   if when_type == 'fixed':
      start = "{}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}-00:00".format(
              year_start,month_start,month_day_start,
              hour_start,min_start,sec_start)
   else:
      start = "{}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}-00:00".format(
              current_date.year,current_date.month,current_date.day,
              hour_start,min_start,sec_start)

   if hour_start > hour_end:
      # Hour start is greather than hour end, so the silence finishes in the next day
      #
      # We add a day to the current
      finish_date = current_date + timedelta(days=1)
   else:
      finish_date = current_date

   if when_type == 'fixed':
      end = "{}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}-00:00".format(
              year_end,month_end,month_day_end,
              hour_end,min_end,sec_end)
   else:
      end = "{}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}-00:00".format(
              finish_date.year,finish_date.month,finish_date.day,
              hour_end,min_end,sec_end)

   # If the dates are old, add a day
   if is_date_old(start):
      start = add_day_to_date(start)

   if is_date_old(end):
      end = add_day_to_date(end)

   # Convert dates in UTC
   # Notice: We convert the dates in UTC because Alertmanger uses UTC
   start = convert_datetime_to_utc(start)
   end   = convert_datetime_to_utc(end)

   # Add start and end time
   cmd = cmd + " --start=" + start + " --end=" + end 

   # Sanity checks for alertname label
   # Notice: alertname is mandatory
   for label in alert['labels']:
      if 'alertname' in label['name']:
         found_alertname = True
         break

   if not found_alertname:
      print("[ERROR] alertname label not found")
      sys.exit(1)

   # Add the labels
   for label in alert['labels']:
      if not 'name' in label and not 'value' in label and not 'type' in label:
         print("[ERROR] name, value or type not found in labels")
         sys.exit(1)
         
      if label['type'] != 'string' and label['type'] != 'regex':
         print("[ERROR] type unknown, only string or regex")
         sys.exit(1)

      if label['type'] == 'regex':
         cmd = cmd + ' {}=~"{}"'.format(label['name'],label['value'])
      else:
         cmd = cmd + ' {}="{}"'.format(label['name'],label['value'])

   # Before run the command we check if the silence is already created
   if check_if_silence_already_exists(start, end, alert['labels']):
      return

   # Run the command
   exec_command(cmd)
#==================================================================================================================

#==================================================================================================================
# Description: Run de alert command inside the pod
# Parameters:  cmd
# Return:      API response if OK, otherwise exit the script

def exec_command(cmd):
   namespace = 'alertmanager'
   stderr    = True 
   stdin     = True 
   stdout    = True 
   tty       = True 

   # We get all alertmanager pods
   ampods    = get_alertmanager_pods()

   # We choose a random pod
   name      = ampods[random.randint(0, len(ampods) - 1)]

   try: 
      api_response = stream(k8s_instance.connect_get_namespaced_pod_exec,
                       name, namespace, command=['sh', '-c', cmd], stderr=stderr, stdin=stdin, 
                       stdout=stdout, tty=tty)
      return api_response
   except ApiException as e:
      print("[ERROR] Exception when calling CoreV1Api->connect_get_namespaced_pod_exec: {}".format(e))
      sys.exit(1)
#==================================================================================================================

#==================================================================================================================
# Description: Get alertmanager pods
# Parameters:  None
# Return:      A list with the pods found. If any issue exit the script

def get_alertmanager_pods():
   global k8s_instance

   pods = []
  
   try:
      ret = k8s_instance.list_namespaced_pod(namespace='alertmanager',watch=False)

      for i in ret.items:
         pods.append(i.metadata.name)
   except ApiException as e:
      print("[ERROR] Exception when calling CoreV1Api->list_namespaced_pod: {}".format(e))
      sys.exit(1)

   # Doble check
   if len(pods) == 0:
      print("[ERROR] Alertmanager Pods not found")
      sys.exit(1)

   return pods 
#==================================================================================================================

#==================================================================================================================
# Description: Compare if a date is old than the current
# Parameters:  Date format
# Return:      True if is old, False is not

def is_date_old(string_date):
   global current_date

   string_date = string_date.replace('-00:00','')
   d           = datetime.strptime(string_date, "%Y-%m-%dT%H:%M:%S")

   if d < current_date:
      return True
   return False
#==================================================================================================================

#==================================================================================================================
# Description: Load kubernetes config
# Parameters:  None
# Return:      Nothing. If any issue exists the script

def k8s_load_config():
   global k8s_instance

   if k8s_conn == 'in':
      try:
         config.load_incluster_config()
      except ConfigException as e:
         print(
            "[ERROR] Exception when calling kubernetes config->load_incluster_config: {}\n".format(e))
         sys.exit(1)
   else:
      try:
         config.load_kube_config()
      except ConfigException as e:
         print(
            "[ERROR] Exception when calling kubernetes config->load_kube_config: {}".format(e))
         sys.exit(1)

   k8s_instance = client.CoreV1Api()
#==================================================================================================================

#==================================================================================================================
# Description: Load kubernetes config
# Parameters:  Date start, date end, comment, author and list of labels
# Return:      True if exists, False otherwise. If any issue exists the script

def check_if_silence_already_exists(start, end, labels):
   labels_orig = []
   labels_dest = []

   start       = start.replace('-00:00','')
   end         = end.replace('-00:00','')

   # Create list labels orig
   for l in labels:
      labels_orig.append({"name": "{}".format(l['name']), "value": "{}".format(l['value'])})

   # We build the command to query if alert already exists
   cmd = amtool + ' silence query -o json'

   # Run the command
   json_res = exec_command(cmd)

   # Replace sigle for doble quote
   json_res = json_res.replace("'",'"')

   # Replace False for "False"
   json_res = json_res.replace("False",'"False"')

   # Replace True for "True"
   json_res = json_res.replace("True",'"True"')

   # Convert string to dict
   try:
      res = json.loads(json_res)
   except JSONDecodeError as e:
      print( "[ERROR] Exception json.loads: {}".format(e))
      sys.exit(1)

   for j in res:
      start_got   = "{}".format(j['startsAt'])
      end_got     = "{}".format(j['endsAt'])

      start_got   = re.sub(r'\.\d{3}\w$', '', start_got)
      end_got     = re.sub(r'\.\d{3}\w$', '', end_got)

      # Check if is the same values
      if start == start_got and end == end_got:
         # Dates are the same, we check the labels
         for l in j['matchers']:
            labels_dest.append({"name": "{}".format(l['name']), "value": "{}".format(l['value'])})

         if labels_orig == labels_dest:
            # This silence is already created
            return True
            
   return False
#==================================================================================================================

#==================================================================================================================
# Description: Add a day to the date passed as a parameter
# Parameters:  String with the date
# Return:      New date

def add_day_to_date(string_date):
   string_date = string_date.replace('-00:00','')
   d           = datetime.strptime(string_date, "%Y-%m-%dT%H:%M:%S")

   # Add a day
   d           = d + timedelta(days=1)

   # Return string with the correct format
   return "{}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}-00:00".format(
              d.year, d.month, d.day, d.hour, d.minute, d.second)
#==================================================================================================================

#==================================================================================================================
# Description: Convert datetime to UTC
# Parameters:  String with the date
# Return:      New date

def convert_datetime_to_utc(string_date):
   local_tz    = pytz.timezone ("Europe/Madrid")

   string_date = string_date.replace('-00:00','')
   d           = datetime.strptime(string_date, "%Y-%m-%dT%H:%M:%S")
   d           = local_tz.localize(d, is_dst=None)
   d           = d.astimezone(pytz.utc)

   # Return string with the correct format
   return "{}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}-00:00".format(
              d.year, d.month, d.day, d.hour, d.minute, d.second)
#==================================================================================================================

#==================================================================================================================
# Description: Print process duration
# Parameters:  None
# Return:      Nothing

def print_duration():
   print("Duration: {:0.4f} seconds".format(timeit.default_timer() - process_init_time))
#==================================================================================================================

# Main
#******************************************************************************************************************
if __name__ == '__main__':
   # Capture signals
   signal.signal(signal.SIGTERM, signal_handler)
   signal.signal(signal.SIGINT,  signal_handler)

   # Register the function which print the duration of the process
   atexit.register(print_duration)

   file_conf = os.environ.get('FILE_CONF')
   k8s_conn  = os.environ.get('K8S_CONNECTION', k8s_conn_default)

   base_path = os.path.dirname( os.path.realpath(__file__) )
   base_path = base_path.replace('/scripts','')

   default_file_conf = "{}/conf/silence-alerts.yaml".format(base_path)

   if file_conf == None:
      file_conf = default_file_conf

   if k8s_conn != 'in' and k8s_conn != 'out':
      print("[ERROR] Kubernetes connection unknown: {}".format(k8s_conn))
      sys.exit(1)

   main()
#******************************************************************************************************************
