from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl

s = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
si = SmartConnect(host="192.168.9.242",user="Administrator@info.com",pwd="infohold123ABC@",sslContext=s)
aboutInfo=si.content.about


print(aboutInfo.fullName)
print(aboutInfo.build)
print(aboutInfo.version)
print(aboutInfo.osType)
print(aboutInfo.vendor)

print('____________________________')

datacenter =si.content.rootFolder.childEntity[0]
vms = datacenter.vmFolder.childEntity

for i in vms:
    print(i.name)

print('____________________________')

#打开虚拟机
def poweronvm(vm_name):
    content = si.content
    objView = content.viewManager.CreateContainerView(content.rootFolder,[vim.VirtualMachine],True)
    vmList = objView.view
    objView.Destroy()
    tasks = [vm.PowerOn() for vm in vmList if vm.name in vm_name]
    print(tasks)
    WaitForTasks(tasks, si)
    print("虚拟机启动成功")

#获取虚拟机状态
def getvmstatus(vm_name):
    content = si.RetrieveContent()
    for child in content.rootFolder.childEntity:
        if hasattr(child, 'vmFolder'):
            datacenter = child
            vmFolder = datacenter.vmFolder
            vmList = vmFolder.childEntity
            for vm in vmList:
                if vm.summary.config.name == vm_name :
                    print(vm.summary.runtime.powerState)
                


poweronvm('centos-7.6-1810-mddlz-240')
getvmstatus('centos-7.6-1810-mddlz-240')









