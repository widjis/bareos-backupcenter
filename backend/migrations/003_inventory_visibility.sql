-- Retain history when a removed VM's MoRef is reused by a different instance.
ALTER TABLE backupcenter.inventory_vms DROP CONSTRAINT inventory_vms_connection_id_moref_key;
CREATE UNIQUE INDEX inventory_vm_visible_moref ON backupcenter.inventory_vms(connection_id,moref) WHERE visible;
