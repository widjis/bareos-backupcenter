"""Apply the isolated Bareos 25.1.1 UUID context compatibility fix."""
import ast,shutil,types
from pathlib import Path
METHOD='''    def get_vm_details_by_uuid(self):
        """Resolve UUID and populate the same inventory context as path lookup."""
        self.vm = self.si.content.searchIndex.FindByUuid(None, self.options["uuid"], True, True)
        if self.vm is None:
            return False
        parent = self.vm.parent
        folders = []
        while parent is not None and not isinstance(parent, vim.Datacenter):
            folders.append(parent)
            parent = parent.parent
        if parent is None:
            return False
        self.dc = parent
        self.options["dc"] = parent.name
        self.options["vmname"] = self.vm.name
        implicit = parent.vmFolder._moId
        self.options["folder"] = "/" + "/".join(folder.name for folder in reversed(folders) if folder._moId != implicit)
        return True

'''
def check():
    class DC:pass
    class Folder:
        def __init__(self,name,parent,moid):self.name=name;self.parent=parent;self._moId=moid
    dc=DC();dc.name='DC';implicit=Folder('vm',dc,'group-v1');dc.vmFolder=implicit
    vm=Folder('PNET',Folder('Discovered virtual machine',implicit,'group-v2'),'vm-1')
    ns={'vim':types.SimpleNamespace(Datacenter=DC)}
    exec(compile(ast.Module(body=[ast.parse(METHOD.strip()).body[0]],type_ignores=[]),'<uuid-test>','exec'),ns)
    def obj(result):return types.SimpleNamespace(options={'uuid':'test'},si=types.SimpleNamespace(content=types.SimpleNamespace(searchIndex=types.SimpleNamespace(FindByUuid=lambda *a:result))))
    x=obj(vm);assert ns['get_vm_details_by_uuid'](x) and x.dc is dc and x.options['dc']=='DC' and x.options['vmname']=='PNET' and x.options['folder']=='/Discovered virtual machine'
    assert not ns['get_vm_details_by_uuid'](obj(None))
    assert not ns['get_vm_details_by_uuid'](obj(Folder('lost',None,'vm-2')))
    x=obj(Folder('direct',implicit,'vm-3'));assert ns['get_vm_details_by_uuid'](x) and x.options['folder']=='/'
    return 4
def apply(path):
    p=Path(path);s=p.read_text();a=s.index('    def get_vm_details_by_uuid(self):');b=s.index('    def _get_dcftree(',a)
    fixed=s[:a]+METHOD+s[b:];ast.parse(fixed);p.write_text(fixed)
if __name__=='__main__':
    import sys
    print(str(check())+' isolated UUID context checks passed')
    if len(sys.argv)>1:apply(sys.argv[1])
