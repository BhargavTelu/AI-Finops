import { auth } from "@clerk/nextjs/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";

// Server-side Supabase client for Server Components and Route Handlers.
// Attaches the Clerk HS256 "supabase" template token so Supabase RLS can
// read the org_id claim. The RS256 Clerk session token must never be used
// here — Supabase only accepts HS256 tokens signed with its configured secret.
export async function createClient() {
  const cookieStore = await cookies();
  const { getToken } = await auth();
  // Returns null if the "supabase" JWT template doesn't exist in Clerk Dashboard,
  // or if the user has no active org (org.public_metadata.db_id not yet set).
  // Fallback to undefined keeps the anon key path, which returns zero rows from RLS.
  const supabaseToken = await getToken({ template: "supabase" });

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      global: supabaseToken
        ? { headers: { Authorization: `Bearer ${supabaseToken}` } }
        : undefined,
      cookies: {
        get(name: string) {
          return cookieStore.get(name)?.value;
        },
        set(name: string, value: string, options: CookieOptions) {
          cookieStore.set({ name, value, ...options });
        },
        remove(name: string, options: CookieOptions) {
          cookieStore.set({ name, value: "", ...options });
        },
      },
    }
  );
}
