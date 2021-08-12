# coding: UTF-8
import os
import sys
import re
import ssl
import json
from decimal import Decimal, getcontext
from multiprocessing.pool import ThreadPool
from pyVmomi import vim
from pyVim.connect import Disconnect, SmartConnect
import atexit

def wait_for_task(task):
    task_done = False
    while not task_done:
        if task.info.state == 'success':
            print(task.info.result)
            return task.info.result
        if task.info.state == 'error':
            print("there was an error")
            print(task.info)
            task_done = True

def get_obj(content, vimtype, name):
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    for c in container.view:
        if name:
            if c.name == name:
                obj = c
                break
        else: 
            obj = c 
            break
    return obj

def connect_vsphere(host,user, pwd, port=443):
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        si = SmartConnect(host = host, user =user, pwd = pwd, port=int(port), sslContext = context)
        atexit.register(Disconnect, si)
        content = si.RetrieveContent()
        print("vSphere {} 连接成功".format(host))
        return content, si
    except Exception as e:
        print("vSphere {} 连接失败 {}".format(host, e))
        sys.exit(1)
         
if __name__ == '__main__':
    ip = '192.168.9.242'
    port = 443
    user = 'administrator@info.com'
    password = 'infohold123ABC@'          
    content, si = connect_vsphere(ip, user, password, port)
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.HostSystem], True)

    for host in container.view:
        # 内存
        total_mem = host.summary.hardware.memorySize  # 总内存
        us_mem  = host.summary.quickStats.overallMemoryUsage * 1024 * 1024 #使用内存
        free_mem = total_mem - us_mem
        p = us_mem / total_mem # 内存使用率
        print( '主机:',host.name,'内存使用率' '%.2f%%'  %(p * 100))
        #网卡
        print( '网卡数量: {}张'.format(host.summary.hardware.numNics))
        #cpu 
        total_cpu = host.summary.hardware.cpuMhz * 16 * 2 
        us_cpu = host.summary.quickStats.overallCpuUsage
        datastorelist = []
        for ds in host.datastore:
            datastorelist.append(ds)
            print(ds.name)
        print('存储链路数：{}'.format(len(datastorelist)))#存储链路数量
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True)
    #虚拟机
    print(round(1.5))
    for vm in container.view:
        snapshot =vm.snapshot
        print(vm.name)#虚拟机名称
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.Datastore], True)
    #存储
    for datastore in container.view:
        capacity = (datastore.summary.capacity / 1099511627776)
        freeSpace = (datastore.summary.freeSpace / 1099511627776)
        us_Space = (capacity -  freeSpace)
        p = (us_Space / capacity)
        print('存储名称：{} 总容量：{}T 剩余容量： {}T 使用率: {}'.format(datastore.name,int(round(capacity)), round(freeSpace,2), '%.2f%%'  %(p * 100)))
        