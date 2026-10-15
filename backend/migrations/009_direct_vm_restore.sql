-- Extend the restore intent without weakening the existing isolated-export branch.
ALTER TABLE backupcenter.operation_requests DROP CONSTRAINT isolated_restore_intent;
ALTER TABLE backupcenter.operation_requests ADD CONSTRAINT isolated_restore_intent CHECK (
 kind <> 'restore' OR COALESCE((
  target ~ '^[1-9][0-9]{0,18}$'
  AND CASE WHEN target ~ '^[1-9][0-9]{0,18}$' THEN target::numeric <= 9223372036854775807 ELSE false END
  AND (
   (parameters->>'mode'='vm-disks-isolated' AND parameters->>'overwrite'='Never'
    AND parameters->>'destination'='/mnt/bareos-smb/backupcenter-restore-tests/' || idempotency_key::text)
   OR
   (parameters->>'mode'='vmware-new-vm' AND jsonb_typeof(parameters->'destination')='object'
    AND parameters->'destination'->>'power'='off' AND parameters->'destination'->>'network'='disconnected'
    AND parameters->'destination'->>'overwrite'='Never' AND parameters->>'reviewDigest' ~ '^[0-9a-f]{64}$'
    AND length(parameters->'destination'->>'vm_name') BETWEEN 1 AND 80)
  )
 ),false)
);
