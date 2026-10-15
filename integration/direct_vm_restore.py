"""Root-owned typed new-VM restore gateway. No arbitrary command or original-VM writes."""
import base64,configparser,hashlib,json,os,re,ssl,stat,subprocess,sys,time,zlib
from pathlib import Path
from uuid import UUID
from pyVim.connect import Connect,Disconnect
from pyVmomi import vim
from pyVim.task import WaitForTask
ROOT=Path('/var/lib/bareos-vm-restore')
SCOPE=Path('/opt/bareos-api/direct-vm-restore-scope.json')
BC='/opt/bareos/25.1.1/sbin/bconsole'
def require(condition,message):
    if not condition:raise ValueError(message)
def rpc(text):
    out=[];d=json.JSONDecoder();i=0
    while i<len(text):
        j=text.find('{',i)
        if j<0:break
        try:o,n=d.raw_decode(text[j:]);i=j+n
        except ValueError:i=j+1;continue
        if isinstance(o,dict) and o.get('jsonrpc')=='2.0':out.append(o)
    return out
def console(command,mutation=False):
    p=subprocess.run([BC],input='.api 2\n'+command+'\nquit\n',text=True,capture_output=True,timeout=45)
    results=rpc(p.stdout)
    require(p.returncode==0 and len(results)>=2,'Director result unavailable; reconcile before retrying.')
    o=results[1]
    require('error' not in o,'Director rejected command; inspect Director history before retrying.')
    return o['result']
def scope():
    m=SCOPE.lstat();require(stat.S_ISREG(m.st_mode) and m.st_uid==0 and not m.st_mode&0o022,'Root restore scope is invalid.')
    return json.loads(SCOPE.read_text())
def connect():
    c=configparser.ConfigParser(interpolation=None);c.read('/etc/bareos/vmware-plugin.ini');o=c['vmware_plugin_options']
    return Connect(host=o['vcserver'],user=o['vcuser'],pwd=o['vcpass'],thumbprint=o['vcthumbprint'],sslContext=ssl._create_unverified_context(),httpConnectionTimeout=15)
def objects(si,types):
    v=si.content.viewManager.CreateContainerView(si.content.rootFolder,types,True)
    try:r=list(v.view);require(len(r)<=5000,'Restore topology exceeds inspection limit.');return r
    finally:v.Destroy()
def topology(si):
    rows=[]
    for dc in objects(si,[vim.Datacenter]):
        folders=[]
        def visit(f,path):
            require(len(folders)<1000,'VM folder limit exceeded.');folders.append({'name':f.name,'path':path,'id':f._moId})
            for x in f.childEntity:
                if isinstance(x,vim.Folder):visit(x,path.rstrip('/')+'/'+x.name)
        visit(dc.vmFolder,'/')
        hosts=[]
        for h in objects(si,[vim.HostSystem]):
            p=h.parent
            while p is not None and not isinstance(p,vim.Datacenter):p=p.parent
            if p!=dc or str(h.runtime.connectionState)!='connected' or h.runtime.inMaintenanceMode:continue
            hosts.append({'name':h.name,'id':h._moId,'datastores':[{'name':d.name,'id':d._moId,'freeBytes':d.summary.freeSpace} for d in h.datastore if d.summary.accessible and d.summary.maintenanceMode=='normal']})
        rows.append({'name':dc.name,'id':dc._moId,'folders':folders,'hosts':hosts})
    return {'datacenters':rows,'vcenterUuid':si.content.about.instanceUuid,'syncedAt':time.time(),'trust':'Pinned certificate','dispatchScope':scope()['jobs']}
def numeric(value):
    require(isinstance(value,int) and not isinstance(value,bool) and 0<value<2**63,'Invalid source JobId.');return value
def source(jobid):
    numeric(jobid);rows=console('llist jobid='+str(jobid)).get('jobs',[])
    require(len(rows)==1,'Backup source not found.');r=rows[0]
    require(r['name'] in scope()['jobs'] and r['type']=='B' and r['jobstatus'] in ('T','W') and str(r['purgedfiles'])=='0','Source is outside the approved restore scope or incomplete.')
    ids=[int(x['id']) for x in console('.bvfs_get_jobids jobid='+str(jobid)).get('jobids',[])]
    require(jobid in ids and 0<len(ids)<=100,'Incomplete backup chain.');media=set();full=False
    for n in ids:
        x=console('llist jobid='+str(n))['jobs'][0]
        require(x['clientid']==r['clientid'] and x['filesetid']==r['filesetid'] and x['jobstatus'] in ('T','W') and str(x['purgedfiles'])=='0','Backup chain mismatch.')
        full|=x['level']=='F';mm=console('list jobmedia jobid='+str(n)).get('jobmedia',[]);require(bool(mm),'Missing chain media.')
        media.update(x['volumename'] for x in mm)
    require(full,'Full baseline missing.')
    # Read backed-up configuration, including when the original VM has disappeared.
    query="SELECT objectcompression,encode(restoreobject,'base64') FROM restoreobject WHERE jobid="+str(jobid)+" AND objectname LIKE '%/vm_config.json%' ORDER BY restoreobjectid DESC LIMIT 1"
    p=subprocess.run(['runuser','-u','bareos','--','psql','-X','-At','-d','bareos','-c',query],capture_output=True,text=True,check=True)
    compression,data=p.stdout.strip().split('|',1);raw=base64.b64decode(data);raw=zlib.decompress(raw) if compression=='1' else raw
    config=json.loads(raw)
    disk_stores={x.get('backing',{}).get('fileName','').split(']')[0] for x in config['hardware']['device'] if 'capacityInKB' in x}
    require(len(disk_stores)==1,'Multi-datastore source disks require separate mapping and are not enabled in this restore mode.')
    required=sum(x.get('capacityInKB',0)*1024 for x in config['hardware']['device'] if 'capacityInKB' in x)
    require(required>0,'Backup disk capacity unavailable.')
    jobs=console('show jobs')['jobs'];definition=jobs[r['name']];fs=definition['fileset'];sets=console('show filesets')['filesets'];plugin=' '.join(str(p) for i in sets[fs].get('include',[]) for p in i.get('plugin',[]))
    require('bareos-fd-vmware' in plugin,'Source is not a VMware backup.')
    for name in (definition['client'],fs,*definition['storage']):require(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',name),'Unsupported source resource name.')
    return r,ids,config,required,definition,sorted(media)
def validate(si,jobid,destination):
    from vm_restore_contract import VMRestoreDestination
    installed=Path('/opt/bareos/25.1.1/lib/bareos/plugins/bareos-fd-vmware.py').read_text()
    require('def backupcenter_restore_options(' in installed and 'config.deviceChange = [c for c in config.deviceChange if not isinstance(c.device, vim.vm.device.VirtualEthernetCard)]' in installed,'The required scoped restore plugin patch is unavailable.')
    d=VMRestoreDestination(**destination).model_dump();r,ids,c,required,definition,media=source(jobid)
    top=topology(si);dcs=[x for x in objects(si,[vim.Datacenter]) if x.name==d['datacenter']];require(len(dcs)==1,'Select a unique destination datacenter.');dc=dcs[0]
    folder=si.content.searchIndex.FindByInventoryPath(dc.name+'/vm'+('' if d['folder']=='/' else d['folder']));require(isinstance(folder,vim.Folder),'Destination VM folder not found.')
    require(not any(v.name==d['vm_name'] for v in objects(si,[vim.VirtualMachine])),'VM name already exists; overwrite is forbidden.')
    candidate=next((x for x in top['datacenters'] if x['name']==dc.name),None);hosts=[h for h in candidate['hosts'] if h['name']==d['host']];require(len(hosts)==1,'Host is not connected or belongs to another datacenter.')
    stores=[x for x in hosts[0]['datastores'] if x['name']==d['datastore']];require(len(stores)==1,'Datastore is inaccessible from the selected host.');ds=next(x for x in dc.datastore if x._moId==stores[0]['id']);required=int(required*1.1)+c['hardware'].get('memoryMB',0)*1024*1024;require(ds.summary.freeSpace>=required,'Insufficient datastore space including safety reserve.')
    host=next(h for h in objects(si,[vim.HostSystem]) if h._moId==hosts[0]['id'])
    privileges=[(folder,['VirtualMachine.Inventory.Create']),(ds,['Datastore.AllocateSpace']),(host.parent.resourcePool,['Resource.AssignVMToPool'])]
    for entity,priv in privileges:
        rows=si.content.authorizationManager.HasPrivilegeOnEntities([entity],si.content.sessionManager.currentSession.key,priv)
        require(rows and all(p.isGranted for p in rows[0].privAvailability),'VMware account lacks required destination privileges.')
    try:
        task=ds.browser.SearchDatastore_Task(datastorePath='['+ds.name+'] '+d['vm_name']);WaitForTask(task)
    except vim.fault.FileNotFound:pass
    else:raise ValueError('Destination datastore directory already exists; overwrite is forbidden.')
    reservation=ROOT/('target-'+hashlib.sha256((top['vcenterUuid']+':'+d['vm_name']).encode()).hexdigest()+'.json')
    require(not reservation.exists(),'A restore intent has already reserved this new VM name. Reconcile its receipt before reuse.')
    body={'sourceJobId':jobid,'jobIds':ids,'destination':d,'mode':'vmware-new-vm','vcenterUuid':top['vcenterUuid'],'targetRefs':{'folder':folder._moId,'host':host._moId,'datastore':ds._moId}}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {**body,'reviewDigest':digest,'requiredBytes':required,'freeBytes':ds.summary.freeSpace,'requiredMedia':media,'blockers':[],'dispatchEnabled':True,'targetVerified':True,'uuidSource':True,'state':'Ready for confirmation'},definition

def handle(body):
    require(os.geteuid()==0,'Administrator service required.');action=body.get('action')
    require(action in ('targets','plan','dispatch','status','verify'),'Unsupported restore action.')
    if action=='status':
        rid=str(UUID(body['request_id']));p=ROOT/(rid+'.json');r=json.loads(p.read_text());boot=ROOT/(rid+'-boot.json');r['bootVerification']=json.loads(boot.read_text()) if boot.exists() else {'bootVerified':False};return r
    si=connect()
    try:
        if action=='verify':
            rid=str(UUID(body['request_id']));receipt=ROOT/(rid+'.json');r=json.loads(receipt.read_text());d=r['destination']
            row=console('llist jobid='+str(r['jobid']))['jobs'][0];require(row['type']=='R' and row['jobstatus'] in ('T','W'),'Restore job has not succeeded.')
            path=d['datacenter']+'/vm/'+d['folder'].strip('/')+'/'+d['vm_name'];path='/'.join(x for x in path.split('/') if x)
            vm=si.content.searchIndex.FindByInventoryPath(path)
            require(isinstance(vm,vim.VirtualMachine) and vm.config.annotation=='Bareos isolated restore '+rid,'Restored VM identity mismatch.')
            require(str(vm.runtime.powerState)=='poweredOff' and not vm.snapshot,'Restored VM must be off without snapshots.')
            require(not any(isinstance(x,vim.vm.device.VirtualEthernetCard) for x in vm.config.hardware.device),'Restored VM still has a network adapter.')
            r.update(state='Completed',isolationVerified=True,vmMoref=vm._moId,vmInstanceUuid=vm.config.instanceUuid,power='poweredOff',networkAdapters=0)
            receipt.write_text(json.dumps(r));return r
        if action=='targets':require(set(body)=={'action'},'Unexpected target parameters.');return topology(si)
        require(set(body)==({'action','job_id','destination'} if action=='plan' else {'action','job_id','destination','request_id','digest'}),'Unexpected restore parameters.')
        if action=='dispatch':
            rid=str(UUID(body['request_id']));ROOT.mkdir(mode=0o700,exist_ok=True);receipt=ROOT/(rid+'.json')
            if receipt.exists():
                saved=json.loads(receipt.read_text());require(saved.get('reviewDigest')==body['digest'] and saved['sourceJobId']==body['job_id'] and saved['destination']==body['destination'],'Request key belongs to another intent.');return saved
        plan,definition=validate(si,body['job_id'],body['destination'])
        if action=='plan':return plan
        require(plan['reviewDigest']==body['digest'],'Destination/source changed since review. Review again.')
        plan.update(requestId=rid,state='Dispatching')
        reservation=ROOT/('target-'+hashlib.sha256((plan['vcenterUuid']+':'+plan['destination']['vm_name']).encode()).hexdigest()+'.json')
        with reservation.open('x') as f:json.dump({'requestId':rid,'reviewDigest':body['digest']},f)
        reservation.chmod(0o600)
        with receipt.open('x') as f:json.dump(plan,f)
        receipt.chmod(0o600)
        client=definition['client'];storage=definition['storage'];require(len(storage)==1,'Source Storage ambiguous.')
        # Plugin reads the root receipt to override UUID, and refuses existing targets.
        command='restore jobid='+','.join(map(str,plan['jobIds']))+' client='+client+' restoreclient='+client+' fileset='+definition['fileset']+' restorejob=RestoreFiles storage='+storage[0]+' replace=never pluginoptions=python:module_name=bareos-fd-vmware:config_file=/etc/bareos/vmware-plugin.ini:backupcenter_request='+rid+' comment=backupcenter-'+rid+' select all done yes'
        try:
            result=console(command,True);n=int(result['run']['jobid']);require(n>0,'JobId unconfirmed.');plan.update(jobid=n,state='Accepted')
        except Exception:
            plan.update(state='Unknown');receipt.write_text(json.dumps(plan));raise
        receipt.write_text(json.dumps(plan));return plan
    finally:Disconnect(si)
if __name__=='__main__':
    try:print(json.dumps(handle(json.load(sys.stdin))))
    except Exception as e:
        message=str(e) if isinstance(e,ValueError) else 'Restore gateway failed; reconcile the root receipt before retrying.'
        print(json.dumps({'error':message[:250]}));sys.exit(1)
