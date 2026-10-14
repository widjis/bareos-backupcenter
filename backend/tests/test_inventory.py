import asyncio
from types import SimpleNamespace as S

import pytest
from pyVmomi import vim
from backend.inventory import Inventory, InventoryError, entities, reconcile


def obj(kind, key, **props):
    return S(obj=kind(key), propSet=[S(name=k, val=v) for k,v in props.items()])


def fixture(name="VM", folder="Production", uuid="instance-one"):
    return [obj(vim.Datacenter,"dc-1",name="DC",vmFolder=vim.Folder("group-1")),obj(vim.Folder,"group-1",name="vm",parent=vim.Datacenter("dc-1")),obj(vim.Folder,"group-2",name=folder,parent=vim.Folder("group-1")),obj(vim.VirtualMachine,"vm-1",**{"name":name,"parent":vim.Folder("group-2"),"config.instanceUuid":uuid})]


def test_scoped_identity_survives_rename_and_move():
    folders,vms=entities(fixture(),"connection-a")
    moved=entities(fixture("Renamed","Other"),"connection-a")[1][0]
    other=entities(fixture(),"connection-b")[1][0]
    assert vms[0]["id"]==moved["id"]!=other["id"]
    assert vms[0]["folder"]=="/Production"
    assert moved["folder"]=="/Other"
    assert vms[0]["datacenter"]=="DC"
    assert len(folders)==3


def test_names_are_candidates_not_identity_bindings():
    vm=entities(fixture(),"a")[1][0]
    w={"name":"VM","folder":"/Production","datacenter":"DC","job":"VMware-VM","evidence":"Backup recorded"}
    assert reconcile([vm],[w])[0]["association"]=="Candidate match"
    assert reconcile([vm,{**vm,"id":"other"}],[w])[0]["association"]=="Ambiguous match"
    assert reconcile([vm],[{**w,"datacenter":"Other"}])[0]["association"]=="Unassigned"
    assert reconcile([{**vm,"name":"Renamed"}],[{**w,"instanceUuid":"instance-one"}])[0]["association"]=="Identity match"


def test_missing_uuid_is_explicit():
    vm=entities(fixture(uuid=None),"a")[1][0]
    assert vm["identityQuality"]=="moref-only"
    assert vm["instanceUuid"] is None


class Store:
    def connect(self): raise RuntimeError("offline")


def test_failed_initial_load_is_not_empty_success(monkeypatch):
    inv=Inventory(Store())
    monkeypatch.setattr(inv,"collect",lambda: (_ for _ in ()).throw(InventoryError("A valid VMware certificate fingerprint is required.")))
    result=asyncio.run(inv.snapshot())
    assert result["state"]=="unavailable" and result["syncedAt"] is None


def test_saved_inventory_is_stale_on_auth_failure(monkeypatch):
    inv=Inventory(Store())
    payload={"vms":[{"id":"vm"}],"folders":[],"syncedAt":"2026-10-14T00:00:00Z"}
    monkeypatch.setattr(inv,"load",lambda:payload)
    monkeypatch.setattr(inv,"collect",lambda: (_ for _ in ()).throw(vim.fault.InvalidLogin()))
    result=asyncio.run(inv.snapshot())
    assert result["state"]=="stale" and result["vms"]==payload["vms"]
    assert result["error"]=="VMware authentication failed."


def test_untrusted_exception_text_is_not_returned(monkeypatch):
    inv=Inventory(Store())
    monkeypatch.setattr(inv,"collect",lambda: (_ for _ in ()).throw(ValueError("password=secret")))
    result=asyncio.run(inv.snapshot())
    assert "secret" not in str(result)


def test_replaced_vcenter_does_not_overwrite_saved_inventory(monkeypatch):
    inv=Inventory(Store())
    monkeypatch.setattr(inv,"load",lambda:{"vcenterUuid":"old","syncedAt":"old-time","vms":[],"folders":[]})
    monkeypatch.setattr(inv,"collect",lambda:{"vcenterUuid":"new","syncedAt":"new-time","vms":[],"folders":[]})
    result=asyncio.run(inv.snapshot())
    assert result["state"]=="stale" and result["vcenterUuid"]=="old"



def test_permission_failure_remains_unavailable_not_empty(monkeypatch):
    inv=Inventory(Store())
    monkeypatch.setattr(inv,"collect",lambda:(_ for _ in ()).throw(vim.fault.NoPermission()))
    result=asyncio.run(inv.snapshot())
    assert result["state"]=="unavailable" and result["error"]=="VMware inventory permission denied."
