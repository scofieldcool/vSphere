# coding: UTF-8
import os
import sys
import re
import ssl
import json
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
            sys.exit(1)
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

def get_obj1(content, vimtype):
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    vm_obj = []
    for c in container.view:
       vm_obj.append(c)
    return vm_obj



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
    
def get_host_network(host, vlan):
    networks = {}
    portgroups = {}

    for i in host.config.network.portgroup:
        portgroups[i.spec.name] = i.spec.vlanId
    for net in host.network:
        info = {'name': net.name, 'net': net}
        if isinstance(net, vim.dvs.DistributedVirtualPortgroup):      
            if hasattr(net.config.defaultPortConfig.vlan, 'vlanId'): #and isinstance(net.config.defaultPortPortConfig.vlan.vlanId, int):
                info['vlanId'] = net.config.defaultPortConfig.vlan.vlanId
        else:
            info['vlanId'] = portgroups.get(net.name)
        networks[net.name] = info
    vlan_id = vlan_name = None
    try:
        vlan_id = int(vlan)
    except:
        vlan_name = vlan
    network = None
    for info in networks.values():
        if vlan_id and info.get('vlanId') == vlan_id:
            network = info['net']
        elif vlan_name and info.get('name') == vlan_name:
            network = info['net']
    return network

def get_vm_device(vm):
    devices = {'disk': [], 'nic': []}
    for d in vm.config.hardware.device:
        if isinstance(d, vim.VirtualDisk):
            devices['disk'].append(d)
        elif isinstance(d, vim.VirtualEthernetCard):
            devices['nic'].append(d)
    return devices

def set_network_device(network, nic):
    nic = nic[0] if nic else None
    nic_spec = vim.vm.device.VirtualDeviceSpec()
    nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
    if not nic or isinstance(nic, vim.vm.device.VirtualE1000):
        nic_spec.device = vim.vm.device.VirtualE1000()
    else:
        nic_spec.device = vim.vm.device.VirtualVmxnet3()

    nic_spec.device.deviceInfo = vim.Description()
    nic_spec.device.deviceInfo.label = 'Network adapter 1'
    nic_spec.device.deviceInfo.summary = network.name
    nic_spec.device.key = 4000
    nic_spec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    nic_spec.device.connectable.allowGuestControl = True
    nic_spec.device.connectable.startConnected = True

    nic_spec.device.wakeOnLanEnabled = True
    nic_spec.device.addressType = 'assigned'

    if isinstance(network, vim.DistributedVirtualPortgroup):
        print("{} 分布式网络".format(network.name))
        nic_spec.device.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
        nic_spec.device.backing.port = vim.dvs.PortConnection()
        nic_spec.device.backing.port.portgroupKey = network.key
        nic_spec.device.backing.port.switchUuid = network.config.distributedVirtualSwitch.uuid
    else:
        print('{} 标准网络'.format(network.name))
        nic_spec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
        nic_spec.device.backing.network = network
        nic_spec.device.backing.deviceName = network.name
        nic_spec.device.backing.useAutoDetect = False

    return nic_spec

def add_disk(vm, disk_size, disk_type):

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
        
        new_disk_kb = int(int(disk_size) * 1024 * 1024)
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
        return disk_spec

def set_nic_settings(ip = None, netmask = None, gateway = None):
    if not netmask:
        netmask = '255.255.255.0'
    print(ip, netmask, gateway)
    guest_map = vim.vm.customization.AdapterMapping()
    guest_map.adapter = vim.vm.customization.IPSettings()
    guest_map.adapter.ip = vim.vm.customization.FixedIp()
    guest_map.adapter.ip.ipAddress = ip
    guest_map.adapter.subnetMask = netmask
    guest_map.adapter.gateway = gateway
    return [guest_map]

def set_custom_spec(adapter_maps, hostname, dns = '', password = None, is_windows = None):
    if is_windows:
        print('模板 Windows 系统')
        ident = vim.vm.customization.Sysprep()
        ident.guiUnattended = vim.vm.customization.GuiUnattended()
        ident.gutUnattended.autoLogon = False
        ident.guiUnattended.password = vim.vm.customization.Password()
        ident.guiUnattended.password.value = password
        ident.guiUnattended.password.plainText = True
        ident.userData = vim.vm.customization.UserData()

        ident.userData.computerName = vim.vm.customozation.FixedName()
        ident.userData.computerName.name = hostname
        ident.identification = vim.vm.customization.Identification()

    else:
        print("模板 Linux 系统")
        ident = vim.vm.customization.LinuxPrep()
        ident.timeZone = 'Asia/Shanghai'
        ident.hostName = vim.vm.customization.FixedName()
        ident.hostName.name = hostname
    
    global_ip = vim.vm.customization.GlobalIPSettings()
    if dns:
        global_ip.dnsServerList = re.split(r'\s*[,;\s]\s*', dns)
    custom_spec = vim.vm.customization.Specification()
    custom_spec.nicSettingMap = adapter_maps
    custom_spec.globalIPSettings = global_ip
    custom_spec.identity = ident
    return custom_spec

def clone_vm(template_obj, vm_name, host_obj, datastore_obj, vlan, vm_ip, vm_netmask, 
             vm_gateway, power, cpu_num, memory, disk_size, vm_hostname, dns, folder_obj):

    if template_obj.summary.config.guestId.lower().startswith('win'):
        is_windows = True
    else:
        is_windows = False

    template_device = get_vm_device(template_obj)

    vm_conf = vim.vm.ConfigSpec()
    
    if cpu_num and isinstance(cpu_num, int):
        vm_conf.numCPUs = cpu_num
        if cpu_num % 2 ==0:
            vm_conf.numCoresPerSocket = int(cpu_num / 2)
        vm_conf.cpuHotAddEnabled = True
    if memory and isinstance(memory, int):
        vm_conf.memoryMB = int(memory * 1024)
        vm_conf.memoryHotAddEnabled = True
    
    nic1 = set_network_device(network, template_device['nic'])
    
    deviceChange = [nic1]

    if disk_size:
        disk1 = add_disk(template_obj, disk_size, 'thick')#add disk  thick 厚置备延时0
        deviceChange.append(disk1)

    vm_conf.deviceChange = deviceChange

    relospec = vim.vm.RelocateSpec()
    relospec.datastore = datastore_obj
    relospec.host = host_obj
    relospec.pool = host_obj.parent.resourcePool

    clonespec = vim.vm.CloneSpec()
    clonespec.location = relospec
    clonespec.powerOn = bool(power)
    clonespec.config = vm_conf
    adapter_maps = set_nic_settings(vm_ip, vm_netmask, vm_gateway)
    clonespec.customization = set_custom_spec(adapter_maps =adapter_maps,hostname= vm_hostname, dns =dns, is_windows = None)
    print("开始克隆虚拟机 {}".format(vm_name))
    if folder_obj == None:
        folder_obj = host_obj.parent.parent.vmFolder
    try:
        task = template_obj.Clone(folder = folder_obj, name = vm_name, spec = clonespec)
        wait_for_task(task)
        vm_names.append(vm_name)
        host_ips.append(vm_ip)
        print("虚拟机 {} 克隆完成".format(vm_name))
    except Exception as e:
        print('虚拟机 {} 克隆失败 {}'.format(vm_name, e))
        sys.exit(1)


def ip_assign(vm):
    adaptermap = vim.vm.customization.AdapterMapping()
    globalip = vim.vm.customization.GlobalIPSettings()
    adaptermap.adapter = vim.vm.customization.IPSettings()

    """Static IP Configuration"""
    adaptermap.adapter.ip = vim.vm.customization.FixedIp()
    adaptermap.adapter.ip.ipAddress = '127.0.0.1'
    adaptermap.adapter.subnetMask = '255.255.255.0'
    adaptermap.adapter.gateway = '127.0.0.1' 
    globalip.dnsServerList = '223.5.5.5'

    #adaptermap.adapter.dnsDomain = inputs['domain']

    # Hostname settings
    ident = vim.vm.customization.LinuxPrep()
    #ident.domain = inputs['domain']
    ident.hostName = vim.vm.customization.FixedName()
    ident.hostName.name = 'vm_name'

    customspec = vim.vm.customization.Specification()
    customspec.nicSettingMap = [adaptermap]
    customspec.globalIPSettings = globalip
    customspec.identity = ident

    print ("Reconfiguring VM Networks . . .")
    task = vm.Customize(spec=customspec)
  
def virtual_nic_state(vm_obj):
    vms = None
    i = 0
    virtual_nic_device = []
    for dev in vm_obj.config.hardware.device:
        if isinstance(dev, vim.vm.device.VirtualEthernetCard):  
            virtual_nic_device.append(dev)
    if not virtual_nic_device:
        print('vm{} not nic_device'.format(vm_obj))
    if len(virtual_nic_device ) != 0:
        for nic in virtual_nic_device:
            if nic.connectable.connected == True:
                i = i + 1 #如果有网卡连接则加1
    if i == 0:
       return vm_obj.name

def get_obj(content, vimtype, name):
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    for c in container.view:
        if c.name == name:
            obj = c
            break
    return obj

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
    nic_spec.device.deviceInfo.summary = ''
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
        #nic_spec.device.backing.deviceName = network
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
    vm.ReconfigVM_Task(spec=spec)
    print("NIC CARD ADDED")
  
if __name__ == '__main__':

    ip = '192.168.9.242'
    port = 443
    user = 'administrator@info.com'
    password = 'infohold123ABC@@'
    content, si = connect_vsphere(ip, user, password, port)
    vm = get_obj(content, [vim.VirtualMachine], 'centos-7.7-1908-db-110')
    hostname = vm.summary.guest.hostName
    #add_nic(si,vm,'192.168.9.0_24_Distributed')
    host_obj = get_obj(content, [vim.HostSystem], "192.168.9.190")
    #snapshot_name = "snapshot_name" 
    #description = "Test snapshot"
    #dump_memory = False
    #quiesce = False
    #vm.CreateSnapshot(snapshot_name, description, dump_memory, quiesce)# 创建快照
    host_ips = []
    vm_names = []
    dns = ''
    vm_netmask = ''
    #pool = ThreadPool(2)
    
    host = '192.168.9.196'
    datastore = 'sata-196'
    vlan = '192.168.9.0_24_Distributed'
    template = 'centos-7.7-1908-template'
    vm_name = 'test3 test3 192.168.9.251;test2 test2 192.168.9.252;'
    folder = 'Test'
    power = True
    memory = 2
    cpu_num = 2
    disk_size = ''

    '''
    #content = si.RetrieveContent()
    vm = get_obj1(content, [vim.VirtualMachine])
    #print(vm)
    vms = []
    for i in vm:
        if i.runtime.powerState == 'poweredOn':
            off_nic = virtual_nic_state(i)
            if off_nic:
                vms.append(off_nic)

    print(vms)
    '''
    vm = get_obj(content, [vim.VirtualMachine], 'bdp_mongodb')
    #vm.Destroy_Task() #销毁虚拟机
    cpu = vm.summary.config.numCpu #模板cpu 
    note = vm.config.annotation
    memorySize = int(vm.summary.config.memorySizeMB) / 1024 #模板内存
    spec = vim.vm.ConfigSpec()
    spec.name = 'bdp_mongodb1'
    spec.annotation = "test" #备注
    vm.ReconfigVM_Task(spec)

    #virtual_nic_state(vm)
    #ip_assign(vm)
    #print(vm)
    #vm.Rename('windows-10-1903-test-239_1')

    for line in re.split(';', vm_name.strip()):
        if not line.strip():
            continue
        vm_name_list = line.strip().split()
        if len(vm_name_list) == 3:
            vm_name = vm_name_list[0]
            vm_hostname =vm_name_list[1]
            vm_ip = vm_name_list[2]
        else:
            print('[WARN] {} 格式错误，应为 虚拟机名 主机名 IP;'.format(line))
            sys.exit(1)

        compile_ip=re.compile('^(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|[1-9])\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)$')
        if not compile_ip.match(vm_ip):
            print("IP {} 地址格式错误".format(vm_ip))
            sys.exit(1)
        g = vm_ip.split('.',-1)
        vm_gateway = g[0] + '.' + g[1] + '.' + g[2] + '.' + '1'

        vm_obj = get_obj(content, [vim.VirtualMachine], vm_name)
        if vm_obj:
            print("虚拟机 {} 已经存在，请选择其他名称". format(vm_name))
            sys.exit(1)
        template_obj = get_obj(content, [vim.VirtualMachine], template)
        if not template_obj:
            print('模板 {} 不存在'.format(template))
            sys.exit(1)
        print('获取到模板对象 {}'.format(template_obj))
        host_obj = get_obj(content, [vim.HostSystem], host)
        if not host_obj: 
            print('主机 {} 不存在'.format(host))
            sys.exit(1)
        print('获取到主机对象 {}'.format(host_obj))
        datastore_obj = get_obj(content, [vim.Datastore], datastore)
        if not datastore_obj:
            print('存储 {} 不存在'.format(datastore))
            sys.exit(1)
        print('获取到存储对象 {}'.format(datastore_obj))
        network = get_host_network(host_obj, vlan)
        if not network:
            print('主机 {} 不存在 {} 网络'.format(host, vlan))
            sys.exit(1)
        print('获取到网络对象 {}'.format(network))
        folder_obj = get_obj(content, [vim.Folder], folder)
        if not folder_obj:
            print("文件夹 {} 不存在".format(folder))
        print('获取到文件夹对象 {}'.format(folder_obj))
        clone_vm(template_obj, vm_name, host_obj, datastore_obj, vlan, 
                 vm_ip, vm_netmask, vm_gateway, power, cpu_num, memory, 
                 disk_size, vm_hostname, dns, folder_obj)