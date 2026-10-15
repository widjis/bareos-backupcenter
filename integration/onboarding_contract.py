"""Deterministic, secret-free review contract for the fixed VMware backup policy."""
import hashlib,json,re
from uuid import UUID
POLICY='vmware-twice-monthly-v1'
def build(uuid,label):
    if str(UUID(uuid))!=uuid or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,59}',label):raise ValueError('Invalid approved VM identity or repository label')
    job='VMware-'+label;storage='SMB-'+label
    def resource(kind,values):return kind+' {\n'+''.join(' '+k+' = '+str(v)+'\n' for k,v in values.items())+'}\n'
    files={
      'bareos-dir.d/storage/'+label+'.conf':resource('Storage',{'Name':storage,'Address':'127.0.0.1','Password':'"<existing-storage-secret>"','Device':storage,'Media Type':storage,'Maximum Concurrent Jobs':1}),
      'bareos-sd.d/device/'+label+'.conf':resource('Device',{'Name':storage,'Device Type':'File','Media Type':storage,'Archive Device':'/mnt/bareos-smb/'+label,'Label Media':'yes','Random Access':'yes','Automatic Mount':'yes','Removable Media':'no','Always Open':'no','Maximum Concurrent Jobs':1}),
      'bareos-dir.d/pool/'+label+'.conf':resource('Pool',{'Name':label,'Pool Type':'Backup','Storage':storage,'Recycle':'yes','AutoPrune':'no','Recycle Oldest Volume':'no','Volume Retention':'30 days','Maximum Volumes':6,'Label Format':'"'+label+'-"'}),
      'bareos-dir.d/fileset/'+label+'.conf':'FileSet {\n Name = '+job+'\n Include {\n  Options {\n   Signature = XXH128\n   Compression = LZ4\n  }\n  Plugin = "python3:module_path=/opt/bareos/25.1.1/lib/bareos/plugins:module_name=bareos-fd-vmware:uuid='+uuid+':enable_cbt=yes:config_file=/etc/bareos/vmware-plugin.ini"\n }\n}\n',
      'bareos-dir.d/job/'+label+'.conf':resource('Job',{'Name':job,'JobDefs':'DefaultJob','Client':'bareos-fd','FileSet':job,'Storage':storage,'Pool':label,'Full Backup Pool':label,'Incremental Backup Pool':label,'Differential Backup Pool':label,'Level':'Incremental','Schedule':'VMwareTwiceMonthly','Enabled':'yes','Priority':16,'Maximum Concurrent Jobs':1,'Max Run Time':'4 hours','Max Wait Time':'24 hours','Run Before Job':'"/opt/bareos/25.1.1/lib/bareos/scripts/prepare-vm-backup '+label+' %l"'})}
    digest=hashlib.sha256(json.dumps({'uuid':uuid,'label':label,'policy':POLICY,'files':files},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'job':job,'fileset':job,'pool':label,'storage':storage,'folder':'/mnt/bareos-smb/'+label,'files':files,'digest':digest,'policyKey':POLICY}
