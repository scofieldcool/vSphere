#!/usr/bin/env python
import sys
import atexit
import argparse
import getpass

from tools import tasks

try:
    from pyVmomi import vim
    from pyVim.connect import SmartConnect, SmartConnectNoSSL, Disconnect
except:
    print("执行主机无pyVmomi库，无法执行操作！")
    sys.exit(1)


def wait_for_task(task):
    """ wait for a vCenter task to finish """
    task_done = False
    while not task_done:
        if task.info.state == 'success':
            return task.info.result

        if task.info.state == 'error':
            print("there was an error")
            print(task.info)
            task_done = True


def get_obj(content, vimtype, name):
    """
    Return an object by name, if name is None the
    first found object is returned
    """
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


def clone_vm(
        content, template, vm_name, si,
        datacenter_name, vm_folder, datastore_name,
        cluster_name, power_on, resource_pool, datastorecluster_name):
    """
    Clone a VM from a template/VM, datacenter_name, vm_folder, datastore_name
    cluster_name, resource_pool, and power_on are all optional.
    """

    # if none git the first one
    datacenter = get_obj(content, [vim.Datacenter], datacenter_name)

    
    if vm_folder:
        destfolder = get_obj(content, [vim.Folder], vm_folder)
    else:
        destfolder = datacenter.vmFolder 
    if datastore_name:
        datastore = get_obj(content, [vim.Datastore], datastore_name)
    else:
        datastore = get_obj(
            content, [vim.Datastore], template.datastore[0].info.name)

    # if None, get the first one
    cluster = get_obj(content, [vim.ClusterComputeResource], cluster_name)

    if resource_pool:
        resource_pool = get_obj(content, [vim.ResourcePool], resource_pool)
    else:
        resource_pool = cluster.resourcePool

    vmconf = vim.vm.ConfigSpec()

    if datastorecluster_name:
        podsel = vim.storageDrs.PodSelectionSpec()
        pod = get_obj(content, [vim.StoragePod], datastorecluster_name)
        podsel.storagePod = pod

        storagespec = vim.storageDrs.StoragePlacementSpec()
        storagespec.podSelectionSpec = podsel
        storagespec.type = 'create'
        storagespec.folder = destfolder
        storagespec.resourcePool = resource_pool
        storagespec.configSpec = vmconf

        try:
            rec = content.storageResourceManager.RecommendDatastores(
                storageSpec=storagespec)
            rec_action = rec.recommendations[0].action[0]
            real_datastore_name = rec_action.destination.name
        except:
            real_datastore_name = template.datastore[0].info.name

        datastore = get_obj(content, [vim.Datastore], real_datastore_name)

    # set relospec
    relospec = vim.vm.RelocateSpec()
    relospec.datastore = datastore
    relospec.pool = resource_pool

    clonespec = vim.vm.CloneSpec()
    clonespec.location = relospec
    clonespec.powerOn = power_on

    print("cloning VM...")
    task = template.Clone(folder=destfolder, name=vm_name, spec=clonespec)
    wait_for_task(task)


def main():
  
    #connect info
    host = '192.168.9.242' #vSpehre service to connect to
    user = 'administrator@info.com'
    pwd  = 'infohold123ABC@'
    port = '443'
    no_ssl =True

    #虚拟机参数
    vm_name ='test1'# 虚拟机名称
    templatename = 'centos-7.7-1908-zabbix-1-234'# 模板
    datacenter_name = 'center'# 数据中心
    vm_folder = 'Test'# 文件夹
    datastore_name ='SAS-196'# 存储
    cluster_name ='cluster'# 集群
    resource_pool =''# 资源池
    power_on = False # 'power on the VM after creation
    datastorecluster_name= ''#数据存储群集


    # connect this thing
    si = None
    if no_ssl:
        si = SmartConnectNoSSL(
            host=host,
            user=user,
            pwd=pwd,
            port=port)
    else:
        si = SmartConnect(
            host=host,
            user=user,
            pwd=pwd,
            port=port)
    # disconnect this thing
    # 程序退出时断开连接。
    atexit.register(Disconnect, si)
    content = si.RetrieveContent()


    vm = get_obj(content, [vim.VirtualMachine], vm_name)
    #return
    if vm:
        print('Virtual machine {0}  already exists'.format(vm.name))
        return

    datacenter = get_obj(content, [vim.Datacenter], datacenter_name)
    if not datacenter:
        print('datecenter not found!');
        return

    template = get_obj(content, [vim.VirtualMachine], templatename)
   
    if not template:
        print('template not found!')
        return

    destfolder = get_obj(content, [vim.Folder], vm_folder)
    if not destfolder:
        print('folder not found！')
        return
    print('template:{0} datacenter:{1} destfolder:{2}'.format(template.name, datacenter.name, destfolder.name))
    clone_vm(
        content, template, vm_name, si,
        datacenter_name, vm_folder,
        datastore_name, cluster_name,
        power_on,resource_pool,datastorecluster_name)
   
# start this thing
if __name__ == "__main__":
    main()
