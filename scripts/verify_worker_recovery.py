"""Process interruption test in an isolated app DB namespace; Director I/O is mocked."""
import asyncio
from pathlib import Path
import os
import shlex
import subprocess
import sys
import time
from uuid import UUID, uuid4

import httpx
from dotenv import dotenv_values
from backend.persistence import ROOT, Store
from backend.operations import dispatch, worker

TARGET='VMware-fault-test'


class FakeGateway:
    def __init__(self,store,marker):
        self.store=store;self.lock=asyncio.Lock();self.context=True
        self.base='https://fixture.invalid';self.token='fixture-only';self.marker=marker
    async def get(self,client,path,query=None):
        if path=='/configuration/jobs':return {'jobs':{TARGET:{'type':'Backup','enabled':True}}}
        if path.startswith('/control/jobs?'):return {'totalItems':0,'jobs':[]}
        raise AssertionError('No real Director read is permitted in this test')


async def child(namespace,operation,marker,restart=False):
    store=Store();store.connection_id=str(UUID(namespace))
    gateway=FakeGateway(store,Path(marker))
    original=httpx.AsyncClient
    async def intercept(request):
        gateway.marker.write_text('Dispatching')
        await asyncio.Future()
        raise AssertionError('Simulated request must be interrupted')
    import backend.operations as operations
    operations.httpx.AsyncClient=lambda **kwargs:original(transport=httpx.MockTransport(intercept))
    if restart:
        await worker(lambda:gateway)
    else:
        row=store.operation(UUID(operation))
        await dispatch(gateway,row)


def cleanup(namespace):
    values=dotenv_values(ROOT/'.env')
    from urllib.parse import urlparse
    endpoint=urlparse(values['POSTGRES_HOST'] if '://' in values['POSTGRES_HOST'] else '//'+values['POSTGRES_HOST'])
    env=os.environ.copy();env.update(SSH_ASKPASS=str(ROOT/'.local/postgres-askpass'),SSH_ASKPASS_REQUIRE='force',DISPLAY='backupcenter-fault-test')
    args=['ssh','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(ROOT/'.local/postgres-knownhosts'),values['POSTGRES_USERNAME']+'@'+endpoint.hostname,"sudo -S -p '' runuser -u postgres -- psql -X -qAt -v ON_ERROR_STOP=1 -d backupcenter"]
    cid=str(UUID(namespace))
    assert cid!=Store().connection_id
    sql="BEGIN;DELETE FROM backupcenter.audit_events WHERE connection_id='"+cid+"';DELETE FROM backupcenter.operation_requests WHERE connection_id='"+cid+"';DELETE FROM backupcenter.connections WHERE id='"+cid+"';COMMIT;\n"
    result=subprocess.run(args,input=(values['POSTGRES_PASSWORD']+'\n'+sql).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=40)
    if result.returncode:raise RuntimeError('Isolated test fixture cleanup failed')


def verify():
    store=Store();main_namespace=store.connection_id
    namespace=str(uuid4());store.connection_id=namespace
    marker=ROOT/'.local/worker-interruption-marker'
    if marker.exists():marker.unlink()
    row=store.prepare('run',TARGET,uuid4(),'admin')
    first=second=None
    try:
        first=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-m','scripts.verify_worker_recovery','child',namespace,str(row['id']),str(marker)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        deadline=time.monotonic()+15
        while not marker.exists() and first.poll() is None and time.monotonic()<deadline:time.sleep(.1)
        if not marker.exists():raise RuntimeError('Simulated dispatch did not reach the interruption boundary')
        assert store.operation(row['id'])['state']=='Dispatching'
        first.kill();first.wait(timeout=5)
        second=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-m','scripts.verify_worker_recovery','restart',namespace,str(row['id']),str(marker)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        deadline=time.monotonic()+12
        while store.operation(row['id'])['state']!='Unknown' and second.poll() is None and time.monotonic()<deadline:time.sleep(.1)
        assert store.operation(row['id'])['state']=='Unknown'
        assert not store.operations(True),'Interrupted request must not reenter the send queue'
        assert not Store().operations(),'Real Director namespace must remain untouched'
        print('Real PostgreSQL + interrupted child + new worker startup verified: Dispatching -> Unknown; no resend; original operation namespace untouched.')
    finally:
        for process in (first,second):
            if process and process.poll() is None:process.terminate();process.wait(timeout=5)
        cleanup(namespace)
        if marker.exists():marker.unlink()


if __name__=='__main__':
    if len(sys.argv)>1:asyncio.run(child(sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[1]=='restart'))
    else:verify()
