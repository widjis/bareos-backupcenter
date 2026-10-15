"""Reproducible opt-in patch for root-receipt new-VM restores only."""
def patch(source):
    if 'def backupcenter_restore_options(' in source:return source
    source=source.replace('            "restore_powerstate",','            "restore_powerstate",\n            "backupcenter_request",',1)
    anchor='    def start_restore_job(self):'
    method='''    def backupcenter_restore_options(self):
        """Read immutable destination from a root-owned scoped restore receipt."""
        import json, os, stat
        from uuid import UUID
        rid = self.options.get("backupcenter_request")
        if not rid:
            return
        rid = str(UUID(rid))
        path = "/var/lib/bareos-vm-restore/" + rid + ".json"
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            metadata = os.fstat(stream.fileno())
            if metadata.st_uid != 0 or metadata.st_mode & 0o077 or not stat.S_ISREG(metadata.st_mode):
                raise ValueError("Invalid root restore receipt")
            receipt = json.load(stream)
        if receipt["state"] not in ("Dispatching", "Accepted") or receipt["requestId"] != rid:
            raise ValueError("Restore receipt is not active")
        d = receipt["destination"]
        if d["power"] != "off" or d["network"] != "disconnected" or d["overwrite"] != "Never":
            raise ValueError("Invalid isolated restore invariants")
        self.options.pop("uuid", None)
        self.options.update(dc=d["datacenter"], folder=d["folder"], vmname=d["vm_name"], restore_esxhost=d["host"], restore_datastore=d["datastore"], restore_powerstate="off", localvmdk="no")
        self.vadp.options = self.options

'''
    assert source.count(anchor)==1;source=source.replace(anchor,method+anchor)
    at=source.index(anchor);before=source[:at];after=source[at:]
    marker='        check_option_bRC = self.check_plugin_options()'
    assert marker in after;after=after.replace(marker,'        self.backupcenter_restore_options()\n\n'+marker,1);source=before+after
    marker='        return self.vadp.prepare_vm_restore()'
    guarded='''        if self.options.get("backupcenter_request"):
            path = self.options["dc"] + "/vm/" + self.options["folder"].strip("/") + "/" + self.options["vmname"]
            path = "/".join(x for x in path.split("/") if x)
            if self.vadp.si.content.searchIndex.FindByInventoryPath(path) is not None:
                raise ValueError("Restore target already exists; overwrite forbidden")
        return self.vadp.prepare_vm_restore()'''
    assert source.count(marker)==1;source=source.replace(marker,guarded)
    marker='        found_dc = self.si.content.searchIndex.FindByInventoryPath(self.options["dc"])'
    isolated='''        if self.options.get("backupcenter_request"):
            # No NIC exists even during VM creation. Isolated boot cannot reach production.
            config.deviceChange = [c for c in config.deviceChange if not isinstance(c.device, vim.vm.device.VirtualEthernetCard)]
            config.annotation = "Bareos isolated restore " + self.options["backupcenter_request"]

'''
    assert source.count(marker)==1;source=source.replace(marker,isolated+marker)
    return source
if __name__=='__main__':
    import sys
    from pathlib import Path
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
