# silence-alerts.py
*silence-alerts.py* is an example of Python script to silence alerts in AlertManager. It can be run in a periodically Jenkins job. The AlertManagers must be deployed in Kubernetes because
the script search the AlertManager pods and run the command *amtool* inside one of them
