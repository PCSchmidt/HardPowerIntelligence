import type { Metadata } from "next";
import { Shield } from "lucide-react";

import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";

export const metadata: Metadata = {
  title: "Reset your password",
  robots: { index: false, follow: false },
};

export default function ForgotPasswordPage() {
  return (
    <div className="mx-auto w-full max-w-sm px-4 py-20">
      <div className="rounded-xl border border-border bg-card p-8 shadow-md">
        <div className="mb-6 flex items-center gap-2 font-display text-lg font-bold text-brand">
          <Shield size={20} className="text-brand-secondary" />
          HPI
        </div>
        <h1 className="font-display text-display-sm">Reset your password</h1>
        <p className="mb-6 mt-1 text-ui-sm text-muted-foreground">
          Enter your email and we&apos;ll send you a link to set a new one.
        </p>
        <ForgotPasswordForm />
      </div>
    </div>
  );
}
