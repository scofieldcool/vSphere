from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect, SmartConnectNoSSL
import atexit
import json
import argparse
import sys
import ssl
import atexit
from concurrent.futures import ThreadPoolExecutor
try:
    sys.setdefaultencoding('utf-8')
except:
    pass

def get_obj(content, vimtype, name=None):
    '''
    列表返回,name 可以指定匹配的对象
    '''
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    obj = [ view for view in container.view]
    return obj

def main(ip, username, password):
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    si = SmartConnect(host = ip, user =username, pwd = password, port=443, sslContext = context)
	# disconnect this thing
    atexit.register(Disconnect, si)
    content = si.RetrieveContent()
	# viewTypeDatacenter = [vim.Datacenter]
    viewTypeComputeResource = [vim.ComputeResource]
	# container = content.viewManager.CreateContainerView(content.rootFolder, viewTypeDatacenter, True)
    containerView = content.viewManager.CreateContainerView(content.rootFolder, viewTypeComputeResource,
															True)  # create container view

	# datacenters = container.view
    clusters = containerView.view
    for cluster in clusters:

        hosts = cluster.host[0]
        hostconfig = hosts.configManager.dateTimeSystem

        #print(cluster.host)
		
ip = '192.168.9.242'

username = 'administrator@info.com'
password = 'infohold123ABC@@'   
main(ip, username, password)