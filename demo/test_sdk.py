import requests
import urllib3

from vmware.vapi.vsphere.client import create_vsphere_client

session = requests.session()


#Disable cert verification for demo purpose.
#This is not recommended in a production environment.

session.verify = False

vsphere_client = create_vsphere_client(server = 'http://192.168.9.242', username = 'administrator@info.com', password = 'infohold123ABC@', session = session)

vsphere_client.vcenter.VM.list()


