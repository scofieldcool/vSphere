#!/usr/bin/env python
import sys
import atexit
import argparse
import getpass
import requests

from tools import tasks
from tools import vm as ww

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

# disable  urllib3 warnings
if hasattr(requests.packages.urllib3, 'disable_warnings'):
    requests.packages.urllib3.disable_warnings()
           

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


def get_hdd_prefix_label(language):
    language_prefix_label_mapper = {
        'English': 'Hard disk ',
        'Chinese': u'硬盘 '
    }
    return language_prefix_label_mapper.get(language)

def delete_virtual_disk(si, vm_obj, disk_number, language):
    """ Deletes virtual Disk based on disk number
    :param si: Service Instance
    :param vm_obj: Virtual Machine Object
    :param disk_number: Hard Disk Unit Number
    :param language: Vcenter API language
    :return: True if success
    """
    hdd_prefix_label = get_hdd_prefix_label(language)
    if not hdd_prefix_label:
        raise RuntimeError('Hdd prefix label could not be found')

    hdd_label = hdd_prefix_label + str(disk_number)
    virtual_hdd_device = None
    for dev in vm_obj.config.hardware.device:
        if isinstance(dev, vim.vm.device.VirtualDisk) \
                and dev.deviceInfo.label == hdd_label:
            virtual_hdd_device = dev
    if not virtual_hdd_device:
        raise RuntimeError('Virtual {} could not '
                           'be found.'.format(virtual_hdd_device))

    virtual_hdd_spec = vim.vm.device.VirtualDeviceSpec()
    virtual_hdd_spec.operation = \
        vim.vm.device.VirtualDeviceSpec.Operation.remove
    virtual_hdd_spec.device = virtual_hdd_device

    spec = vim.vm.ConfigSpec()
    spec.deviceChange = [virtual_hdd_spec]
    task = vm_obj.ReconfigVM_Task(spec=spec)
    tasks.wait_for_tasks(si, [task])
    return True  

def add_disk(vm, si, disk_size, disk_type):
        spec = vim.vm.ConfigSpec()
        # get all disks on a VM, set unit_number to the next available
        unit_number = 0
        for dev in vm.config.hardware.device:
            if hasattr(dev.backing, 'fileName'):
                unit_number = int(dev.unitNumber) + 1
                # unit_number 7 reserved for scsi controller
                if unit_number == 7:
                    unit_number += 1
                if unit_number >= 16:
                    print("we don't support this many disks")
                    return
            if isinstance(dev, vim.vm.device.VirtualSCSIController):
                controller = dev
        # add disk here
        dev_changes = []
        new_disk_kb = int(disk_size) * 1024 * 1024
        disk_spec = vim.vm.device.VirtualDeviceSpec()
        disk_spec.fileOperation = "create"
        disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        disk_spec.device = vim.vm.device.VirtualDisk()
        disk_spec.device.backing = \
            vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        if disk_type == 'thin':
            disk_spec.device.backing.thinProvisioned = True
        disk_spec.device.backing.diskMode = 'persistent'
        disk_spec.device.unitNumber = unit_number
        disk_spec.device.capacityInKB = new_disk_kb
        disk_spec.device.controllerKey = controller.key
        dev_changes.append(disk_spec)
        spec.deviceChange = dev_changes
        vm.ReconfigVM_Task(spec=spec)
        #print "%sGB disk added to %s" % (disk_size, vm.config.name)

def del_nic(si, vm, nic_number):
    """ Deletes virtual NIC based on nic number
    :param si: Service Instance
    :param vm: Virtual Machine Object
    :param nic_number: Unit Number
    :return: True if success
    """
    nic_prefix_label = 'Network adapter '
    nic_label = nic_prefix_label + str(nic_number)
    virtual_nic_device = None
    for dev in vm.config.hardware.device:
        if isinstance(dev, vim.vm.device.VirtualEthernetCard)   \
                and dev.deviceInfo.label == nic_label:
            virtual_nic_device = dev

    if not virtual_nic_device:
        raise RuntimeError('Virtual {} could not be found.'.format(nic_label))

    virtual_nic_spec = vim.vm.device.VirtualDeviceSpec()
    virtual_nic_spec.operation = \
        vim.vm.device.VirtualDeviceSpec.Operation.remove
    virtual_nic_spec.device = virtual_nic_device

    spec = vim.vm.ConfigSpec()
    spec.deviceChange = [virtual_nic_spec]
    task = vm.ReconfigVM_Task(spec=spec)
    tasks.wait_for_tasks(si, [task])
    return True

def add_nic(si, vm, network_name):
    """
    :param si: Service Instance
    :param vm: Virtual Machine Object
    :param network_name: Name of the Virtual Network
    """
    spec = vim.vm.ConfigSpec()
    nic_changes = []

    nic_spec = vim.vm.device.VirtualDeviceSpec()
    nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add

    nic_spec.device = vim.vm.device.VirtualE1000()

    nic_spec.device.deviceInfo = vim.Description()
    nic_spec.device.deviceInfo.summary = 'vCenter API test'

    content = si.RetrieveContent()
    network = get_obj(content, [vim.Network], network_name)
    if isinstance(network, vim.OpaqueNetwork):
        nic_spec.device.backing = \
            vim.vm.device.VirtualEthernetCard.OpaqueNetworkBackingInfo()
        nic_spec.device.backing.opaqueNetworkType = \
            network.summary.opaqueNetworkType
        nic_spec.device.backing.opaqueNetworkId = \
            network.summary.opaqueNetworkId
    else:
        nic_spec.device.backing = \
            vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
        nic_spec.device.backing.useAutoDetect = False
        nic_spec.device.backing.deviceName = network_name

    nic_spec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    nic_spec.device.connectable.startConnected = True
    nic_spec.device.connectable.allowGuestControl = True
    nic_spec.device.connectable.connected = False
    nic_spec.device.connectable.status = 'untried'
    nic_spec.device.wakeOnLanEnabled = True
    nic_spec.device.addressType = 'assigned'

    nic_changes.append(nic_spec)
    spec.deviceChange = nic_changes
    e = vm.ReconfigVM_Task(spec=spec)

    print("NIC CARD ADDED")

def update_virtual_nic_state(si, vm_obj, nic_number, new_nic_state):
    """
    :param si: Service Instance
    :param vm_obj: Virtual Machine Object
    :param nic_number: Network Interface Controller Number
    :param new_nic_state: Either Connect, Disconnect or Delete
    :return: True if success
    """
    nic_prefix_label = 'Network adapter '
    nic_label = nic_prefix_label + str(nic_number)
    virtual_nic_device = None
    for dev in vm_obj.config.hardware.device:
        if isinstance(dev, vim.vm.device.VirtualEthernetCard) \
                and dev.deviceInfo.label == nic_label:
            virtual_nic_device = dev
    if not virtual_nic_device:
        raise RuntimeError('Virtual {} could not be found.'.format(nic_label))

    virtual_nic_spec = vim.vm.device.VirtualDeviceSpec()
    virtual_nic_spec.operation = \
        vim.vm.device.VirtualDeviceSpec.Operation.remove \
        if new_nic_state == 'delete' \
        else vim.vm.device.VirtualDeviceSpec.Operation.edit
    virtual_nic_spec.device = virtual_nic_device
    virtual_nic_spec.device.key = virtual_nic_device.key
    virtual_nic_spec.device.macAddress = virtual_nic_device.macAddress
    virtual_nic_spec.device.backing = virtual_nic_device.backing
    virtual_nic_spec.device.wakeOnLanEnabled = \
        virtual_nic_device.wakeOnLanEnabled
    connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    if new_nic_state == 'connect':
        connectable.connected = True
        connectable.startConnected = True
    elif new_nic_state == 'disconnect':
        connectable.connected = False
        connectable.startConnected = False
    else:
        connectable = virtual_nic_device.connectable
    virtual_nic_spec.device.connectable = connectable
    dev_changes = []
    dev_changes.append(virtual_nic_spec)
    spec = vim.vm.ConfigSpec()
    spec.deviceChange = dev_changes
    task = vm_obj.ReconfigVM_Task(spec=spec)
    tasks.wait_for_tasks(si, [task])
    return True

def virtual_expansion_contraction_capacity(si, vm, numcpu, memory):
    
    config = vim.vm.ConfigSpec()
    config.numCPUs = numcpu
    config.memoryMB = (memory * 1024)

    config.cpuHotRemoveEnabled = True
    config.cpuHotAddEnabled = True
    config.memoryHotAddEnabled = True

    limite_memory = vim.ResourceAllocationInfo()
    limite_memory.limit = (16 * 1024)
    config.memoryAllocation = limite_memory

    task = vm.ReconfigVM_Task(spec=config)

    tasks.wait_for_tasks(si, [task])
def main():
  
    #connect info
    host = '192.168.9.242' #vSpehre service to connect to
    user = 'administrator@info.com'
    pwd  = 'infohold123ABC@'
    port = '443'
    no_ssl =True
    #虚拟机参数
    vm_name ='centos7-test'# 虚拟机名称
    templatename = 'centos-7.7-1908-test-85'# 模板
    datacenter_name = 'center'# 数据中心
    vm_folder = 'Test'# 文件夹
    datastore_name ='SAS-190'# 存储
    cluster_name ='cluster'# 集群
    resource_pool =''# 资源池
    power_on = False # 'power on the VM after creation
    datastorecluster_name= ''#数据存储群集
    host_name ='192.168.9.190'
    folder_name='Test'

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
   
    #数据中心对象
    datacenter = get_obj(content, [vim.Datacenter], datacenter_name)
    # 集群对象
    cluster = get_obj(content, [vim.ClusterComputeResource], cluster_name)
    # 宿主机对象
    host = get_obj(content, [vim.HostSystem], host_name)
    # 资源池
    resource_pool = cluster.resourcePool
    # 存储对象
    datastore = get_obj(content, [vim.Datastore], datastore_name)
    # 文件夹对象
    folder= get_obj(content, [vim.Folder], folder_name)
    # 虚拟机对象
    vm = get_obj(content, [vim.VirtualMachine], vm_name)

    #print(datacenter, cluster, resource_pool, host, datastore, folder, vm)
    net_name ='VM Network'
    if vm: 
        ww.print_vm_info(vm)
        #delete_virtual_disk(si, vm, '4', 'English')
        #add_disk(vm, si, 30, 'thin')
        #del_nic(si, vm,2)
        #add_nic(si, vm, 'VM Network')
        #update_virtual_nic_state(si, vm, 3, 'disconnect')
        #virtual_expansion_contraction_capacity(si, vm, 8, 8)
       
# start this thing
if __name__ == "__main__":
    main()
