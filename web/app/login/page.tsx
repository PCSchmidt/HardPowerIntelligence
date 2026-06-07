import { Suspense } from "react";
import type { Metadata } from "next";
import { Shield } from "lucide-react";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = {
  title: "Sign In",
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  return (
    <div className="mx-auto w-full max-w-sm px-4 py-20">
      <div className="rounded-xl border border-border bg-card p-8 shadow-md">
        <div className="mb-6 flex items-center gap-2 font-display text-lg font-bold text-brand">
          <Shield size={20} className="text-brand-secondary" />
          HPI
        </div>
        <h1 className="mb-6 font-display text-display-sm">Sign in</h1>
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
