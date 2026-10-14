import BackupCenter from "@/components/backup-center";
import { AuthGate } from "@/components/auth";
export default function Page() {
  return (
    <AuthGate>
      <BackupCenter />
    </AuthGate>
  );
}
