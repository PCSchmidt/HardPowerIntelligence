import type { Metadata } from "next";
import { Shield } from "lucide-react";

import { ResetPasswordForm } from "@/components/auth/reset-password-form";

export const metadata: Metadata = {
  title: "Set a new password",
  robots: { index: false, follow: false },
};

export default function ResetPasswordPage() {
  return (
    <div className="mx-auto w-full max-w-sm px-4 py-20">
      <div className="rounded-xl border border-border bg-card p-8 shadow-md">
        <div className="mb-6 flex items-center gap-2 font-display text-lg font-bold text-brand">
          <Shield size={20} className="text-brand-secondary" />
          HPI
        </div>
        <h1 className="mb-6 font-display text-display-sm">Set a new password</h1>
        <ResetPasswordForm />
      </div>
    </div>
  );
}
