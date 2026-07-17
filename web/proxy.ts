import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const AUTH_REQUIRED_PREFIXES = ["/desk", "/brief", "/entity", "/graph", "/account"];
// Routes a signed-in user has no business on — they get bounced to the product.
// /reset-password is deliberately ABSENT (D141): the recovery link authenticates the user
// *before* they choose a new password, so listing it here would bounce them to the desk and
// make the password impossible to change — the deadlock this whole flow exists to remove.
// /auth/callback is likewise absent; it must run the code exchange on its own terms.
const AUTH_ROUTES = ["/login", "/signup", "/forgot-password"];

// Next 16 proxy (formerly middleware): refreshes the Supabase session cookie on
// every request and gates UX routing (D022). FastAPI remains the data authority.
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  if (!user && AUTH_REQUIRED_PREFIXES.some((p) => pathname.startsWith(p))) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (user && AUTH_ROUTES.some((p) => pathname.startsWith(p))) {
    const url = request.nextUrl.clone();
    url.pathname = "/desk/defense";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
