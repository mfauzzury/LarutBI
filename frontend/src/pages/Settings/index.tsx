import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/lib/auth";
import { useChatStore } from "@/stores/chat";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default function SettingsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const resetChat = useChatStore((s) => s.reset);

  const handleLogout = () => {
    // Drop chat state and cached data so the next user on this browser can't see it
    resetChat();
    qc.clear();
    clearAuth();
    navigate("/login", { replace: true });
  };

  return (
    <div className="p-6 space-y-5 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-gray-500 mt-1">Your account.</p>
      </div>

      <section className="rounded-md border bg-white p-4 space-y-4">
        <dl className="grid grid-cols-[100px_1fr] gap-y-3 text-sm">
          <dt className="text-gray-500">Email</dt>
          <dd>{user?.email}</dd>
          <dt className="text-gray-500">Role</dt>
          <dd>
            <Badge variant="secondary">{user?.role}</Badge>
          </dd>
        </dl>

        <Button type="button" variant="outline" size="sm" onClick={handleLogout}>
          <LogOut size={15} />
          Log out
        </Button>
      </section>
    </div>
  );
}
