from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from pyVmomi import vmodl
import ssl

__author__ = ' '


def vShereconnect():
    try:
        s = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        si = SmartConnect(host="192.168.9.242",user="Administrator@info.com",pwd="infohold123ABC@",sslContext=s)
        print("连接成功")
        return si
    except Exception:
        print("连接错误")


def wait_for_tasks(content, tasks):
    """
    Given the tasks, it returns after all the tasks are complete
    """
    taskList = [str(task) for task in tasks]

    # Create filter
    objSpecs = [
        vmodl.query.PropertyCollector.ObjectSpec(obj=task) for task in tasks
    ]
    propSpec = vmodl.query.PropertyCollector.PropertySpec(
        type=vim.Task, pathSet=[], all=True)
    filterSpec = vmodl.query.PropertyCollector.FilterSpec()
    filterSpec.objectSet = objSpecs
    filterSpec.propSet = [propSpec]
    task_filter = content.propertyCollector.CreateFilter(filterSpec, True)

    try:
        version, state = None, None

        # Loop looking for updates till the state moves to a completed state.
        while len(taskList):
            update = content.propertyCollector.WaitForUpdates(version)
            for filterSet in update.filterSet:
                for objSet in filterSet.objectSet:
                    task = objSet.obj
                    for change in objSet.changeSet:
                        if change.name == 'info':
                            state = change.val.state
                        elif change.name == 'info.state':
                            state = change.val
                        else:
                            continue

                        if not str(task) in taskList:
                            continue

                        if state == vim.TaskInfo.State.success:
                            # Remove task from taskList
                            taskList.remove(str(task))
                        elif state == vim.TaskInfo.State.error:
                            raise task.info.error
            # Move to next version
            version = update.version
    finally:
        if task_filter:
            task_filter.Destroy()

#open vm power
def poweronvm(content,mo):
    """
    Powers on a VM and wait for power on operation to complete
    """
    if not isinstance(mo, vim.VirtualMachine):
        return False

    print('Powering on vm {0}'.format(mo._GetMoId()))
    try:
        wait_for_tasks(content, [mo.PowerOn()])
        print('{0} powered on successfully'.format(mo._GetMoId()))
    except Exception:
        print('Unexpected error while powering on vm {0}'.format(
            mo._GetMoId()))
        return False
    return True



#获取虚拟机状态
def getvmstatus(vm_name,si):
    content = si.RetrieveContent()
    for child in content.rootFolder.childEntity:
        if hasattr(child, 'vmFolder'):
            datacenter = child
            vmFolder = datacenter.vmFolder
            vmList = vmFolder.childEntity
            for vm in vmList:
                if vm.summary.config.name == vm_name :
                    print(vm.summary.runtime.powerState)

si = vShereconnect()          
# getvmstatus('centos-7.6-1810-mddlz-240',si)
poweronvm(si,'centos-7.6-1810-mddlz-240')