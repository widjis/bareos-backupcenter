-- Durable restore intents cannot request another destination or overwrite mode.
ALTER TABLE backupcenter.operation_requests ADD CONSTRAINT isolated_restore_intent CHECK (
 kind <> 'restore' OR (
  target ~ '^[1-9][0-9]{0,18}$'
  AND CASE WHEN target ~ '^[1-9][0-9]{0,18}$' THEN target::numeric <= 9223372036854775807 ELSE false END
  AND COALESCE(parameters->>'mode' = 'vm-disks-isolated',false)
  AND COALESCE(parameters->>'overwrite' = 'Never',false)
  AND COALESCE(parameters->>'destination' = '/mnt/bareos-smb/backupcenter-restore-tests/' || idempotency_key::text,false)
 )
);
